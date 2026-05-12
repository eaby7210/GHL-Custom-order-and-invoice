from django.dispatch import receiver, Signal
from django.db.models.signals import post_save, pre_save
from stripe_payment.signals import notary_order_created
from stripe_payment.models import Order
from stripe_payment.serializer import OrderSerializer
from webhooks.services import dispatch_webhook_event
from stripe_payment.models import NotaryClientCompany, NotaryUser
from stripe_payment.serializer import NotaryClientCompanySerializer, NotaryUserSerializer
from webhooks.constants import WebhookEventKeys
import logging

logger = logging.getLogger(__name__)

@receiver(notary_order_created)
def handle_notary_order_created(sender, notary_order, order_response, **kwargs):
    """
    Connects the stripe_payment signal to the webhooks dispatcher.
    This function lives in 'core' to keep both apps decoupled.
    """
    payload = {
         **notary_order,
        # "order_response": order_response
    }
    order_res_payload ={
        **order_response,
    }
    logger.info("Core received notary_order_created signal, dispatching webhook.")
    # dispatch_webhook_event(WebhookEventKeys.NOTARY_ORDER_CREATED, payload)
    dispatch_webhook_event(WebhookEventKeys.NOTARY_ORDER_CREATED, order_res_payload)


@receiver(pre_save, sender=Order)
def order_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            instance._old_processing_status = old_instance.processing_status
        except Order.DoesNotExist:
            instance._old_processing_status = None
    else:
        instance._old_processing_status = None

@receiver(post_save, sender=Order)
def order_post_save(sender, instance, created, **kwargs):
    event_name = None
    if created:
        event_name = WebhookEventKeys.ORDER_CREATED
        print(f"SIGNAL:Order created")
    elif hasattr(instance, '_old_processing_status') and instance._old_processing_status != instance.processing_status:
        print(f"SIGNAL:Order status changed from {instance._old_processing_status} to {instance.processing_status}")
        event_name = WebhookEventKeys.get_order_event(instance.processing_status)
    else:
        # Status didn't change. This is normal when updating other fields.
        print(f"SIGNAL: no change {instance.processing_status} and {instance._old_processing_status}")
        logger.debug(f"Order saved without status change. Status: {instance.processing_status}")
    
    if event_name:
        try:
            print(f"")
            serializer = OrderSerializer(instance)
            payload = serializer.data
            logger.info(f"Dispatching webhook {event_name} for order {instance.id}")
            dispatch_webhook_event(event_name, payload)
        except Exception as e:
            logger.error(f"Error dispatching webhook for order {instance.id}: {e}")

    # ── V2 Supabase sync: send completed non-external orders ──
    if (
        not created
        and instance.processing_status == "completed"
        and not getattr(instance, "is_external_odr", False)
    ):
        try:
            from stripe_payment.serializer import SupabaseOrderSerializer
            v2_serializer = SupabaseOrderSerializer(instance)
            v2_payload = v2_serializer.data
            logger.info(f"Dispatching V2 sync webhook for order {instance.id}")
            dispatch_webhook_event(WebhookEventKeys.ORDER_COMPLETED_V2_SYNC, v2_payload)
        except Exception as e:
            logger.error(f"Error dispatching V2 sync webhook for order {instance.id}: {e}")



@receiver(post_save, sender=NotaryClientCompany)
def notary_company_post_save(sender, instance, created, **kwargs):
    event_name = WebhookEventKeys.NOTARY_CLIENT_COMPANY_CREATED if created else WebhookEventKeys.NOTARY_CLIENT_COMPANY_UPDATED
    try:
        serializer = NotaryClientCompanySerializer(instance)
        payload = serializer.data
        logger.info(f"Dispatching webhook {event_name} for company {instance.id}")
        dispatch_webhook_event(event_name, payload)
    except Exception as e:
        logger.error(f"Error dispatching webhook for company {instance.id}: {e}")

@receiver(post_save, sender=NotaryUser)
def notary_user_post_save(sender, instance, created, **kwargs):
    event_name = WebhookEventKeys.NOTARY_USER_CREATED if created else WebhookEventKeys.NOTARY_USER_UPDATED
    try:
        serializer = NotaryUserSerializer(instance)
        payload = serializer.data
        logger.info(f"Dispatching webhook {event_name} for user {instance.id}")
        dispatch_webhook_event(event_name, payload)
    except Exception as e:
        logger.error(f"Error dispatching webhook for user {instance.id}: {e}")
