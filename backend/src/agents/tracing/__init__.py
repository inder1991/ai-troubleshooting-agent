"""TracingAgent v1 — production-ready distributed-tracing diagnostic agent.

Packages:
  backends/    Pluggable TraceBackend protocol + Jaeger/Tempo implementations
  envoy_flags  Deterministic Envoy response.flags matcher (zero-LLM path)
  summarizer   Deterministic span subset + bucketing (prompt-budget control)
  ranker       Top-N candidate selection during trace mining
  redactor     PII/credential redaction for span tags
  tier_selector  Tier 0 / 1 / 2 model-cost cascade routing
  elk_reconstructor  Log-based trace reconstruction fallback

Design locked via head-of-architecture review. See docs/plans/ for decisions.
"""
