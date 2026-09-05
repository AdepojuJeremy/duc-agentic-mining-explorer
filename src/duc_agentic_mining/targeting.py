from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .config import TargetMatrixConfig
from .models import VignetteProposal

Cell = tuple[str, str]


def equal_cell_targets(total: int, cfg: TargetMatrixConfig) -> dict[Cell, int]:
    cells = [(domain, arm) for domain in cfg.domains for arm in cfg.arms]
    if not cells:
        return {}
    base, remainder = divmod(total, len(cells))
    return {
        cell: base + (1 if index < remainder else 0)
        for index, cell in enumerate(cells)
    }


def proposal_counts(rows: Iterable[VignetteProposal]) -> Counter[Cell]:
    counts: Counter[Cell] = Counter()
    for row in rows:
        if row.evidence_arm == "no_conflict_control":
            continue
        counts[(row.decision_domain, row.evidence_arm)] += 1
    return counts


def choose_target_cells(
    targets: dict[Cell, int],
    current: Counter[Cell],
    n: int,
) -> list[Cell | None]:
    if not targets:
        return [None] * n
    simulated = Counter(current)
    chosen: list[Cell | None] = []
    for _ in range(n):
        deficits = {
            cell: max(0, target - simulated[cell]) for cell, target in targets.items()
        }
        max_deficit = max(deficits.values(), default=0)
        if max_deficit <= 0:
            chosen.append(None)
            continue
        cell = min(
            (cell for cell, deficit in deficits.items() if deficit == max_deficit),
            key=lambda x: (x[0], x[1]),
        )
        chosen.append(cell)
        simulated[cell] += 1
    return chosen


def select_balanced(
    proposals: Iterable[VignetteProposal],
    targets: dict[Cell, int],
    total: int,
) -> list[VignetteProposal]:
    if not targets:
        return list(proposals)[:total]
    counts: Counter[Cell] = Counter()
    selected: list[VignetteProposal] = []
    for proposal in proposals:
        cell = (proposal.decision_domain, proposal.evidence_arm)
        limit = targets.get(cell)
        if limit is None or counts[cell] >= limit:
            continue
        selected.append(proposal)
        counts[cell] += 1
        if len(selected) >= total:
            break
    return selected


def matrix_status(
    targets: dict[Cell, int],
    current: Counter[Cell],
) -> list[dict[str, int | str]]:
    return [
        {
            "decision_domain": domain,
            "evidence_arm": arm,
            "target": target,
            "accepted": current[(domain, arm)],
            "remaining": max(0, target - current[(domain, arm)]),
        }
        for (domain, arm), target in sorted(targets.items())
    ]
