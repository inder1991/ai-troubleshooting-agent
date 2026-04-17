# Counterfactual Remediation Experiments — Design (P2)

**Status:** design + interface stub only. No runtime code wired.

## Purpose

Before a fix is applied to production, estimate "what would change" by
replaying against a staging snapshot. This is the safer sibling of
auto-remediation: no change lands in prod until a human approves, and
the approval is informed by a concrete dry-run.

## Scope

- **In scope:** replay proposed fix against a staging environment with
  the same deployed SHA; observe symptom resolution; surface the
  delta in the UI before asking for approval.
- **Out of scope:** any automatic execution against production. Even
  "low-risk" remediations (restart a pod) must go through human
  approval every time.

## Core components

1. **Staging replay harness.** Takes the last 30 minutes of traffic
   captured in staging, replays it post-fix, captures symptom curves.
2. **Blast radius estimator.** Given a proposed config/code change,
   enumerate the blast radius — which services share the changed
   dependency, which tenants, what percentile of traffic.
3. **Safety policy.** Hard-coded list of action classes that are never
   eligible for counterfactual experiment (e.g. DROP TABLE, delete PVC,
   force-close circuit breakers).

## Why P2

Everything here requires a functioning staging environment with traffic
capture + replay, which we do not have today. Shipping a stub with a
design doc lets us hold the intent without writing code that will rot
before it's wired up.

## Interface

See `backend/src/remediation/counterfactual.py`. All methods raise
`NotImplementedError` until staging capture/replay exists.
