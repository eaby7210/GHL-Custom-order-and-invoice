from celery import shared_task
from stripe_payment.management.commands.pull_notary_company import Command as pull_companies
import logging, json

logger = logging.getLogger(__name__)

@shared_task
def example_task(arg1, arg2):
    # Your task logic here
    return arg1 + arg2

@shared_task
def sample_beat_task():
    # Logic for the periodic task
    logger.info("Sample beat task executed.")
    return "Task completed"

@shared_task
def create_order_task(order_id, user_id):
    pass

@shared_task
def pull_clients():
    p =pull_companies()
    p.handle()


def process_tos_for_ghl(user_id: int, contact_id: int):
    from stripe_payment.models import NotaryUser
    from core.services import ContactServices
    from core.models import Contact
    notary_user = NotaryUser.objects.filter(id=user_id).first()
    last_tos = notary_user.signed_terms.order_by('-updated_at').first()
    if not notary_user:
        return
    contact_update_payload={
        "customFields": [
             {
                "id": "1gdlUMPAHflS6thKSC6U",
                "key": "contact.tos_signed_at",
                "field_value": notary_user.last_signed_at.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "yHPqdzxgyYR900Gaqs7l", 
                "key": "contact.signed_tos",
                "field_value": f"{last_tos.title} {last_tos.version_id if last_tos.version_id else last_tos.updated_at.strftime('%Y-%m-%d')}"
            },
        ]

    }
    contact = Contact.objects.filter(id=contact_id).first()
    if not contact:
        contact_data = ContactServices.get_contact("n7iGMwfy1T5lZZacxygj", contact_id)
        contact = ContactServices.save_contact(contact_data)
    if contact:
       response= ContactServices.push_contact(contact, contact_update_payload)
       print("updated contact with tos")
    
@shared_task
def check_duplicate_payment_method(customer_id, payment_intent_id):
    """
    Checks if the payment method used in the given PaymentIntent is a duplicate
    (same fingerprint) of an existing saved card for the customer.
    If so, it detaches the new one to prevent duplicates.
    Returns a string indicating the outcome for logging/debugging.
    """
    import stripe
    from .utils import list_payment_methods
    
    try:
        # 1. Retrieve the PaymentIntent
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        if not pi or not pi.payment_method:
            return "Skipped: No payment method on PaymentIntent"

        new_pm_object = pi.payment_method 

        # 2. Get the full PaymentMethod object
        if isinstance(new_pm_object, str):
            new_pm = stripe.PaymentMethod.retrieve(new_pm_object)
        else:
            new_pm = new_pm_object

        # 3. Validate it's a card with a fingerprint
        if not new_pm or not new_pm.card or not new_pm.card.fingerprint:
            return "Skipped: Payment method is not a card or missing fingerprint"

        new_fingerprint = new_pm.card.fingerprint
        existing_methods = list_payment_methods(customer_id)

        # 4. Check for duplicates
        for pm in existing_methods:
            # Skip comparing to itself
            if pm.id == new_pm.id:
                continue
            
            # Ensure existing method has a card fingerprint
            if not pm.card or not pm.card.fingerprint:
                continue

            if pm.card.fingerprint == new_fingerprint:
                print(f"⚠️ Duplicate payment method detected (Fingerprint: {new_fingerprint}). Detaching new one: {new_pm.id}, Keeping old one: {pm.id}")
                stripe.PaymentMethod.detach(new_pm.id)
                return f"Detached duplicate: {new_pm.id}"

        return "No duplicate found"

    except Exception as e:
        error_msg = f"⚠️ Error in duplicate payment method check task: {e}"
        print(error_msg)
        return error_msg

