# Dataset axes

DUC dataset construction uses two independent formal axes.

## Decision domain

Each route belongs to one of six clinical decision domains:

1. `diagnosis`
2. `treatment_selection`
3. `triage_urgency`
4. `medication_safety`
5. `public_health_advice`
6. `patient_counselling`

The decision domain describes **what kind of clinical decision is being updated**.

## Evidence taxonomy

Each formal route belongs to one of three DUC evidence taxonomies:

1. `contradictory` — Stage 2 materially conflicts with or undermines the basis of the initial recommendation;
2. `complicating` — Stage 2 adds a clinically relevant condition, caveat, eligibility constraint, interaction, trade-off, or implementation consideration;
3. `uncertainty_inducing` — Stage 2 makes the decision less determinate and can warrant reduced confidence, broader options, information seeking, or abstention.

The evidence taxonomy describes **what the new evidence does to the decision context**. It is separate from the warranted decision update.

## Controls

No-conflict, weak-evidence, irrelevant-evidence, and framing variants can be constructed as controls. They are not a fourth evidence taxonomy and are excluded from the formal 6 × 3 target matrix unless a separate control build is requested.

## 1,200-item equal target

The formal matrix has 18 cells. An equal 1,200-item build assigns 66 or 67 accepted items to each cell, with the allocation summing exactly to 1,200.

The pipeline writes the live deficits and accepted counts to `target_matrix.yaml` during a run.
