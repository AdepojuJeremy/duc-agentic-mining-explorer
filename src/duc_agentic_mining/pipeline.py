from __future__ import annotations

import asyncio
import random
import subprocess
import time
from pathlib import Path

from .artifacts import atomic_yaml, load_yaml_items, write_jsonl
from .config import PipelineConfig
from .contracts import build_construction_contract
from .corpus import CorpusStore, build_index
from .dedup import is_near_duplicate
from .explorer import explore_round
from .generator import generate_vignette
from .llm import OpenAIRoleClient
from .models import (
    Candidate,
    CandidateValidation,
    ConstructionContract,
    ProposalReview,
    RunMetrics,
    VignetteProposal,
    utc_now,
)
from .reviewer import review_proposal
from .targeting import (
    choose_target_cells,
    equal_cell_targets,
    matrix_status,
    proposal_counts,
    select_balanced,
)
from .validator import validate_candidate


class RunPaths:
    def __init__(self, root: Path):
        self.root = root
        self.candidates = root / "candidates.yaml"
        self.validations = root / "validations.yaml"
        self.contracts = root / "construction_contracts.yaml"
        self.proposals = root / "vignette_proposals.yaml"
        self.reviews = root / "proposal_reviews.yaml"
        self.metrics = root / "metrics.yaml"
        self.manifest = root / "run_manifest.yaml"
        self.target_matrix = root / "target_matrix.yaml"
        self.passed_jsonl = root / "passed_vignettes.jsonl"
        self.trajectories = root / "trajectories"


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


class AgenticMiningPipeline:
    def __init__(
        self,
        cfg: PipelineConfig,
        run_id: str,
        target_passed: int | None = None,
    ):
        self.cfg = cfg
        self.run_id = run_id
        self.target_passed = target_passed or cfg.target_passed
        self.paths = RunPaths(cfg.output_root / run_id)
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.trajectories.mkdir(parents=True, exist_ok=True)
        self.metrics = self._load_metrics()
        if cfg.corpus.input_paths:
            self.corpus, _ = build_index(cfg.corpus, replace=False)
        else:
            self.corpus = CorpusStore(cfg.corpus.index_path, cfg.corpus.search_snippet_chars)
        if self.corpus.count() == 0:
            raise RuntimeError(
                "corpus index is empty; run `duc-agentic index CONFIG` or configure corpus.input_paths"
            )
        self.clients = {
            role: OpenAIRoleClient(role, cfg.openai, role_cfg, self.metrics)
            for role, role_cfg in cfg.roles.items()
        }
        self.started_monotonic = time.monotonic()
        self.cell_targets = (
            equal_cell_targets(self.target_passed, cfg.target_matrix)
            if cfg.target_matrix.balance_mode == "equal"
            else {}
        )

    def _load_metrics(self) -> RunMetrics:
        if self.paths.metrics.exists():
            import yaml

            return RunMetrics.model_validate(
                yaml.safe_load(self.paths.metrics.read_text(encoding="utf-8"))
            )
        return RunMetrics(run_id=self.run_id)

    def _persist_metrics(self) -> None:
        self.metrics.updated_at = utc_now()
        self.metrics.elapsed_seconds += max(0, time.monotonic() - self.started_monotonic)
        self.started_monotonic = time.monotonic()
        atomic_yaml(self.paths.metrics, self.metrics)

    def _manifest(self) -> None:
        atomic_yaml(
            self.paths.manifest,
            {
                "run_id": self.run_id,
                "target_passed": self.target_passed,
                "started_at": self.metrics.started_at,
                "pipeline_version": "0.3.0",
                "git_sha": git_sha(),
                "config": self.cfg.model_dump(mode="json"),
            },
        )

    def _update_matrix_artifact(self, accepted: list[VignetteProposal]) -> None:
        counts = proposal_counts(accepted)
        self.metrics.passed_by_domain = {}
        self.metrics.passed_by_arm = {}
        self.metrics.passed_by_cell = {}
        for (domain, arm), count in counts.items():
            self.metrics.passed_by_domain[domain] = self.metrics.passed_by_domain.get(domain, 0) + count
            self.metrics.passed_by_arm[arm] = self.metrics.passed_by_arm.get(arm, 0) + count
            self.metrics.passed_by_cell[f"{domain}::{arm}"] = count
        atomic_yaml(
            self.paths.target_matrix,
            {
                "balance_mode": self.cfg.target_matrix.balance_mode,
                "formal_evidence_taxonomies": self.cfg.target_matrix.arms,
                "decision_domains": self.cfg.target_matrix.domains,
                "controls_are_fourth_taxonomy": False,
                "cells": matrix_status(self.cell_targets, counts)
                if self.cell_targets
                else [],
                "accepted_by_domain": self.metrics.passed_by_domain,
                "accepted_by_arm": self.metrics.passed_by_arm,
                "accepted_by_cell": self.metrics.passed_by_cell,
            },
        )

    async def run(self) -> dict:
        self._manifest()
        candidates: list[Candidate] = load_yaml_items(
            self.paths.candidates, "candidates", Candidate
        )
        validations: list[CandidateValidation] = load_yaml_items(
            self.paths.validations, "validations", CandidateValidation
        )
        contracts: list[ConstructionContract] = load_yaml_items(
            self.paths.contracts, "contracts", ConstructionContract
        )
        proposals: list[VignetteProposal] = load_yaml_items(
            self.paths.proposals, "proposals", VignetteProposal
        )
        reviews: list[ProposalReview] = load_yaml_items(
            self.paths.reviews, "reviews", ProposalReview
        )

        cand_by_id = {x.candidate_uid: x for x in candidates}
        val_by_id = {x.candidate_uid: x for x in validations}
        contract_by_id = {x.candidate_uid: x for x in contracts}
        prop_by_id = {x.candidate_uid: x for x in proposals}
        rev_by_id = {x.candidate_uid: x for x in reviews}

        def accepted_now() -> list[VignetteProposal]:
            deduped: list[VignetteProposal] = []
            for uid, rev in sorted(rev_by_id.items()):
                if not rev.overall_pass or uid not in prop_by_id:
                    continue
                proposal = prop_by_id[uid]
                if proposal.evidence_arm == "no_conflict_control":
                    continue
                if self.cfg.dedup.enabled and is_near_duplicate(
                    proposal, deduped, self.cfg.dedup.lexical_similarity_threshold
                ):
                    continue
                deduped.append(proposal)
            if self.cell_targets:
                return select_balanced(deduped, self.cell_targets, self.target_passed)
            return deduped[: self.target_passed]

        accepted = accepted_now()
        pair_keys = {
            tuple(sorted((c.baseline_source_id, c.modifier_source_id))) for c in candidates
        }
        self.metrics.candidates_unique = len(candidates)
        self.metrics.construction_contracts = len(contract_by_id)
        self.metrics.proposals_passed = len(accepted)
        self._update_matrix_artifact(accepted)
        total_records = self.corpus.count()
        next_round = self.metrics.exploration_rounds_completed

        while (
            len(accepted) < self.target_passed
            and next_round < self.cfg.exploration.max_rounds
        ):
            wave = min(
                self.cfg.exploration.round_batch_size,
                self.cfg.exploration.max_rounds - next_round,
            )
            current_counts = proposal_counts(accepted)
            target_cells = (
                choose_target_cells(self.cell_targets, current_counts, wave)
                if self.cell_targets
                else [None] * wave
            )
            offsets = [
                random.Random(
                    self.cfg.exploration.random_seed + next_round + i + 1
                ).randrange(total_records)
                for i in range(wave)
            ]
            round_specs = []
            for i, (offset, target_cell) in enumerate(zip(offsets, target_cells, strict=True)):
                domain = target_cell[0] if target_cell else None
                arm = target_cell[1] if target_cell else None
                round_specs.append(
                    (
                        f"round_{next_round + i + 1:06d}",
                        self.corpus.get_by_offset(offset).source_id,
                        domain,
                        arm,
                    )
                )
            explorer_sem = asyncio.Semaphore(self.cfg.roles["explorer"].concurrency)

            async def one_round(spec, sem=explorer_sem):
                rid, anchor, domain, arm = spec
                async with sem:
                    return await explore_round(
                        rid,
                        anchor,
                        self.corpus,
                        self.clients["explorer"],
                        self.cfg.exploration,
                        self.metrics,
                        self.paths.trajectories / f"{rid}.jsonl",
                        pair_keys,
                        target_domain=domain,
                        target_arm=arm,
                        strict_target_cell=self.cfg.target_matrix.strict_explorer_target,
                    )

            new_batches = await asyncio.gather(*(one_round(x) for x in round_specs))
            for batch in new_batches:
                for c in batch:
                    cand_by_id.setdefault(c.candidate_uid, c)
            candidates = list(cand_by_id.values())
            self.metrics.candidates_unique = len(candidates)
            atomic_yaml(self.paths.candidates, {"candidates": candidates})

            pending_validation = [
                c for c in candidates if c.candidate_uid not in val_by_id
            ]

            async def do_validate(c: Candidate):
                try:
                    v = await validate_candidate(
                        c,
                        self.corpus,
                        self.clients["validator"],
                        self.cfg.validation,
                        self.cfg.source_policy,
                    )
                    return c.candidate_uid, v, None
                except Exception as exc:
                    return c.candidate_uid, None, f"{type(exc).__name__}: {exc}"

            for uid, val, _err in await asyncio.gather(
                *(do_validate(c) for c in pending_validation)
            ):
                if val:
                    val_by_id[uid] = val
                    self.metrics.validations_completed += 1
                    if val.promote:
                        self.metrics.candidates_promoted += 1
            validations = list(val_by_id.values())
            atomic_yaml(self.paths.validations, {"validations": validations})

            for candidate in candidates:
                validation = val_by_id.get(candidate.candidate_uid)
                if not validation or not validation.promote:
                    continue
                current_contract = contract_by_id.get(candidate.candidate_uid)
                expected_contract = build_construction_contract(candidate, validation, self.corpus)
                if not current_contract or current_contract != expected_contract:
                    contract_by_id[candidate.candidate_uid] = expected_contract
            contracts = list(contract_by_id.values())
            self.metrics.construction_contracts = len(contracts)
            atomic_yaml(self.paths.contracts, {"contracts": contracts})

            pending_generation = [
                c
                for c in candidates
                if val_by_id.get(c.candidate_uid)
                and val_by_id[c.candidate_uid].promote
                and c.candidate_uid in contract_by_id
                and not (
                    rev_by_id.get(c.candidate_uid)
                    and rev_by_id[c.candidate_uid].overall_pass
                )
            ]

            async def construct(c: Candidate):
                validation = val_by_id[c.candidate_uid]
                contract = contract_by_id[c.candidate_uid]
                last_review: ProposalReview | None = None
                proposal: VignetteProposal | None = prop_by_id.get(c.candidate_uid)
                repair_instructions: list[str] = []
                start_draft = (proposal.draft_number + 1) if proposal else 1
                for draft_no in range(
                    start_draft, self.cfg.generation.max_drafts_per_candidate + 1
                ):
                    try:
                        proposal = await generate_vignette(
                            c,
                            contract,
                            self.corpus,
                            self.clients["generator"],
                            self.cfg.generation,
                            draft_no,
                            repair_instructions,
                        )
                        self.metrics.proposals_generated += 1
                        if not proposal.constructible:
                            return c.candidate_uid, contract, proposal, None
                        review = await review_proposal(
                            c,
                            validation,
                            contract,
                            proposal,
                            self.corpus,
                            self.clients["reviewer"],
                            self.cfg.source_policy,
                        )
                        self.metrics.proposal_reviews_completed += 1
                        last_review = review
                        if review.needs_candidate_revalidation:
                            reval = await validate_candidate(
                                c,
                                self.corpus,
                                self.clients["validator"],
                                self.cfg.validation,
                                self.cfg.source_policy,
                                extra_concerns=review.concerns,
                            )
                            val_by_id[c.candidate_uid] = reval
                            if not reval.promote:
                                return c.candidate_uid, contract, proposal, review
                            validation = reval
                            contract = build_construction_contract(c, reval, self.corpus)
                            contract_by_id[c.candidate_uid] = contract
                        if review.overall_pass:
                            return c.candidate_uid, contract, proposal, review
                        if not review.repairable:
                            return c.candidate_uid, contract, proposal, review
                        repair_instructions = review.repair_instructions
                        self.metrics.repairs_attempted += 1
                    except Exception:
                        continue
                return c.candidate_uid, contract, proposal, last_review

            if pending_generation:
                results = await asyncio.gather(
                    *(construct(c) for c in pending_generation)
                )
                for uid, contract, prop, rev in results:
                    contract_by_id[uid] = contract
                    if prop:
                        prop_by_id[uid] = prop
                    if rev:
                        rev_by_id[uid] = rev
                contracts = list(contract_by_id.values())
                proposals = list(prop_by_id.values())
                reviews = list(rev_by_id.values())

                accepted = accepted_now()
                dedup_rejected = set()
                dedup_reference: list[VignetteProposal] = []
                for uid, rev in sorted(rev_by_id.items()):
                    if not rev.overall_pass or uid not in prop_by_id:
                        continue
                    proposal = prop_by_id[uid]
                    if self.cfg.dedup.enabled and is_near_duplicate(
                        proposal,
                        dedup_reference,
                        self.cfg.dedup.lexical_similarity_threshold,
                    ):
                        dedup_rejected.add(uid)
                        continue
                    dedup_reference.append(proposal)
                self.metrics.construction_contracts = len(contracts)
                self.metrics.proposals_passed = len(accepted)
                self._update_matrix_artifact(accepted)
                atomic_yaml(self.paths.contracts, {"contracts": contracts})
                atomic_yaml(self.paths.proposals, {"proposals": proposals})
                atomic_yaml(
                    self.paths.reviews,
                    {
                        "reviews": reviews,
                        "dedup_rejected_candidate_uids": sorted(dedup_rejected),
                    },
                )
                write_jsonl(self.paths.passed_jsonl, accepted)

            next_round += wave
            self._persist_metrics()
            if len(accepted) >= self.target_passed:
                break

        self._update_matrix_artifact(accepted)
        self._persist_metrics()
        return {
            "run_id": self.run_id,
            "corpus_records": self.corpus.count(),
            "rounds_completed": self.metrics.exploration_rounds_completed,
            "candidates": len(cand_by_id),
            "promoted": sum(1 for x in val_by_id.values() if x.promote),
            "construction_contracts": len(contract_by_id),
            "reviewed": len(rev_by_id),
            "passed": min(len(accepted), self.target_passed),
            "target": self.target_passed,
            "output": str(self.paths.root),
            "target_reached": len(accepted) >= self.target_passed,
            "passed_by_domain": self.metrics.passed_by_domain,
            "passed_by_arm": self.metrics.passed_by_arm,
            "target_matrix": str(self.paths.target_matrix),
        }
