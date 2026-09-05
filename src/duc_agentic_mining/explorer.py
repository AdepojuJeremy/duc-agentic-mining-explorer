from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import append_jsonl
from .config import ExplorationConfig
from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import Candidate, RunMetrics, ToolEvent, stable_id
from .prompts import EXPLORER_SYSTEM


def explorer_tools(cfg: ExplorationConfig) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "search_sources",
            "description": "Search the trusted local source corpus for clinically relevant records.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": cfg.max_results_per_search,
                    },
                },
                "required": ["query", "limit"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "open_source",
            "description": "Open one source record by exact source_id before using it in a candidate.",
            "parameters": {
                "type": "object",
                "properties": {"source_id": {"type": "string"}},
                "required": ["source_id"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "record_candidate",
            "description": "Record a proposed DUC evidence route. This does not validate or endorse it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision_question": {"type": "string"},
                    "baseline_source_id": {"type": "string"},
                    "modifier_source_id": {"type": "string"},
                    "relationship_summary": {"type": "string"},
                    "proposed_arm": {
                        "type": "string",
                        "enum": [
                            "contradictory",
                            "complicating",
                            "uncertainty_inducing",
                            "no_conflict_control",
                        ],
                    },
                    "expected_update": {
                        "type": "string",
                        "enum": ["maintain", "revise", "weaken", "strengthen", "abstain"],
                    },
                    "rationale": {"type": "string"},
                    "concerns": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "decision_question",
                    "baseline_source_id",
                    "modifier_source_id",
                    "relationship_summary",
                    "proposed_arm",
                    "expected_update",
                    "rationale",
                    "concerns",
                ],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "finish_round",
            "description": "End the exploration round when enough candidates are recorded or further search is unlikely to help.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


async def explore_round(
    round_id: str,
    anchor_id: str,
    corpus: CorpusStore,
    client: OpenAIRoleClient,
    cfg: ExplorationConfig,
    metrics: RunMetrics,
    trajectory_path: Path,
    existing_pair_keys: set[tuple[str, str]],
) -> list[Candidate]:
    anchor = corpus.get(anchor_id)
    if not anchor:
        return []
    candidates: list[Candidate] = []
    opened = {anchor_id}
    searches = 0
    opens = 0
    finished = False

    def emit(event: ToolEvent) -> None:
        payload = event.model_dump(mode="json")
        if (
            not cfg.trace_include_tool_outputs
            and event.kind == "tool_result"
            and event.name == "open_source"
        ):
            result = payload.get("payload", {}).get("result")
            if isinstance(result, dict) and "text" in result:
                result["text"] = (
                    result["text"][:1000] + "…"
                    if len(result["text"]) > 1000
                    else result["text"]
                )
        append_jsonl(trajectory_path, payload)

    def dispatch(name: str, args: dict[str, Any]) -> Any:
        nonlocal searches, opens, finished
        if name == "search_sources":
            if searches >= cfg.max_searches_per_round:
                return {"ok": False, "error": "search budget exhausted"}
            searches += 1
            metrics.searches += 1
            return {
                "ok": True,
                "results": corpus.search(
                    args["query"],
                    min(args["limit"], cfg.max_results_per_search),
                    exclude_ids=opened,
                ),
            }
        if name == "open_source":
            if opens >= cfg.max_opens_per_round:
                return {"ok": False, "error": "open budget exhausted"}
            record = corpus.get(args["source_id"])
            if not record:
                return {"ok": False, "error": "unknown source_id"}
            opens += 1
            metrics.opens += 1
            opened.add(record.source_id)
            return {"ok": True, **record.model_dump(mode="json")}
        if name == "record_candidate":
            if len(candidates) >= cfg.max_candidates_per_round:
                return {"ok": False, "error": "candidate budget exhausted"}
            if (
                args["baseline_source_id"] not in opened
                or args["modifier_source_id"] not in opened
            ):
                return {"ok": False, "error": "both sources must be opened before recording"}
            if not corpus.get(args["baseline_source_id"]) or not corpus.get(
                args["modifier_source_id"]
            ):
                return {"ok": False, "error": "unknown source id"}
            pair_key = tuple(
                sorted((args["baseline_source_id"], args["modifier_source_id"]))
            )
            if pair_key in existing_pair_keys:
                return {"ok": False, "error": "duplicate source pair"}
            uid = stable_id("candidate", *pair_key, args["decision_question"])
            candidate = Candidate(
                candidate_uid=uid,
                round_id=round_id,
                anchor_source_id=anchor_id,
                **args,
            )
            candidates.append(candidate)
            existing_pair_keys.add(pair_key)
            metrics.candidates_recorded += 1
            return {"ok": True, "candidate_uid": uid, "recorded": len(candidates)}
        if name == "finish_round":
            finished = True
            emit(
                ToolEvent(
                    kind="round_end",
                    name="finish_round",
                    payload={"reason": args["reason"]},
                )
            )
            return {"ok": True, "finished": True, "_stop": True}
        return {"ok": False, "error": f"unknown tool {name}"}

    prompt = (
        f"ROUND_ID: {round_id}\n"
        f"ANCHOR_SOURCE:\n{json.dumps(anchor.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        "Explore for one or more clinically stageable evidence routes starting from this anchor."
    )
    metrics.exploration_rounds_started += 1
    try:
        await client.tool_loop(
            EXPLORER_SYSTEM,
            prompt,
            explorer_tools(cfg),
            dispatch,
            cfg.max_turns_per_round,
            emit,
        )
    except Exception as exc:
        emit(
            ToolEvent(
                kind="error",
                name="exploration",
                payload={"error": f"{type(exc).__name__}: {exc}"},
            )
        )
    metrics.exploration_rounds_completed += 1
    if not finished:
        emit(
            ToolEvent(
                kind="round_end",
                name="implicit_end",
                payload={"candidates": len(candidates)},
            )
        )
    return candidates
