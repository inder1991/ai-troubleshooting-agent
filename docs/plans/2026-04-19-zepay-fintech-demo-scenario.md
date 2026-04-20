# Zepay Fintech Demo — Live-Cluster Scenario Storyboard

**Codename:** `INC-2026-0419-payment-ledger-ghost-debits`
**Audience:** CXO-tier demo, 90-second walkthrough, end-to-end live cluster.
**Status:** Storyboard — reviewable on paper before any code lands.

---

## 0. Pitch line

> **"Every team was correct. Every dashboard was green. And yet — customers were being double-charged."**

That tension is the product thesis. Everything below exists to produce it in 90 seconds, on a real Kubernetes cluster, with real telemetry, against three real bugs in three real repos.

---

## 1. The incident, told to a CXO first

### 1.1 Customer-side timeline

- **Wednesday, 2:47pm ET.** `@sarah_trades_btc` (340K followers, crypto/fintech Twitter) posts:
  > *"hey @Zepay your app just charged me $87.41 TWICE for the same dinner order. the second charge isn't even in my history. wtf"*
- **Over the next 4 hours**, 47 customers file identical complaints. Each insists they clicked "Pay" exactly once. The in-app transaction history shows one transaction. The customer's bank statement shows two debits, 15.2 seconds apart, same merchant.
- **Three of the 47** are named and render as read-only rows in the `BlastRadiusList` panel's `notable_affected_accounts`:
  - **Acme Logistics Corp** (`C-CORP-ACME-LOG-0042`) — corporate treasury, $2.1M monthly volume, Tier-1 SLA, $50K penalty clause triggered. Controller caught it in 4 minutes. RM ticket opened. Legal on the bridge call. Peer-account ARR at risk: $840K/year.
  - **Sarah Chen** (`C-CHEN-SARAH-8741`) — food blogger, 184K followers. Tweet pinned to `/r/personalfinance`. 2.3M impressions.
  - **@sarah_trades_btc** (`C-INFLUENCER-BTC-2291`) — 340K crypto followers. Quote-tweeted by `@patio11` ("this is the kind of reconciliation failure that should never happen at a licensed bank"). 47K engagements. Trending #6 in US fintech Twitter.

### 1.2 War-room timeline (before the workflow runs)

- **2:58pm.** CS routes 3rd complaint to payments-on-call (Priya). Grafana: `checkout-service` p50 190→210ms, noise. Error rate 0.04%, baseline. Priya greps payment-service for Sarah's customer_id. One transaction, one ledger write, `SUCCESS`. Priya: *"can't reproduce; escalating to finance-ops."*
- **3:11pm.** Finance-ops checks the nightly recon from 3am. Zero diffs flagged. Closed ticket: *"App is correct; customer's bank has a duplicate-processing issue."*
- **3:47pm.** Ten more complaints. Three from customers who personally confirmed with their card network that the duplicates are genuine.
- **4:02pm.** War-room bridge opens. Payments lead + Platform SRE + Finance reconciliation lead + VP Eng.
- **6:30pm (2.5 hours in).** Each team's component "looks healthy in isolation." Bridge hits the 4-hour mark with zero progress. VP considers paging the CEO's office about Twitter risk.
- **6:47pm.** Someone mutters: *"Could we just run the AI diagnostic workflow on this?"*

### 1.3 Workflow-side timeline (what the CXO watches)

- **6:48:00** — on-call opens a new session in the app:
  - `service_name: checkout-service` (where the complaints point — wrong! the bug is downstream)
  - `namespace: payments-prod`
  - `time_window: last 4h`
  - `repo_url: github.com/zepay/checkout-service`
- **Phase: `collecting_context`.** The NOW strip in the AgentsCard lights up: Log Analyzer, Metric Scanner, K8s Probe, Trace Walker all pulse.
- **6:48:11** — `log_agent` lands. The Investigator's Patient Zero banner flips from `checkout-service` → `payment-service` (repo-mismatch flag raised). First AgentFindingCard appears with `UpstreamTimeoutException` cluster, 47 occurrences, affected components include `istio-proxy`.
- **6:48:24** — `tracing_agent` lands. Replays Sarah's trace. Two `wallets.UPDATE` spans, 15.203s apart, same customer_id, different txn_ids. **The smoking gun.**
- **6:48:31** — `metrics_agent` lands. `payment_ledger_write_total{retry="true"}` is 15× the 6-week baseline. Reproduce-inline button available. **DisagreementStrip starts glowing**: "metrics ↔ tracing disagree".
- **6:48:35** — `fraud-adapter` appears red on the topology. Looks like the obvious cause — its p95 is 2.7× baseline. CXO leans in.
- **6:48:43** — `k8s_agent` lands: payment-service pods healthy, no restarts, no OOM. Clears infrastructure hypotheses.
- **6:48:58** — **The fraud-adapter false lead dies.** Cross-check math: fraud-adapter slowdown contributes 1.6% of incident latency; istio-inventory contributes 98.4%. EliminationLog surfaces H1 with explicit evidence-against. *"We considered this. It's not it."*
- **6:49:08** — `critic` challenges the winning hypothesis. One re-investigation round fires. Confidence dips to 74%, then rebounds to 92%.
- **6:49:22** — `change_agent` correlates git history: `payment-service` commit `abc123` (6 weeks ago) introduced the `@Retryable` wrapper. Bug has been silently running for 42 days.
- **6:49:31** — **Verdict lands.** Verdict block renders:
  > *"Likely cause — non-idempotent ledger retry under Istio-sidecar timeout (92% confidence). Affects 3 services; 47 customers double-charged totaling $4,089; Acme Logistics SLA penalty clause triggered ($50K + $840K peer-ARR risk)."*
- **6:49:33** — `SignatureMatchPill` renders on banner: `🔖 known pattern · retry_without_idempotency_key · 89%`. Hover expands: *"Seen in Stripe Q3-2024, Square Q1-2025."*
- **6:49:36** — `FixReadyBar` slides in: *"Fix ready — PaymentExecutor.java, line 127."* Operator clicks **Open PR**. Remediation Campaign spawns with three draft PRs.

**Total wall-clock from session-start to verdict: 91 seconds.**

---

## 2. The three bugs (as they'll exist in actual code)

### Bug #1 — Primary cause (villain, 70% airtime)

**File:** `payment-service/src/main/java/com/zepay/payment/ledger/PaymentExecutor.java:127`

```java
@Retryable(
    value = {UpstreamTimeoutException.class, HttpServerErrorException.class},
    maxAttempts = 2,
    backoff = @Backoff(delay = 200)
)
public PaymentResult execute(PaymentRequest req) {
    LedgerTxn txn = ledger.debit(req.customerId(), req.amount());  // ← re-runs on retry
    inventoryClient.reserve(req.orderId(), req.items());           // ← this is what times out at 15s
    return PaymentResult.success(txn.id());
}
```

When `inventoryClient.reserve(...)` throws `UpstreamTimeoutException` at the 15s Istio boundary, Spring re-runs the entire method — including `ledger.debit(...)` which already succeeded. The customer is debited twice.

**Fix (PR #8427 on `payment-service`):** move the mutation outside the retry boundary and make the debit idempotent via a `Idempotency-Key` header:

```java
public PaymentResult execute(PaymentRequest req) {
    LedgerTxn txn = ledger.debit(req.customerId(), req.amount(), req.idempotencyKey());
    reserveInventoryWithRetry(req.orderId(), req.items());
    return PaymentResult.success(txn.id());
}
```

### Bug #2 — Hidden amplifier (20% airtime)

**File:** `shared-finance-models/src/main/java/com/zepay/finance/Money.java:38`

```java
public class Money {
    private final double amount;   // ← IEEE-754 floating-point
    private final Currency currency;

    public Money plus(Money other) {
        return new Money(this.amount + other.amount, this.currency);  // ← drift
    }
}
```

`double` can't exactly represent decimal fractions. `$87.41 + $87.41` is `174.81999999999999` in IEEE-754. Sub-cent drift accumulates across a day of reconciliation. That drift looks exactly like the drift a duplicate charge would produce, so the real signal gets lost in the noise.

**Fix (PR #1203 on `shared-finance-models`):** switch to `BigDecimal` with explicit scale.

### Bug #3 — Signal suppressor (10% airtime)

**File:** `reconciliation-job/src/reconcile/NightlyReconcile.py:88`

```python
diff = bank_total - ledger_total
if abs(diff) < 0.02:
    log.info(f"reconciled within tolerance: diff={diff}")
    continue        # ← silently swallows
if abs(diff) < 1.00:
    log.warning(f"minor drift detected: diff={diff}; auto-adjusting")
    adjust_drift(diff)
    continue        # ← silently auto-corrects
alert_finance_oncall(diff)
```

The `$0.02` threshold was added 3 years ago to absorb Bug #2's floating-point drift. Now it swallows duplicate-charge signals because those signals look identical to floating-point drift.

**Fix (PR #294 on `reconciliation-job`):** lower threshold to `$0.001`, escalate sub-cent diffs as P3 alerts.

### The lethal combination

- **#1 alone** → reconciliation catches it next morning, engineering fixes it in a week. Single-page postmortem.
- **#2 alone** → annoying but harmless sub-cent drift.
- **#3 alone** → sloppy alerting.
- **#1+#2+#3** → duplicate charges disappear into floating-point noise that reconciliation auto-hides. Undetectable except by customer Twitter posts.

---

## 3. Service topology (9 microservices)

```
k6 traffic (ingress)
  │
  ▼
api-gateway       (Go)     healthy · routing only
  │
  ├─ auth-service (Go)     healthy · JWT validation, 8ms span
  │
  └─ cart-service (Go)     healthy · Redis cart state
        │
        ▼
  checkout-service (Go)    INNOCENT — but where PagerDuty points
        │
        ▼
  payment-service  (Java)  ← PRIMARY ROOT CAUSE (Bug #1)
        │
        ├─ fraud-adapter    (Go)   DECOY — 2.7× spike, eliminated by critic
        │
        ├─ inventory-service (Go)  Istio timeout target (15s)
        │                          (fault-injection attached here)
        │
        ├─ wallet-service   (Go)   evidence surface — ledger table lives here
        │
        └─ notification-service (Go)  healthy · emails, trailing span
```

### Per-service spec

| # | Service | Language | Port | DB/State | Trace-role | Notes |
|---|---|---|---|---|---|---|
| 1 | `api-gateway` | Go | 8080 | — | Entry span for all traces | Exposed via Ingress |
| 2 | `auth-service` | Go | 8081 | Postgres `auth` schema | Trivial JWT span | JWT verify only |
| 3 | `cart-service` | Go | 8082 | Redis | `GET /cart/{customer_id}` span | Reads cart to pass to checkout |
| 4 | `checkout-service` | Go | 8083 | — | Orchestrates `/pay` | Patient-zero-by-perception |
| 5 | `payment-service` | Java | 8084 | Postgres `ledger` schema | **Where the retry happens** | **Primary cause** |
| 6 | `fraud-adapter` | Go | 8085 | — | 2.7× latency spike during incident | Decoy false lead |
| 7 | `inventory-service` | Go | 8086 | Postgres `inventory` schema | 15s Istio fault-injected | Timing source |
| 8 | `wallet-service` | Go | 8087 | Postgres `wallet` schema | Target of `wallets.UPDATE` | **Evidence surface (double-debit)** |
| 9 | `notification-service` | Go | 8088 | Postgres `notif` schema | Trailing confirmation email | Healthy background noise |

### Per-service API contract (abbreviated; full spec in PR-K2)

```
POST /checkout                       (api-gateway → checkout-service)
  headers: Authorization: Bearer <jwt>
           Idempotency-Key: <uuid>    ← absent in pre-fix calls; present post-fix
  body:    {customer_id, cart_id, amount_cents, currency}
  response: 200 {txn_id, status: "SUCCESS"}    |  5xx {error_code}

POST /v1/ledger/debit                (checkout-service → payment-service → wallet-service)
  headers: Idempotency-Key: <uuid>
  body:    {customer_id, amount, currency}
  response: 200 {txn_id}    |  409 {existing_txn_id}  (post-fix)

POST /v1/inventory/reserve           (payment-service → inventory-service)
  headers: Idempotency-Key: <uuid>
  body:    {order_id, items: [...]}
  response: 200 {reserved_at}    |  504 (via Istio fault-injection: 20% of calls, 15s delay)

POST /v1/fraud/score                 (payment-service → fraud-adapter)
  response: 200 {risk_score, decision}    (380ms p95 during incident, 140ms baseline)
```

---

## 4. Fault injection (Istio VirtualService)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: inventory-timeout-fault
  namespace: payments-prod
spec:
  hosts: [inventory-service]
  http:
  - match: [{uri: {prefix: /v1/inventory/reserve}}]
    fault:
      delay:
        percentage: {value: 20.0}    # 20% of requests
        fixedDelay: 15s              # exactly the timeout boundary
    route:
    - destination: {host: inventory-service, port: {number: 8086}}
```

This is the single config that makes the scenario reproducible. Enabled by the demo-controller when a scenario starts; disabled when reset.

---

## 5. Demo-controller API (FastAPI, runs on laptop alongside workflow backend)

```
POST /demo/healthcheck
  Verifies kubectl port-forwards alive for ES:9200, Prom:9090, Jaeger:16686, K8s.
  Response: {ok: bool, checks: {es: ok, prom: ok, jaeger: ok, k8s: ok}}

POST /demo/reset
  Truncates ledger/wallet/inventory Postgres rows; clears Redis carts;
  disables Istio fault; stops traffic; restores baseline. ~8s.

POST /demo/start-traffic?rps=50
  k6 job — POST /checkout from 500 seeded customers at 50 RPS against Ingress.

POST /demo/inject-fault
  kubectl apply -f inventory-timeout-fault.yaml    (the VS above)
  Returns: {fault_active: true, affects: "20% of /v1/inventory/reserve"}

POST /demo/trigger-incident
  Deterministic race-trigger:
  1. Picks 3 seeded customers (Acme, Sarah Chen, @sarah_trades_btc) + 44 random.
  2. For each: calls /checkout with Idempotency-Key intentionally missing.
  3. Injects a concurrent /wallet/topup for the same customer at t+10s to pass
     the balance-check for the retry's second debit.
  4. Waits 15s; fault fires; @Retryable re-issues; double debit lands.
  Response: {txn_ids: [...47 ids], expected_verdict_s: 90}

POST /demo/spike?rps=500
  Temporarily bumps k6 RPS to 500 for 60s.

POST /demo/historical-seed
  Seeds prior incident INC-2026-0211-checkout-cart-sync-drift
  (resolved 2026-02-12, 4h, cart-service + Redis) into the workflow backend
  archive via /api/v4/demo/seed (gated behind DEMO_MODE=on).

GET /demo/state
  Returns current demo state (traffic on?, fault on?, last trigger ts,
  current incident id if any).
```

## 6. Demo operator page (one HTML file)

Static asset served by demo-controller at `http://localhost:7777/`. Layout:

```
┌ Zepay Demo Control ─────────────────────────────────┐
│                                                      │
│ Cluster health                                       │
│  ● ES     ● Prom    ● Jaeger    ● K8s                │
│                                                      │
│ Scenario state                                       │
│  Traffic: off    Fault: off    Incident: —           │
│                                                      │
│ [ Reset ] [ Start Traffic ] [ Inject Fault ]         │
│ [ Trigger Incident ] [ Spike RPS ] [ Seed History ]  │
│                                                      │
│ Last trigger → Verdict at 00:01:31 (expected ~01:30) │
│                                                      │
│ Open: War Room  |  Jaeger  |  Grafana  |  Kibana     │
└──────────────────────────────────────────────────────┘
```

---

## 7. Workflow-backend data expectations

What each of the 4 agents expects to find in ELK/Prom/Jaeger/K8s for the scenario to land the designed verdict.

### 7.1 log_agent (queries Elasticsearch)

Services emit structured JSON to stdout. Log shape (example from `payment-service`):

```json
{"ts":"2026-04-19T18:47:18.024Z","service":"payment-service","level":"INFO","msg":"RetryAttempt=2 for inventory-reserve","txn_id":"T-abc-001","retry_cause":"UpstreamTimeoutException","customer_id":"C-CHEN-SARAH-8741"}
```

Cluster expectations:
- `UpstreamTimeoutException` cluster: frequency 47, payload includes `RetryAttempt=2` keyword → drives the primary hypothesis.
- `FraudScoreProviderSlowdown` warning cluster: frequency ~200 → drives the decoy hypothesis.
- No ERROR-level logs on `payment-service` (intentional — retries succeed).

### 7.2 metrics_agent (queries Prometheus)

Metrics emitted by each service via Micrometer (Java) or `prometheus/client_golang` (Go):

- `payment_ledger_write_total{retry, namespace}` — counter, retry label "true" or "false"
- `istio_request_duration_seconds_bucket{destination_service, source_service, namespace}` — Istio-native
- `checkout_payment_latency_seconds_bucket{namespace}` — histogram
- `wallet_balance_changes_total{customer_id}` — counter (cardinality-bounded via sampling)
- `reconciliation_drift_dollars` — gauge (scraped from the CronJob's last-run ConfigMap)

Baseline expectations:
- `payment_ledger_write_total{retry="true"}`: 0.02/sec baseline → 0.31/sec during incident (15×)
- `istio_request_duration_seconds` p99 for `inventory-service`: 140ms baseline → 15.003s during incident
- `checkout_payment_latency_seconds` p95: 1.8s → 15.2s

### 7.3 tracing_agent (queries Jaeger)

Every service propagates W3C trace context. Critical span pattern:

```
trace_id: T-sarah-1234-...
  span: api-gateway.POST /checkout           duration=15253ms
    span: checkout-service.POST /pay         duration=15241ms
      span: payment-service.execute          duration=15231ms
        span: wallets.UPDATE customer=Sarah  duration=6ms   ← T1 (ghost debit)
        span: fraud-adapter.score            duration=380ms (decoy spike)
        span: istio-proxy.CONNECT inventory  duration=15003ms STATUS=504
        span: @Retry.reissue                 duration=220ms
          span: wallets.UPDATE customer=Sarah duration=5ms   ← T2 (visible debit)
          span: inventory-service.reserve    duration=207ms
```

`tracing_agent` must be able to identify `pattern_findings_from_traces`:
`double_wallets_update_same_customer_different_txn_id`, observed in 47 of 47 traces.

### 7.4 k8s_agent (queries K8s API via kubeconfig)

Expected state:
- All 9 service Deployments: `available_replicas == desired_replicas`, restart count 0.
- All pods: no OOMKilled, no ImagePullBackOff, no CrashLoopBackOff.
- Istio sidecar on `inventory-service`: healthy, one `upstream_cx_overflow` metric elevated (for the metric layer).
- Recent Events: no deployments in last 24h (enables `change_agent` to say "this has been live 6 weeks").

---

## 8. Pre-baked Remediation Campaign (3 PRs)

When operator clicks **Open PR**, the `RemediationCampaign` card surfaces these, with real diffs loaded through the existing generateFix endpoint:

### PR #8427 — `zepay/payment-service` (must_fix_to_resolve_incident)
- Files: `PaymentExecutor.java`, `LedgerClient.java`
- Changes: idempotency-key threading; move mutation outside `@Retryable`; integration test for retry-safety
- +31 / -8 lines · CI-green-predicted

### PR #1203 — `zepay/shared-finance-models` (must_fix_to_prevent_recurrence)
- Files: `Money.java`, `MoneyTest.java`, `package-info.java`
- Changes: `double` → `BigDecimal` with currency-scale; deprecate `.plus()` variant; 14 downstream services' tests pass against bumped version
- +47 / -22 lines · BREAKING CHANGE semver

### PR #294 — `zepay/reconciliation-job` (must_fix_to_prevent_recurrence)
- Files: `NightlyReconcile.py`
- Changes: threshold $0.02 → $0.001; sub-cent diffs escalate as P3; replay of 90 days of recon shows zero false positives
- +19 / -5 lines · config-only

UI groups these: **[1 PR to stop the bleeding] + [2 PRs to close the blind spot]**.

---

## 9. Operator script (verbatim, 90 seconds)

```
[SETUP — before CXO enters the room]
1. kubectl port-forward -n elk svc/elasticsearch 9200:9200 &
2. kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
3. kubectl port-forward -n observability svc/jaeger-query 16686:16686 &
4. cd demo && ./start-demo-controller.sh       # FastAPI on :7777
5. Open operator page → click Reset → click Start Traffic → click Seed History
6. Open War Room app in a second browser tab, ready but blank.

[CXO ENTERS. BEGIN.]

OPERATOR (0s):
  "Last Wednesday we had 47 customers double-charged. War-room ran 4 hours
   with no resolution. Let me show you what happens when the AI workflow
   picks up the same incident from scratch."

  [CLICK] operator page → Inject Fault
  [CLICK] operator page → Trigger Incident

  "The traffic generator is driving 50 transactions per second right now.
   I just injected the same Istio timeout that caused Wednesday's incident
   and triggered the same concurrent-top-up race for 47 customers. Double-
   charges are landing in Postgres as we speak. Zepay's dashboards still
   show green — error rate is 0.04%, success ratio is 99.97%. No alarm bells.

   Now I'll start the investigation the way on-call did."

  [SWITCH TO WAR ROOM TAB]
  [CLICK] new session → service=checkout-service (WRONG service, matching
                         what on-call assumed), namespace=payments-prod, 4h window.

OPERATOR (20s):
  "Watch the Patient Zero banner. Our on-call said checkout is broken.
   Log Agent just reframed it — Patient Zero is payment-service, not
   checkout. This is the moment a traditional war-room saves 30 minutes.

   Look at the topology — fraud-adapter just went red. Any senior SRE
   would chase that first. Watch what the workflow does."

OPERATOR (45s):
  "Fraud-adapter eliminated. The EliminationLog in the Navigator shows
   why — its latency spike accounts for 1.6% of total incident latency.
   The real villain is the Istio 15-second timeout on inventory-reserve.

   Tracing Agent found something no human grepped for — every customer
   complaint has TWO wallet-update spans per transaction. Fifteen seconds
   apart. Same customer, different txn IDs. That's the double-debit,
   caught red-handed.

   Look at the DisagreementStrip — our own metrics and tracing contradict
   each other. Metrics say '1 successful transaction.' Traces say '2 wallet
   writes.' The contradiction is the proof."

OPERATOR (75s):
  "Verdict. Non-idempotent retry under Istio-sidecar timeout, 92% confidence.
   Signature match — this exact pattern appeared in Stripe's Q3-2024
   postmortem and Square's Q1-2025 postmortem. 47 customers affected;
   Acme Logistics alone just triggered a $50,000 SLA penalty clause.

   Fix is ready. Three repos. One PR to stop the bleeding; two to close
   the blind spot. Real diffs, review-ready."

  [CLICK] Open PR

OPERATOR (90s):
  "Ninety seconds from session-start to review-ready fix. Wednesday's
   version of this same incident took us four hours, six teams, and
   didn't even reach a verdict. That's the product."

[PAUSE. LET CXO ASK FIRST QUESTION.]
```

---

## 10. Cluster prerequisites (already present in your cluster)

- Istio (for sidecar + fault-injection VirtualService)
- ELK (Elasticsearch for log_agent queries; Filebeat/Fluent Bit wired to pick up pod stdout)
- Prometheus (scraping `/metrics` on each service)
- Jaeger (trace collection from Istio)
- Kubernetes 1.28+ (for standard features)

## 11. Cluster additions (we'll stand these up in PR-K2)

- **Namespace:** `payments-prod` (scenario namespace) + `demo-ctrl` (demo-controller + k6)
- **Postgres:** single instance, 4 schemas (wallet, ledger, inventory, cart) — Helm chart standard
- **Redis:** single instance — Helm chart standard
- **RBAC:** ServiceAccount for workflow backend's K8s queries (read-only on payments-prod)
- **Istio config:** `PeerAuthentication STRICT`, `Gateway` for k6 ingress, `VirtualService` for fault-injection (applied on demand by demo-controller, not baseline)
- **Prometheus ServiceMonitor** CRDs for each of the 9 services
- **kubectl port-forward script** for the operator (4 endpoints)

## 12. Resource envelope

| Component | Replicas | CPU req | Mem req |
|---|---|---|---|
| 8 Go services × avg | 2 each | 100m | 128Mi |
| payment-service (Java) | 2 | 500m | 512Mi |
| Postgres | 1 | 250m | 512Mi |
| Redis | 1 | 100m | 128Mi |
| reconciliation-job (cron) | 0 (cron) | 500m | 512Mi (when running) |
| k6 | 2 | 500m | 256Mi |
| demo-controller | 0 (laptop) | — | — |
| **Total cluster** | | **~4.8 cores** | **~5.2 GiB** |

Fits comfortably on any dev laptop with 8+ cores / 16+ GiB — you said no constraint, so we take the simplest config.

## 13. PR roadmap (this doc is PR-K1)

- **PR-K1 ← this doc.** Storyboard only.
- **PR-K2** — Infra: namespaces, Postgres schemas, Redis, Istio configs, Prometheus SMs, RBAC, Helm umbrella, port-forward script, healthcheck. **1 week.**
- **PR-K3** — Six Go services (api-gateway, auth, cart, checkout, inventory, fraud-adapter, wallet, notification) — plain happy-path, structured logging, /metrics, OTel. **1.5 weeks.**
- **PR-K4** — Java `payment-service` Spring Boot + `shared-finance-models` jar. With real Bug #1 and Bug #2 in code. **1 week.**
- **PR-K5** — Python `reconciliation-job` CronJob with Bug #3 + `/demo/run-now` trigger. **3 days.**
- **PR-K6** — k6 traffic generator + demo-controller FastAPI + operator HTML page. **5 days.**
- **PR-K7** — E2E integration test (assert workflow backend hits verdict < 120s against live cluster) + operator README. **3 days.**

**Live-cluster demo grand total: ~6 weeks.**

**Backup fixture-demo (parallel):**
- **PR-K1-fix** — Fixture-mode storyboard + seeder endpoint contract.
- **PR-K2-fix** — Fixtures + fixture-mode operator README.
~1 week of time, spread across the 6 weeks.

## 14. Explicit non-goals for this demo

- ❌ No Ignored Signals panel (our workflow doesn't integrate with Grafana/Alertmanager/PagerDuty config-read today; we'd be faking it). The "you had the signal" beat lives in operator voice-over only.
- ❌ No Acme drill-down side-panel (out of scope, would require new UI).
- ❌ No Kafka / event-sourcing in `wallet-service` (simplification to keep narrative tight).
- ❌ No real fraud-scoring vendor integration. `fraud-adapter` is a stub that fakes a 140ms / 380ms response based on a fault flag.
- ❌ No PagerDuty / Opsgenie / Slack integration anywhere.

## 15. Pitch line (repeat on slide)

> **"Every team was correct. Every dashboard was green. And yet — customers were being double-charged."**

The storyboard above is the engine that earns that line.
