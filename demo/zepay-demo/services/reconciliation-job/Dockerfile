FROM python:3.12-slim AS runtime
WORKDIR /app

# Non-root user — reconciliation-job never needs root in-cluster.
RUN adduser --system --group --no-create-home zepay

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY entrypoint.sh /app/entrypoint.sh
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
USER zepay
EXPOSE 8090
ENTRYPOINT ["/app/entrypoint.sh"]
