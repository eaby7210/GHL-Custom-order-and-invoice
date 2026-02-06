from django.dispatch import receiver, Signal
from django.db.models.signals import post_save, pre_save
from stripe_payment.signals import notary_order_created
from stripe_payment.models import Order
from stripe_payment.serializer import OrderSerializer
from webhooks.services import dispatch_webhook_event
from stripe_payment.models import NotaryClientCompany, NotaryUser
from stripe_payment.serializer import NotaryClientCompanySerializer, NotaryUserSerializer
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
    dispatch_webhook_event("notary_order.creating_payload", payload)
    dispatch_webhook_event("notary_order.created_res", order_res_payload)


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
        event_name = "order.created"
    elif hasattr(instance, '_old_processing_status') and instance._old_processing_status != instance.processing_status:
        event_name = f"order.{instance.processing_status}"
    
    if event_name:
        try:
            serializer = OrderSerializer(instance)
            payload = serializer.data
            logger.info(f"Dispatching webhook {event_name} for order {instance.id}")
            dispatch_webhook_event(event_name, payload)
        except Exception as e:
            logger.error(f"Error dispatching webhook for order {instance.id}: {e}")



@receiver(post_save, sender=NotaryClientCompany)
def notary_company_post_save(sender, instance, created, **kwargs):
    event_name = "notary_client_company.created" if created else "notary_client_company.updated"
    try:
        serializer = NotaryClientCompanySerializer(instance)
        payload = serializer.data
        logger.info(f"Dispatching webhook {event_name} for company {instance.id}")
        dispatch_webhook_event(event_name, payload)
    except Exception as e:
        logger.error(f"Error dispatching webhook for company {instance.id}: {e}")

@receiver(post_save, sender=NotaryUser)
def notary_user_post_save(sender, instance, created, **kwargs):
    event_name = "notary_user.created" if created else "notary_user.updated"
    try:
        serializer = NotaryUserSerializer(instance)
        payload = serializer.data
        logger.info(f"Dispatching webhook {event_name} for user {instance.id}")
        dispatch_webhook_event(event_name, payload)
    except Exception as e:
        logger.error(f"Error dispatching webhook for user {instance.id}: {e}")
