from celery import shared_task
import logging

from django.utils import timezone

from core.services import ContactServices
from order_page.models import TypeformResponse, TypeformPartnerMapping, TypeformAnswer
from tolt.models import Link
from tolt.services import ToltService

logger = logging.getLogger(__name__)


@shared_task
def ghl_update_contact(email: str, typeform_response):
    print(f"---- [ghl_update_contact] START processing for {email} ----")
    if isinstance(typeform_response, (str, int)):
        try:
             typeform_response = TypeformResponse.objects.get(id=typeform_response)
        except TypeformResponse.DoesNotExist:
            logger.error(f"TypeformResponse with id {typeform_response} not found")
            return

    # 1. Look for existing contact in GHL
    contact_data = None
    search_response = ContactServices.search_contacts('n7iGMwfy1T5lZZacxygj', query={
            "locationId": "n7iGMwfy1T5lZZacxygj",
            "page": 1,
            "pageLimit": 20,
            "filters": [
                {
                    "field": "email",
                    "operator": "eq",
                    "value": email
                },
            ],
            "sort": [
                {
                    "field": "dateAdded",
                    "direction": "desc"
                }
            ]
        })
    print(f"[ghl_update_contact] Search response raw: {search_response}")
    if len(search_response.get("contacts", [])) > 0:
        contact_data = search_response["contacts"][0]
    
    if contact_data:
        print(f"Contact found: {contact_data.get('contactName')} - {contact_data.get('email')}")
    else:
        print(f"[ghl_update_contact] No contact found in GHL for email {email}")

    # 2. Check for Partner Mappings in the response
    # Only if contact_data exists and does NOT have the partner custom field set
    CUSTOM_FIELD_PARTNER_ID = "83SlnV9oK3J4aBnknXyD"
    CUSTOM_FIELD_KEY = "contact.tolt_referral_id"
    
    should_process = False
    if contact_data:
        existing_custom_fields = contact_data.get("customFields", []) or []
        # Check if field exists and has a value
        has_partner_value = any(
            cf.get("id") == CUSTOM_FIELD_PARTNER_ID and cf.get("value") 
            for cf in existing_custom_fields
        )
        if not has_partner_value:
             should_process = True
        else:
            print(f"Contact {email} already has Affiliate set. Skipping update.")

    if should_process:
        try:
            answers = typeform_response.answers.select_related('field').filter(
                answer_type='choice', 
                field__field_type='dropdown'
            )
            
            for answer in answers:
                print(f"[ghl_update_contact] Checking answer: {answer.id} (Field: {answer.field.title})")
                if not answer.value_json or not isinstance(answer.value_json, dict):
                    print(f"[ghl_update_contact] Answer {answer.id} has no valid value_json. Skipping.")
                    continue

                choice_data = answer.value_json
                choice_ref = choice_data.get('ref')
                choice_label = choice_data.get('label')
                
                if not choice_ref and not choice_label:
                    continue

                # Look for mapping
                mapping = None
                if choice_ref:
                    mapping = TypeformPartnerMapping.objects.filter(
                        field=answer.field,
                        choice_ref=choice_ref
                    ).first()
                
                # Fallback to label
                if not mapping and choice_label:
                     mapping = TypeformPartnerMapping.objects.filter(
                        field=answer.field,
                        choice_label=choice_label
                    ).first()

                print(f"[ghl_update_contact] Lookup result for {choice_label}/{choice_ref}: {mapping}")

                if mapping:
                    print(f"[ghl_update_contact] Found Partner Mapping for field '{answer.field.title}': "
                          f"Choice '{choice_label}' -> Partner '{mapping.partner}'")
                    
                    if mapping.partner:
                         # Found the Partner logic to apply
                         # Found the Partner logic to apply
                         print(f"Applying Partner {mapping.partner} to Contact {email}...")
                         
                         # Get latest link value
                         latest_link = Link.objects.filter(partner=mapping.partner).order_by('-created_at').first()
                         
                         if latest_link and latest_link.value:
                            print(f"Found Partner Link: {latest_link.value}")
                            
                            update_payload = {
                                "customFields": [
                                    {
                                        "id": CUSTOM_FIELD_PARTNER_ID,
                                        "key": CUSTOM_FIELD_KEY,
                                        "field_value": latest_link.value
                                    }
                                ]
                            }
                            
                            try:
                                # Use contact ID and location ID from search result
                                location_id = contact_data.get("locationId")
                                contact_id = contact_data.get("id")
                                
                                if location_id and contact_id:
                                    print(f"Updating GHL Contact {contact_id}...")
                                    ContactServices.put_contact(location_id, contact_id, update_payload)
                                    print(f"Successfully updated GHL Contact {contact_id} with Partner Link {latest_link.value}")
                                else:
                                    print(f"Missing locationId or id for contact {email}. Cannot update.")

                            except Exception as e:
                                logger.error(f"Failed to update GHL contact {email}: {e}")
                                
                         else:
                             print(f"No Link found for Partner {mapping.partner} or Link has no value.")
                        
        except Exception as e:
            logger.error(f"Error processing partner mappings in ghl_update_contact: {e}")


@shared_task
def create_tolt_customer_for_notary_user(notary_user_id: int):
    """
    Create a Tolt customer for a NotaryUser when they have a linked Partner.
    Uses NotaryUser email, name, id (as customer_id), partner_id, and lead timestamps.
    """
    from stripe_payment.models import NotaryUser

    try:
        user = NotaryUser.objects.select_related("partner").get(pk=notary_user_id)
    except NotaryUser.DoesNotExist:
        logger.warning(
            "create_tolt_customer_for_notary_user: NotaryUser %s not found",
            notary_user_id,
        )
        return

    if not user.partner_id:
        logger.info(
            "create_tolt_customer_for_notary_user: skip user %s (no partner)",
            notary_user_id,
        )
        return

    existing = ToltService.find_customer_by_email(
        user.email,
        partner_id=user.partner_id,
    )
    if existing:
        logger.info(
            "create_tolt_customer_for_notary_user: skip user %s; Tolt customer "
            "already exists (id=%s, email=%s)",
            notary_user_id,
            existing.get("id"),
            existing.get("email"),
        )
        return

    name_parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in name_parts if p).strip()
    if not name:
        name = (getattr(user, "name", None) or "").strip() or None

    now = timezone.now()
    lead_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    try:
        result = ToltService.create_customer(
            user.email,
            user.partner_id,
            name=name,
            customer_id=str(user.id),
            status="lead",
            lead_at=lead_at,
        )
    except Exception as e:
        logger.exception(
            "create_tolt_customer_for_notary_user failed for user %s: %s",
            notary_user_id,
            e,
        )
        return

    logger.info(
        "Tolt create_customer finished for NotaryUser %s: %s",
        notary_user_id,
        result,
    )


