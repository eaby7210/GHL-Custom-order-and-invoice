from django.db.models.signals import post_save
from django.dispatch import receiver, Signal

from tolt.services import ToltService



# @receiver(post_save, sender=ContactCustomFieldValue)
# def contact_created_or_updated(sender, instance :ContactCustomFieldValue, created, **kwargs):
#     """
#     Fires when a Contact is created/updated AND has a custom field
#     with field_key == 'contact.tolt_referral_id'.
#     """
#     if instance.custom_field.field_key != 'contact.tolt_referral_id':
#         return
#     print(f"Processing contact to tolt {instance.value} - {instance.contact.id} - {instance.custom_field.field_key}")
#     referral_field = instance
#     # print(f" values: {referral_field_value} {referral_field_value.value if referral_field_value else 'No value'}")
#     if referral_field and referral_field.value:
#         # referral_id = referral_field
#         ToltService.push_customer_from_contact(referral_field.contact)
#         # Emit custom signal

