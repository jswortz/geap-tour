FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastmcp>=2.0.0 \
    opentelemetry-api==1.40.0 \
    opentelemetry-sdk==1.40.0 \
    opentelemetry-exporter-otlp-proto-grpc==1.40.0 \
    google-auth>=2.52.0
COPY . .
EXPOSE 8003
CMD ["python", "-m", "server"]
