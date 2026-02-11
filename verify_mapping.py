import os
import django
import sys

# Setup Django Environment
sys.path.append('/home/eaby/Projects/dj_investorbootz')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

import logging
from order_page.models import TypeformForm, TypeformField, TypeformPartnerMapping, TypeformResponse, TypeformAnswer
from order_page.tasks import ghl_update_contact
from tolt.models import Partner
from django.utils import timezone
import uuid

def run_test():
    print("--- Starting Verification Test ---")
    
    # 1. Setup Data
    form_id = f"test_form_{uuid.uuid4().hex[:8]}"
    form = TypeformForm.objects.create(
        form_id=form_id,
        title="Test Form"
    )
    
    field_id = f"field_{uuid.uuid4().hex[:8]}"
    field = TypeformField.objects.create(
        form=form,
        field_id=field_id,
        field_type="custom_test_type", # Bypass sync logic which checks for 'dropdown'
        title="Select Partner"
    )
    
    # Create a dummy Partner
    # Partner model uses id as PK and has first_name/last_name
    try:
        partner, _ = Partner.objects.get_or_create(
            id="test_partner_001",
            defaults={
                "email": "testpartner@example.com",
                "first_name": "Test",
                "last_name": "Partner"
            }
        )
    except Exception as e:
        print(f"Could not create Partner: {e}.")
        return

    mapping = TypeformPartnerMapping.objects.create(
        form=form,
        field=field,
        choice_ref="ref_123",
        choice_label="Partner Choice",
        partner=partner
    )
    
    response = TypeformResponse.objects.create(
        event_id=f"evt_{uuid.uuid4().hex}",
        form=form,
        token=f"tok_{uuid.uuid4().hex}",
        landed_at=timezone.now(),
        submitted_at=timezone.now()
    )
    
    # Answer matching the mapping
    TypeformAnswer.objects.create(
        response=response,
        field=field,
        answer_type="choice",
        value_json={"ref": "ref_123", "label": "Partner Choice"}
    )
    
    print(f"Created Mapping: {mapping}")
    print(f"Created Answer with ref: ref_123")
    
    # 2. Run Task Logic
    print("--- Running ghl_update_contact ---")
    try:
        # Pass dummy email
        ghl_update_contact("testuser@example.com", response)
    except Exception as e:
        print(f"Error running task: {e}")

    # 3. Cleanup
    print("--- Cleanup ---")
    response.delete()
    mapping.delete()
    field.delete()
    form.delete()
    print("Test Complete.")

if __name__ == "__main__":
    run_test()
