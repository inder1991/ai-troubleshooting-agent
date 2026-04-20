# Service Stubs — PR-K3 vs PR-K3.5

PR-K3 (this PR) ships:

- **Shared `go-common` scaffolding** — logging, OTel tracing,
  HTTP serve, Postgres pool helpers. Any service that imports
  this gets uniform structured-JSON logs, a /metrics endpoint,
  a /livez + /readyz pair, W3C trace propagation, and a graceful
  shutdown for free.
- **`api-gateway`** — complete reference implementation. Reviews
  against this one; the others follow its shape.
- **Boot-stubs** for `auth-service`, `cart-service`,
  `checkout-service`, `inventory-service`, `fraud-adapter`,
  `wallet-service`, `notification-service` — each is ~50 LOC of
  `main.go` that boots, registers `/livez`, and returns a
  placeholder 200 on its primary route. Enough to:
    - Compile the Helm chart for the whole scenario
    - Verify kubectl port-forwards reach each service
    - Let k6 hit `api-gateway` without connection errors
    - Prove the scaffolding works uniformly across all 8

PR-K3.5 (follow-up, ~1 week) replaces each stub with its real
business logic per storyboard §3 — Postgres writes, Redis reads,
downstream HTTP calls, trace-span enrichment. Each service's
handler goes from "respond 200" to "do the thing the storyboard
says."

## Why this shape

Ships a reviewable, installable PR TODAY. You see the scaffolding
once and its style decisions settle before they get repeated 7
more times. If you hate the log shape, the OTel setup, the Helm
value structure, the port-forward script, etc., we change it here
in a day — not after 8 services are built around it.
