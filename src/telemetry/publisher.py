"""
Asynchronous Google Cloud Pub/Sub Telemetry Publisher (Hardened).
Streams event telemetry to Cloud Pub/Sub with automatic retries and exponential backoff.
"""
import json
from config.settings import settings

try:
    from google.cloud import pubsub_v1
    from google.api_core import retry

    publisher_client = pubsub_v1.PublisherClient()
    topic_path = publisher_client.topic_path(settings.GCP_PROJECT_ID, settings.PUBSUB_TOPIC_ID)
    
    # Exponential backoff retry policy for Pub/Sub publish calls
    custom_retry = retry.Retry(
        initial=0.1,
        maximum=5.0,
        multiplier=2.0,
        deadline=10.0
    )
    PUBSUB_ENABLED = True
except Exception as e:
    print(f"⚠️ Pub/Sub Client initialization note: {e}. Local offline mode active.")
    publisher_client = None
    topic_path = None
    custom_retry = None
    PUBSUB_ENABLED = False


def _pubsub_callback(future):
    """Non-blocking callback executed when Pub/Sub acknowledges message receipt."""
    try:
        message_id = future.result()
        if settings.DEBUG:
            print(f"✅ Telemetry published to Pub/Sub. Message ID: {message_id}")
    except Exception as e:
        print(f"❌ Failed to publish telemetry to Pub/Sub after retries: {e}")


def publish_telemetry_async(telemetry_data: dict) -> None:
    """
    Publishes telemetry payload dictionary to Cloud Pub/Sub asynchronously with retries.
    """
    if not PUBSUB_ENABLED or not publisher_client:
        if settings.DEBUG:
            print(f"ℹ️ [Mock Telemetry Log]: {telemetry_data}")
        return

    try:
        data_bytes = json.dumps(telemetry_data).encode("utf-8")
        future = publisher_client.publish(topic_path, data_bytes, retry=custom_retry)
        future.add_done_callback(_pubsub_callback)
    except Exception as e:
        print(f"⚠️ Pub/Sub publish execution error: {e}")