
import os
import django
import sys
import json
from rest_framework.test import APIRequestFactory
from order_page.views import TypeFormWebhook
from order_page.models import TypeformForm, TypeformField, TypeformPartnerMapping, TypeformResponse
from tolt.models import Partner
import uuid

# Setup Django Environment
sys.path.append('/home/eaby/Projects/dj_investorbootz')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

def simulate_webhook():
    print("--- Simulating Typeform Webhook ---")
    
    # 1. Setup minimal data for mapping to work
    # The payload uses specific IDs, so we should try to match them if possible or just use the payload logic.
    # The payload defines form_id="RDSI2QYH"
    # field ref="785293f2-28c1-4f04-8fcf-b9d86b105f9c" (dropdown)
    # choice ref="01KFK75BFS72289ZM4VHF10NGK" label="tests"
    
    form_id = "RDSI2QYH"
    
    # Ensure form exists (parser will create it, but we need mapping to exist beforehand to test logic? 
    # Actually, parser creates/updates form. But mapping is manual.)
    
    # Create form and field so we can attach mapping
    form, _ = TypeformForm.objects.get_or_create(form_id=form_id, defaults={"title": "DropDown test"})
    
    field_ref = "785293f2-28c1-4f04-8fcf-b9d86b105f9c"
    field_id = "23GANIokcQsE"
    field, _ = TypeformField.objects.get_or_create(
        form=form, 
        field_id=field_id, 
        defaults={
            "ref": field_ref, 
            "title": "test dropdown", 
            "field_type": "dropdown"
        }
    )
    
    # Create Partner
    partner, _ = Partner.objects.get_or_create(id="partner_test_002", defaults={"email": "an_account@example.com", "first_name": "Webhook", "last_name": "Tester"})
    
    # Create Mapping
    choice_ref = "01KFK75BFS72289ZM4VHF10NGK"
    choice_label = "tests"
    mapping, _ = TypeformPartnerMapping.objects.get_or_create(
        form=form,
        field=field,
        choice_ref=choice_ref,
        defaults={"choice_label": choice_label, "partner": partner}
    )
    print(f"Ensured Mapping exists: {mapping}")

    # 2. Prepare Payload
    payload = {
      "event_id": f"evt_{uuid.uuid4().hex}", # Unique event ID to avoid unique constraint if re-running
      "event_type": "form_response",
      "form_response": {
        "form_id": "RDSI2QYH",
        "token": f"tok_{uuid.uuid4().hex}", # Unique token
        "response_url": "https://admin.typeform.com/...",
        "landed_at": "2026-01-28T14:17:03Z",
        "submitted_at": "2026-01-28T14:17:03Z",
        "definition": {
          "id": "RDSI2QYH",
          "title": "DropDown test",
          "fields": [
            {
              "id": "23GANIokcQsE",
              "ref": "785293f2-28c1-4f04-8fcf-b9d86b105f9c",
              "type": "dropdown",
              "title": "test dropdown",
              "properties": {}
            },
            {
              "id": "L4Q9N1ALRjSv",
              "ref": "38c31c87-f2c0-431a-bcf7-0c81be6ebc0b",
              "type": "email",
              "title": "Email",
              "properties": {}
            }
          ],
            "endings": [],
            "settings": {}
        },
        "answers": [
          {
            "type": "choice",
            "choice": {
              "id": "jQAvxVosbL9i",
              "label": "tests",
              "ref": "01KFK75BFS72289ZM4VHF10NGK"
            },
            "field": {
              "id": "23GANIokcQsE",
              "type": "dropdown",
              "ref": "785293f2-28c1-4f04-8fcf-b9d86b105f9c"
            }
          },
          {
            "type": "email",
            "email": "an_account@example.com",
            "field": {
              "id": "L4Q9N1ALRjSv",
              "type": "email",
              "ref": "38c31c87-f2c0-431a-bcf7-0c81be6ebc0b"
            }
          }
        ]
      }
    }

    # 3. Call View
    factory = APIRequestFactory()
    request = factory.post('/order_page/typeform/webhook/', payload, format='json')
    view = TypeFormWebhook.as_view()
    
    print("Sending Request...")
    response = view(request)
    print(f"Response Status: {response.status_code}")
    print(f"Response Data: {response.data}")
    
    if response.status_code == 201:
        # Check if task logic would have triggered (by checking stdout for prints if we could, 
        # but here we rely on the Code we successfully reviewed).
        # We can also verify if Response object was created.
        response_id = response.data.get('response_id')
        print(f"Response Object ID: {response_id}")
        
        # Verify ghl_update_contact logic manually again on this real object since Celery is likely mocked/async using eager in test?
        # Or just trust the view call.
        # But we want to ensure the task CODE handles this object correctly.
        from order_page.tasks import ghl_update_contact
        
        print("--- Verifying Task Logic on Created Response ---")
        # Since celery .delay() returns immediately, we can't easily check side effects unless we run it synchronously.
        # But we can call the function directly to test the logic part:
        try:
             # Manually call task function (bypassing celery delay wrapper if possible, or just calling implementation)
             # NOTE: shared_task decorates it. calling .apply() usually runs it inline if EAGER is on, 
             # or we can inspect the module.
             
             # Actually, let's just run the function logic manually:
             ghl_update_contact("an_account@example.com", response_id)
        except Exception as e:
            print(f"Task Execution Error: {e}")

    print("Test Complete.")

if __name__ == "__main__":
    simulate_webhook()
