#!/usr/bin/env bash
# Opens the four kubectl port-forwards the workflow backend needs when
# it runs on your laptop:
#
#   localhost:9200   → elasticsearch (log_agent)
#   localhost:9090   → prometheus    (metrics_agent)
#   localhost:16686  → jaeger-query  (tracing_agent)
#   (k8s_agent uses your normal kubeconfig; no forward needed)
#
# Tune the ES_NS / PROM_NS / JAEGER_NS variables to match your cluster's
# actual namespaces — the defaults below are the most common layouts.
# Run in the background; Ctrl-C kills all four.
#
# Usage:
#   ./port-forwards.sh            # default namespaces
#   ES_NS=logging PROM_NS=mon JAEGER_NS=tracing ./port-forwards.sh
set -euo pipefail

ES_NS="${ES_NS:-elk}"
ES_SVC="${ES_SVC:-elasticsearch}"

PROM_NS="${PROM_NS:-monitoring}"
PROM_SVC="${PROM_SVC:-prometheus-operated}"

JAEGER_NS="${JAEGER_NS:-observability}"
JAEGER_SVC="${JAEGER_SVC:-jaeger-query}"

pids=()
trap 'echo; echo "Stopping port-forwards…"; for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; exit 0' INT TERM

pf() {
  local ns="$1" svc="$2" local_port="$3" remote_port="$4" label="$5"
  echo "→ port-forward $label : $ns/svc/$svc -> localhost:$local_port"
  kubectl port-forward -n "$ns" "svc/$svc" "$local_port:$remote_port" \
    >/tmp/pf-"$label".log 2>&1 &
  pids+=($!)
}

pf "$ES_NS"     "$ES_SVC"     9200  9200  elasticsearch
pf "$PROM_NS"   "$PROM_SVC"   9090  9090  prometheus
pf "$JAEGER_NS" "$JAEGER_SVC" 16686 16686 jaeger-query

echo
echo "All four port-forwards running. Leaving this window open keeps them alive."
echo "Press Ctrl-C to stop."
echo
wait "${pids[@]}"
