"""
Asynchronous Google Cloud Pub/Sub Telemetry Publisher (Lazy Initialized).
Guarantees fast container cold-boot times by initializing GCP client on first request.
"""
import json
from config.settings import settings

_publisher_client = None
_topic_path = None
_pubsub_initialized = False


def _get_pubsub_client():
    """Lazily initializes Pub/Sub publisher client on first use."""
    global _publisher_client, _topic_path, _pubsub_initialized
    if not _pubsub_initialized:
        try:
            from google.cloud import pubsub_v1

            _publisher_client = pubsub_v1.PublisherClient()
            _topic_path = _publisher_client.topic_path(settings.GCP_PROJECT_ID, settings.PUBSUB_TOPIC_ID)
            _pubsub_initialized = True
        except Exception as e:
            print(f"⚠️ Pub/Sub Client initialization note: {e}. Running in local/mock mode.")
            _publisher_client = None
            _topic_path = None
            _pubsub_initialized = True
    return _publisher_client, _topic_path


def _pubsub_callback(future):
    """Non-blocking callback executed when Pub/Sub acknowledges message receipt."""
    try:
        message_id = future.result()
        if settings.DEBUG:
            print(f"✅ Telemetry published to Pub/Sub. Message ID: {message_id}")
    except Exception as e:
        print(f"❌ Failed to publish telemetry to Pub/Sub: {e}")


def publish_telemetry_async(telemetry_data: dict) -> None:
    """
    Publishes telemetry payload dictionary to Cloud Pub/Sub asynchronously.
    """
    client, topic = _get_pubsub_client()
    if not client or not topic:
        if settings.DEBUG:
            print(f"ℹ️ [Mock Telemetry Log]: {telemetry_data}")
        return

    try:
        data_bytes = json.dumps(telemetry_data).encode("utf-8")
        future = client.publish(topic, data_bytes)
        future.add_done_callback(_pubsub_callback)
    except Exception as e:
        print(f"⚠️ Pub/Sub publish execution error: {e}")
