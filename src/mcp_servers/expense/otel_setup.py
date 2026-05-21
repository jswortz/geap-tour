"""OpenTelemetry setup for MCP servers — exports traces to Google Cloud Observability.

Enables the topology tab in the Agent Engine console by providing trace data
that shows agent-to-MCP-server relationships.

Reference: https://docs.google.com/stackdriver/docs/instrumentation/self-hosted-mcp-servers
"""

import logging

import google.auth
import google.auth.transport.requests
import grpc
from google.auth.transport.grpc import AuthMetadataPlugin
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def setup_opentelemetry(service_name: str) -> None:
    """Configure OpenTelemetry to send traces to Google Cloud Observability."""
    credentials, project_id = google.auth.default()
    if not project_id:
        raise Exception("Could not determine Google Cloud project ID.")

    resource = Resource.create(
        attributes={
            SERVICE_NAME: service_name,
            "gcp.project_id": project_id,
        }
    )

    request = google.auth.transport.requests.Request()
    auth_metadata_plugin = AuthMetadataPlugin(credentials=credentials, request=request)
    channel_creds = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.metadata_call_credentials(auth_metadata_plugin),
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                credentials=channel_creds,
                endpoint="https://telemetry.googleapis.com:443/v1/traces",
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)
    logger.info("OpenTelemetry initialized for %s", service_name)
