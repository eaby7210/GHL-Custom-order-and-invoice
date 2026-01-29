
import os
import django
import sys
from unittest.mock import patch, MagicMock

# Setup Django Environment
sys.path.append('/home/eaby/Projects/dj_investorbootz')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

from order_page.models import TypeformResponse, TypeformAnswer, TypeformField, TypeformPartnerMapping, TypeformForm
from order_page.tasks import ghl_update_contact
from tolt.models import Partner
import uuid

def verify_strict_logic():
    print("--- Verifying Strict Logic ---")
    
    # 1. Setup Data
    form = TypeformForm.objects.create(form_id=f"strict_{uuid.uuid4().hex[:6]}", title="Strict Form")
    field = TypeformField.objects.create(form=form, field_id="f_drop", field_type="dropdown", title="Partner Dropdown")
    wrong_field = TypeformField.objects.create(form=form, field_id="f_text", field_type="short_text", title="Wrong Field")
    
    partner, _ = Partner.objects.get_or_create(id="p_strict", defaults={"email":"strict@test.com", "first_name": "Strict"})
    
    # Mock TypeformService to prevent API calls
    with patch('order_page.services.TypeformService') as MockService:
         MockService.return_value.get_form.return_value = {} # behave nicely if called
         MockService.return_value.update_form.return_value = {}
         
         mapping = TypeformPartnerMapping.objects.create(
            form=form, field=field, choice_ref="ref_valid",choice_label="Valid Choice", partner=partner
        )
    
    response = TypeformResponse.objects.create(
        event_id=f"evt_{uuid.uuid4().hex}", form=form, token=f"tok_{uuid.uuid4().hex}", landed_at="2023-01-01T00:00:00Z", submitted_at="2023-01-01T00:00:00Z"
    )
    
    # Valid Answer (dropdown + choice)
    TypeformAnswer.objects.create(
        response=response, field=field, answer_type="choice", 
        value_json={"ref": "ref_valid", "label": "Valid Choice"}
    )
    
    # Invalid Answer (wrong type)
    TypeformAnswer.objects.create(
        response=response, field=field, answer_type="text", # logic filters for 'choice'
        value_text="Some text"
    )
    
    # Invalid Answer (wrong field type)
    TypeformAnswer.objects.create(
        response=response, field=wrong_field, answer_type="choice", # field is short_text
        value_json={"ref": "ref_valid", "label": "Valid Choice"}
    )


    # Create Link for Partner
    from tolt.models import Link
    # Mock Link timestamp to ensure ordering works if needed, or just create one
    Link.objects.create(id="l_1", partner=partner, value="ref_123", created_at="2023-01-01T00:00:00Z")

    # 2. Test Case 1: Contact Found, No Custom Field -> Should Process and Call put_contact
    print("\nTest 1: Contact Found, Missing Custom Field (Should Update)")
    mock_contact_data = {
        "id": "contact_123",
        "locationId": "loc_123",
        "contactName": "Test User",
        "email": "test@example.com",
        "customFields": []
    }
    
    with patch('order_page.tasks.ContactServices.search_contacts') as mock_search, \
         patch('order_page.tasks.ContactServices.put_contact') as mock_put:
        
        mock_search.return_value = {"contacts": [mock_contact_data]}
        mock_put.return_value = {}

        ghl_update_contact("test@example.com", response)
        
        # Verify put_contact was called with correct payload
        expected_payload = {
            "customFields": [
                {
                    "id": "83SlnV9oK3J4aBnknXyD",
                    "key": "contact.tolt_referral_id",
                    "field_value": "ref_123"
                }
            ]
        }
        mock_put.assert_called_with("loc_123", "contact_123", expected_payload)
        print("✅ put_contact called with expected payload.")

    # 3. Test Case 2: Contact Found, Has Custom Field -> Should Skip
    print("\nTest 2: Contact Found, Has Custom Field (Should Skip)")
    mock_contact_data_existing = {
        "contactName": "Test User",
        "email": "test@example.com",
        "customFields": [{"id": "83SlnV9oK3J4aBnknXyD", "value": "some_value"}]
    }
    
    with patch('order_page.tasks.ContactServices.search_contacts') as mock_search:
        mock_search.return_value = {"contacts": [mock_contact_data_existing]}
        ghl_update_contact("test@example.com", response)

    # Cleanup
    response.delete()
    mapping.delete()
    field.delete()
    wrong_field.delete()
    form.delete()
    print("\n--- Test Complete ---")

if __name__ == "__main__":
    verify_strict_logic()
