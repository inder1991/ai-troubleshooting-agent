# Two-stage Maven + Eclipse Temurin build, with the OpenTelemetry
# Java agent attached at runtime for automatic trace propagation.
#
# Why OTel Java agent not OTel SDK:
#   The agent auto-instruments Spring Web, JDBC, and java.net.http —
#   zero code changes needed for the spans tracing_agent walks.

FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src

# shared-finance-models first so payment-service can depend on it.
COPY shared-finance-models /src/shared-finance-models
RUN cd /src/shared-finance-models && mvn -q -B install -DskipTests

COPY payment-service /src/payment-service
WORKDIR /src/payment-service
RUN mvn -q -B package -DskipTests && \
    cp target/payment-service-*.jar /app.jar

# Fetch the OTel Java agent.
ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.6.0/opentelemetry-javaagent.jar /otel/agent.jar

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app.jar /app/app.jar
COPY --from=build /otel/agent.jar /otel/agent.jar

ENV JAVA_TOOL_OPTIONS="-javaagent:/otel/agent.jar"
ENV OTEL_SERVICE_NAME=payment-service
ENV OTEL_EXPORTER_OTLP_PROTOCOL=grpc
# Pointed at the same Jaeger collector the Go services use.
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger-collector.observability.svc.cluster.local:4317
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none
ENV OTEL_TRACES_SAMPLER=always_on
ENV OTEL_INSTRUMENTATION_LOGBACK_APPENDER_EXPERIMENTAL_LOG_ATTRIBUTES_ENABLED=true

EXPOSE 8084
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
