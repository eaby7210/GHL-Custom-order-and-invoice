import os
import django
import json
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

from stripe_payment.models import Order, ALaCarteService, ALaCarteItem, ALaCarteItemModalOption

def test_modal_option_creation():
    # Mock data based on data.json
    service_data = {
        "id": "notary",
        "title": "Notarizations & Signings",
        "subtitle": "Get documents signed or notarized",
        "form": {
            "title": "Document Order Options",
            "description": "Have documents signed or notarized",
            "items": [
                {
                    "id": "NTinperson",
                    "title": "In-Person Notarization",
                    "basePrice": 185
                },
                {
                    "id": "NTonline",
                    "title": "Online Notarization",
                    "basePrice": 105
                }
            ],
            "modalOption": {
                "form": [
                    {
                        "label": "Signers Name",
                        "name": "signersName",
                        "type": "text",
                        "value": "test name",
                        "valid_item_index": None
                    },
                    {
                        "label": "Email",
                        "name": "email",
                        "type": "email",
                        "value": "testmail@mailinator.com",
                        "valid_item_index": ["NTonline"]
                    }
                ]
            }
        }
    }
    
    service_totals = {
        "notary": {
            "items": {
                "NTinperson": {"discountedPrice": 185},
                "NTonline": {"discountedPrice": 105}
            }
        }
    }

    # Create a dummy order
    order = Order.objects.create(
        unit_type="single",
        service_type="a_la_carte"
    )
    
    # Create Service
    service = ALaCarteService.objects.create(
        order=order,
        service_id=service_data["id"],
        title=service_data["title"]
    )
    
    print("Testing NTinperson (Should have 'Signers Name' only)")
    item_data_inperson = service_data["form"]["items"][0]
    item_inperson = ALaCarteItem.from_api(service, item_data_inperson, service_data["form"], service_totals)
    
    modal_options_inperson = ALaCarteItemModalOption.objects.filter(item=item_inperson)
    print(f"Count: {modal_options_inperson.count()}")
    for opt in modal_options_inperson:
        print(f"- {opt.name}: {opt.value}")
        
    print("\nTesting NTonline (Should have 'Signers Name' and 'Email')")
    item_data_online = service_data["form"]["items"][1]
    item_online = ALaCarteItem.from_api(service, item_data_online, service_data["form"], service_totals)
    
    modal_options_online = ALaCarteItemModalOption.objects.filter(item=item_online)
    print(f"Count: {modal_options_online.count()}")
    for opt in modal_options_online:
        print(f"- {opt.name}: {opt.value}")

if __name__ == "__main__":
    test_modal_option_creation()
