# Active-Learning Pipeline — Design (P2)

**Status:** design + interface stub only. No runtime code wired.

## Purpose

Close the loop between user-submitted feedback (Task 2.5 `/feedback` endpoint)
and the system's deterministic decision layer — agent priors (Task 2.4) and
signature pattern confidence floors (Task 4.1). The LLM is never updated
by this pipeline; we don't fine-tune.

## What gets updated

- **Agent priors** (`agent_priors.prior`): per-agent rolling accuracy, moved
  by the EMA already running in `ConfidenceCalibrator.update_prior`.
- **Signature pattern confidence floors** (`SignaturePattern.confidence_floor`):
  if a pattern fires with high confidence and the user labels the outcome
  `correct=True` N times in a row, the floor can be raised slightly (and
  vice versa). Capped at [0.50, 0.95] so a run of noisy labels can't turn
  a floor into nonsense.

## What is NEVER updated automatically

- Prompts (Task 4.23 registry pins; any change ships as a new version).
- Pattern required_signals / temporal_constraints. Changing the rule is
  always a code diff with a tested PR.
- Circuit-breaker thresholds / retry policy / budget caps.

## Cadence

Weekly batch. Reason: daily would be too noisy on small corpora; monthly
would miss short-lived regressions. The batch runs off the already-
persisted `incident_feedback` table, so the pipeline doesn't need a
separate telemetry store.

## Guardrails

1. **Dry-run first.** Each run produces a `LearningReport` that lists
   every intended update + before/after values before any writes.
2. **Manual approval** on the first 4 runs so operators can validate
   the effect. Automation kicks in after that window.
3. **Hard caps.** Priors clamp to [0.1, 0.9]; floors clamp to [0.5, 0.95].
   The same EMA smoothing from Task 2.4 applies so a single week can't
   swing a value > ~0.1.
4. **Rollback.** Every batch run persists a delta row in a new table
   (`agent_prior_updates`); reverting is a SQL replay.

## Open questions

- Should the pipeline run on successful-remediation signals too, or only
  on explicit `/feedback` labels? Answer: explicit labels only for the
  first version. Implicit signals (e.g. "incident closed without further
  investigation") are too noisy.
- Do we want a held-out validation set to detect overfitting? Yes,
  eventually — depends on the same ≥ 10 labelled incidents gate that
  unblocks the eval runner.

## Interface

See `backend/src/learning/__init__.py`. All methods raise
`NotImplementedError` until the corpus gate is met.
