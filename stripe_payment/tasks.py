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
    
