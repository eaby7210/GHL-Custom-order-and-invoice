
import os
import django
import sys
from unittest.mock import patch

# Setup Django Environment
sys.path.append('/home/eaby/Projects/dj_investorbootz')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

from order_page.models import TypeformForm, TypeformField, TypeformPartnerMapping
import uuid

def verify_sync_deletion():
    print("--- Verifying Sync Deletion ---")
    
    # 1. Setup ID
    form_id = f"sync_test_{uuid.uuid4().hex[:6]}"
    
    # 2. Simulate API Payload with only A and B (C is deleted)
    mock_payload = {
        "id": form_id,
        "title": "Sync Test Form",
        "fields": [
            {
                "id": "f_drop_1",
                "ref": "ref_field",
                "type": "dropdown",
                "title": "Dropdown",
                "properties": {
                    "choices": [
                        {"ref": "ref_A", "label": "A"},
                        {"ref": "ref_B", "label": "B-Updated"} # Also testing update
                    ]
                }
            }
        ]
    }
    
    # 3. Patch TypeformService to prevent any API calls during save() or other ops from the start
    with patch('order_page.services.TypeformService') as MockService:
        # 1. Setup Form and Field and Mappings (Create triggers save triggers sync)
        # form_id defined above
        form = TypeformForm.objects.create(form_id=form_id, title="Sync Test Form")
        field = TypeformField.objects.create(
            form=form, field_id="f_drop_1", field_type="dropdown", title="Dropdown"
        )
        
        # Create 3 choices locally
        TypeformPartnerMapping.objects.create(form=form, field=field, choice_ref="ref_A", choice_label="A")
        TypeformPartnerMapping.objects.create(form=form, field=field, choice_ref="ref_B", choice_label="B")
        TypeformPartnerMapping.objects.create(form=form, field=field, choice_ref="ref_C", choice_label="C")
        
        print(f"Initial Mappings Count: {TypeformPartnerMapping.objects.filter(form=form).count()} (Expected 3)")

        print("Syncing Form with C removed and B updated...")
        TypeformForm.create_or_update_from_api(mock_payload)
        
    # 4. Verify Results
    mappings = TypeformPartnerMapping.objects.filter(form=form, field=field)
    print(f"Post-Sync Mappings Count: {mappings.count()}")
    
    mapping_a = mappings.filter(choice_ref="ref_A").first()
    mapping_b = mappings.filter(choice_ref="ref_B").first()
    mapping_c = mappings.filter(choice_ref="ref_C").first()
    
    if mapping_a: print("Mapping A exists.")
    if mapping_b: print(f"Mapping B exists with label: {mapping_b.choice_label}")
    if not mapping_c: print("Mapping C successfully deleted.")
    else: print("Mapping C still exists (Fail).")

    # Cleanup
    form.delete() # Helper delete implementation might cascade, or standard Django cascade
    # Clean mappings explicitly if needed
    TypeformPartnerMapping.objects.filter(form__form_id=form_id).delete()
    print("--- Test Complete ---")

if __name__ == "__main__":
    verify_sync_deletion()
