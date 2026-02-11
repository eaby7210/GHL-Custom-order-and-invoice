
from .models import WebhookEndpoint, WebhookEvent
from .tasks import send_webhook
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

def dispatch_webhook_event(event_name, payload):
    """
    Dispatches the given event and payload to all subscribed endpoints.
    """
    try:
        event = WebhookEvent.objects.get(name=event_name)
    except WebhookEvent.DoesNotExist:
        logger.warning(f"Webhook event '{event_name}' does not exist.")
        return

    endpoints = WebhookEndpoint.objects.filter(events=event, is_active=True)
    
    if not endpoints.exists():
        logger.debug(f"No active endpoints found for event '{event_name}'.")
        return

    # Construct the final payload here so it's consistent for signing and logging
    final_payload = {
        "event_type": event_name,
        "created_at": timezone.now().isoformat(),
        "data": payload
    }

    for endpoint in endpoints:
        send_webhook.delay(endpoint.id, event_name, final_payload)
        logger.info(f"Queued webhook for endpoint {endpoint.id} on event {event_name}")
