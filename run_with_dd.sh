#!/bin/bash

# Check if API Key is provided
if [ -z "$1" ]; then
    echo "Usage: ./run_with_dd.sh <YOUR_DATADOG_API_KEY>"
    exit 1
fi

export DD_API_KEY=$1
export DD_SITE="datadoghq.com"
export DD_LLMOBS_ENABLED=1
export DD_LLMOBS_AGENTLESS_ENABLED=1
export DD_LLMOBS_ML_APP="ai-troubleshooting"
export DD_ENV="dev-local"
export DD_SERVICE="ai-troubleshooting-backend"

echo "Checking for ddtrace installation..."
pip install ddtrace uvicorn

echo "Launching Backend with Datadog LLM Observability..."
exec ddtrace-run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
