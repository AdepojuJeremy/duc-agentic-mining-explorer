from collections import Counter

from duc_agentic_mining.config import TargetMatrixConfig
from duc_agentic_mining.targeting import choose_target_cells, equal_cell_targets


def test_1200_equal_matrix_has_18_cells_and_exact_total():
    cfg = TargetMatrixConfig()
    targets = equal_cell_targets(1200, cfg)
    assert len(targets) == 18
    assert sum(targets.values()) == 1200
    assert set(targets.values()) == {66, 67}


def test_target_picker_prioritizes_largest_deficit():
    cfg = TargetMatrixConfig(
        domains=["diagnosis", "medication_safety"],
        arms=["contradictory", "complicating"],
    )
    targets = equal_cell_targets(8, cfg)
    current = Counter({("diagnosis", "contradictory"): 2})
    picked = choose_target_cells(targets, current, 3)
    assert ("diagnosis", "contradictory") not in picked
