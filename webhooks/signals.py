from django.dispatch import Signal, receiver
from .services import dispatch_webhook_event
import logging

logger = logging.getLogger(__name__)

# Define the custom signal
# Arguments:
# - event_name: str (e.g., 'order.created')
# - payload: dict (the data to send)
webhook_event_signal = Signal()

@receiver(webhook_event_signal)
def handle_webhook_event_signal(sender, event_name, payload, **kwargs):
    """
    Listener that triggers the actual webhook dispatch logic
    when the signal is sent.
    """
    logger.info(f"Received webhook signal: {event_name}")
    dispatch_webhook_event(event_name, payload)

