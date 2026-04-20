#!/usr/bin/env sh
# Single image, two roles. The CronJob sets RECONCILE_MODE=cronjob;
# the long-running Deployment sets RECONCILE_MODE=web.
set -eu
mode="${RECONCILE_MODE:-cronjob}"
case "$mode" in
  cronjob) exec python -m reconcile.NightlyReconcile ;;
  web)     exec python -m reconcile.reconcile_web ;;
  *)       echo "bad RECONCILE_MODE=$mode (expected cronjob|web)" >&2; exit 2 ;;
esac
