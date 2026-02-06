from django.dispatch import receiver
from stripe_payment.signals import notary_order_created
from webhooks.services import dispatch_webhook_event
import logging

logger = logging.getLogger(__name__)

@receiver(notary_order_created)
def handle_notary_order_created(sender, notary_order, order_response, **kwargs):
    """
    Connects the stripe_payment signal to the webhooks dispatcher.
    This function lives in 'core' to keep both apps decoupled.
    """
    payload = {
        "notary_order": notary_order,
        # "order_response": order_response
    }
    logger.info("Core received notary_order_created signal, dispatching webhook.")
    dispatch_webhook_event("notary_order.created", payload)
