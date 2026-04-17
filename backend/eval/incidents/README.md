# Incident Label Corpus

This folder is the **regression corpus** for the diagnostic eval harness (built in Phase 4, Tasks 4.6–4.7). Each `.yaml` file describes one real past incident: the symptoms we saw, the inputs to replay, and the **correct diagnosis** the system should arrive at. The harness loads every `*.yaml` here (skipping files that start with `_`) and replays each one through the diagnostic workflow, scoring whether the produced root cause matches the labelled one.

## Acceptance gate

**Phase 4 cannot start until at least 10 labelled incidents live in this folder.** Aim for 10–20 in Week 1, drawn from real past incidents you remember well enough to label confidently.

## How to label one incident (5 minutes)

1. Pick a past incident you remember the resolution of.
2. Copy the template:
   ```bash
   cp _template.yaml 2026-04-12-checkout-cert-expiry.yaml
   ```
3. Fill in the fields (see "Field reference" below). Leave `notes` for anything that didn't fit.
4. Commit it.

That's it. There is no validator — the harness will surface schema mistakes when it loads the file. Don't over-think evidence wording; aim for substrings that *must* appear somewhere in the agent's findings.

## File naming

`YYYY-MM-DD-<short-slug>.yaml` — e.g. `2025-12-15-payment-oom.yaml`. The date is the incident date (not today). Underscore-prefixed files (`_template.yaml`, `_anything.yaml`) are skipped by the loader, so use that prefix for non-incident scaffolding.

## Field reference

Top-level fields (all required unless noted):

- **`schema_version`** — Always `1`. Matches the convention from Task 0.3; eval files are persisted artifacts, so future migrations key off this.
- **`incident_id`** — Unique slug, usually the same as the filename without `.yaml`.
- **`title`** — One-line human-readable summary.
- **`incident_window.start` / `.end`** — ISO 8601 UTC timestamps bracketing the incident.
- **`context.cluster` / `.namespace` / `.service`** — Where it happened.
- **`context.symptom_summary`** — One sentence on what users/dashboards saw.
- **`inputs_for_replay.prom_url`** — Path to a recorded Prometheus snapshot, or a live URL if reproducible.
- **`inputs_for_replay.elk_url`** — Same for logs.
- **`inputs_for_replay.k8s_snapshot`** — Path to a tarball of `kubectl get/describe` output captured during the incident (under `eval/snapshots/`).
- **`inputs_for_replay.starting_signals`** — The alerts/pages that kicked things off. The harness feeds these to the workflow as the initial trigger.
- **`labels.root_cause.category`** — One of the enum values below.
- **`labels.root_cause.summary`** — One-sentence description of the actual root cause.
- **`labels.root_cause.evidence_must_include`** — List of substrings that the agent's findings must contain to be scored as having found the right evidence. Keep these specific and grep-able.
- **`labels.cascading_symptoms`** — Symptoms that were *downstream* of the root cause. The agent should identify these as cascades, not as the cause.
- **`labels.acceptable_alternates`** — Other root causes that would also be considered correct (often empty). Use when two framings are both defensible.
- **`labels.hard_negative_hypotheses`** — Diagnoses that should *not* win. Useful when the symptom pattern superficially looks like something else; a good agent won't fall for it.
- **`notes`** — Free text for the labeller.

## `category` enum

Pick the closest one. When in doubt, `other` plus a clear `summary` is fine.

- **`memory`** — OOM, leak, GC thrash, page-cache pressure, swap.
- **`cpu`** — Saturation, runaway thread, hot loop, throttling.
- **`network`** — Partitions, DNS failure, packet loss, LB/proxy misroute, connection-pool exhaustion.
- **`deploy`** — A change that shipped — bad code, bad config, bad image — directly caused the incident.
- **`config`** — Misconfiguration that wasn't tied to a specific deploy (e.g. wrong feature flag, stale env var).
- **`dep`** — Upstream/downstream dependency outage (DB, cache, third-party API, internal service).
- **`cert`** — TLS expiry, mTLS rotation failure, CA chain issues.
- **`quota`** — Hitting a rate limit, namespace quota, cloud-provider limit.
- **`other`** — Anything that doesn't fit cleanly. Explain in `summary`.

## Worked example

Suppose checkout started 502-ing because the certificate on the upstream payments service expired:

```yaml
labels:
  root_cause:
    category: "cert"
    summary: "Payments mTLS cert expired; checkout couldn't reach payments and 502'd."
    evidence_must_include:
      - "x509: certificate has expired"
      - "payments-api"
      - "expired"
  cascading_symptoms:
    - "checkout 502 spike"
    - "cart-abandon-rate spike"
  acceptable_alternates:
    - "Cert rotation job failed (root cause one layer deeper, but same fix)."
  hard_negative_hypotheses:
    - "Payments service crash"
    - "Checkout deploy regression"
```

Notice:
- `evidence_must_include` uses **specific, searchable substrings** — the harness greps these against the agent's findings.
- `hard_negative_hypotheses` lists the *plausible-but-wrong* diagnoses. A 502 spike does look like an upstream crash; we want to verify the agent doesn't stop there.
- `acceptable_alternates` covers the case where "the rotation job failed" is technically the deeper cause; either framing should pass.
