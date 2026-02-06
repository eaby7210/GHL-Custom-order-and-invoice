
import requests
import json
from celery import shared_task
from .models import WebhookEndpoint, WebhookEvent, WebhookLog
from .utils import generate_signature
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5)
def send_webhook(self, endpoint_id, event_name, payload):
    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
        event = WebhookEvent.objects.get(name=event_name)
    except (WebhookEndpoint.DoesNotExist, WebhookEvent.DoesNotExist):
        logger.warning(f"Endpoint {endpoint_id} or Event {event_name} not found.")
        return

    # Create initial pending log
    log = WebhookLog.objects.create(
        endpoint=endpoint,
        event=event,
        payload=payload,
        status='PENDING'
    )

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Event': event_name,
        'X-Hub-Signature': generate_signature(endpoint.secret, payload)
    }

    try:
        response = requests.post(
            endpoint.target_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=10
        )
        
        log.response_status = response.status_code
        log.response_body = response.text
        
        if 200 <= response.status_code < 300:
            log.status = 'SUCCESS'
            log.save()
            logger.info(f"Webhook sent to {endpoint.target_url} for event {event_name}")
        else:
            log.status = 'FAILED'
            log.error_message = f"HTTP {response.status_code}"
            log.save()
            logger.warning(f"Webhook failed for {endpoint.target_url} with status {response.status_code}")
            # Retry on non-2xx response
            raise requests.exceptions.HTTPError(f"HTTP {response.status_code}")

    except requests.exceptions.RequestException as exc:
        log.status = 'FAILED'
        log.error_message = str(exc)
        log.save()
        
        logger.error(f"Failed to send webhook to {endpoint.target_url}: {exc}")
        
        # Exponential backoff: 2s, 4s, 8s, 16s, 32s
        retry_delay = 2 ** self.request.retries
        raise self.retry(exc=exc, countdown=retry_delay)
