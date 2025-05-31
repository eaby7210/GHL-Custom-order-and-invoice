# views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Order, ALaCarteService, ALaCarteAddOn, ALaCarteSubMenu,
    StripeCharge, CheckoutSession
)
from core.services import OAuthServices, ContactServices
from core.models import Contact, OAuthToken
from django.utils.dateparse import parse_datetime
from decimal import Decimal
import json
from .utils import create_stripe_session
from .services import InvoiceServices
import stripe
# from stripe.error import SignatureVerificationError
from stripe._error import SignatureVerificationError
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
import datetime
import re
from django.utils.timezone import now

class FormSubmissionAPIView(APIView):
    def post(self, request):
        data = request.data
        # print("Received data:", json.dumps(data, indent=4)) 
        # Common fields
        # data ={
        # "unitType": "single",
        # "streetAddress": "Dolores unde minim i",
        # "city": "Ullamco molestiae ev",
        # "postalCode": "Voluptatem quisquam",
        # "unit": "Voluptate est deleni",
        # "state": "Montana",
        # "serviceType": "bundled",
        # "bundleGroup": "InvestorBootz Deal Accelerator™ Bundle",
        # "bundleItem": "Ext/Int Photos + Walk Through Video",
        # "bundlePrice": 180,
        # "occupancy_occupied": True,
        # "preferred_datetime": "1995-05-02T18:59",
        # "contact_name_sched": "Roanna Forbes",
        # "contact_phone_sched": "+1 (521) 617-7188",
        # "contact_email_sched": "josafyc@mailinator.com",
        # "tbd": True,
        # "acceptedAt": "2025-05-31T18:36:33.457Z"
        # }
        streetAddress = data.get("streetAddress")
        city = data.get("city")
        state = data.get("state")
     
        postal_code = data.get("postalCode")
        unit_type = data.get("unitType")
        address = data.get("address")
        
        unit = data.get("unit")
        service_type = data.get("serviceType")

        accepted_at = parse_datetime(data.get("acceptedAt")) if data.get("acceptedAt") else None
        tbd = data.get("tbd", False)
        preferred_datetime = parse_datetime(data.get("preferred_datetime")) if data.get("preferred_datetime") else None

        # Create order
        order = Order.objects.create(
            unit_type=unit_type,
            address=address,
            state=state,
            city=city,
            postal_code=postal_code,
            tbd=tbd,
            unit=unit,
            service_type=service_type,
            accepted_at=accepted_at,
            preferred_datetime=preferred_datetime,
            bundle_group=data.get("bundleGroup"),
            bundle_item=data.get("bundleItem"),
            occupancy_vacant=data.get("occupancy_vacant", False),
            occupancy_occupied=data.get("occupancy_occupied", False),
            access_lock_box=data.get("access_lock_box", False),
            lock_box_code=data.get("lock_box_code"),
            lock_box_location=data.get("lock_box_location"),
            access_app_lock_box=data.get("access_app_lock_box", False),
            access_meet_contact=data.get("access_meet_contact", False),
            access_hidden_key=data.get("access_hidden_key", False),
            hidden_key_directions=data.get("hidden_key_directions"),
            access_community_access=data.get("access_community_access", False),
            community_access_instructions=data.get("community_access_instructions"),
            access_door_code=data.get("access_door_code", False),
            door_code_value=data.get("door_code_value"),
            contact_name_sched=data.get("contact_name_sched"),
            contact_phone_sched=data.get("contact_phone_sched"),
            contact_email_sched=data.get("contact_email_sched"),
            total_price = Decimal(data.get("bundlePrice", 0)) if data.get("bundlePrice") else data.get("a_la_carte_total")
        )
        # contact_name = order.contact_name_sched  
        # contact_phone = order.contact_phone_sched 
        # contact_email = order.contact_email_sched
        # token_obj = OAuthServices.get_valid_access_token_obj()
        
    

        # Handle A La Carte services
        if service_type == "a_la_carte":
            # a_la_services = data.get("a_la_carte_services", [])
            a_la_services = [
                value for key, value in data.items()
                if key.startswith("a_la_carte_") and key != "a_la_carte_total"
            ]
            # print("A La Carte Services:", json.dumps(a_la_services, indent=4))
            for item in a_la_services:
                service = ALaCarteService.objects.create(
                    order=order,
                    key=item.get("key"),
                    name=item.get("name"),
                    price=Decimal(item.get("price", 0)),
                    description=item.get("description"),
                    prompt=item.get("prompt"),
                    total_price=Decimal(item.get("total_price", 0)),
                    addons_price=Decimal(item.get("addons_price", 0)),
                    submenu_input=item.get("submenu_input")
                )

                
                for addon_name, addon_price in item.get("addOns", {}).items():
                    ALaCarteAddOn.objects.create(
                        service=service,
                        name=addon_name,
                        price=Decimal(addon_price)
                    )

                # Submenu
                submenu = item.get("submenu")
                if submenu:
                    ALaCarteSubMenu.objects.create(
                        service=service,
                        option=submenu.get("option"),
                        label=submenu.get("label"),
                        amount = Decimal(submenu.get("amount") or submenu.get("option_price") or 0)
                    )
        frontend_domain = request.headers.get("Origin") 
        # if not frontend_domain:
        #     frontend_domain = "http://localhost:5173"
        print(f"Frontend domain: {frontend_domain}")

        try:
            stripe_session = create_stripe_session(order, frontend_domain)
            order.stripe_session_id = stripe_session.id


            order.save()
            return Response({
                "message": "Order created successfully",
                "order_id": order.id, # type: ignore
                "stripe_checkout_url": stripe_session.url
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                "message": "Order created, but Stripe session failed",
                "order_id": order.id, # type: ignore
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    



@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    # endpoint_secret = "whsec_f15e56f0881d7d269a0eed0131e76fe54a895bc712d81de8868f2e5388198683"

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)
    except SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse(status=400)

    # Process the event type
    event_type = event['type']
    data_object = event['data']['object']

    print(f"Received Stripe event: {event_type}")
    # print("Event: \n", json.dumps(event,indent=4))
    if event_type == 'charge.succeeded':
        handle_charge_succeeded(event)
    elif event_type == 'charge.failed':
        handle_charge_failed(event)
    elif event_type == 'charge.refunded':
        handle_charge_refunded(event)
    elif event_type == 'charge.updated':
        handle_charge_updated(event)
    elif event_type == 'checkout.session.completed':
        session_obj : CheckoutSession= handle_checkout_session_completed(event)
        print(f"Checkout session completed: {session_obj.session_id}")
    else:
        print(f"Unhandled event type: {event_type}")

    return HttpResponse(status=200)


def handle_charge_failed(event):
    print("❌ Charge failed:", json.dumps(event,indent=4))
    # Log failure or alert user

def handle_charge_refunded(event):
    print("↩️ Charge refunded:", json.dumps(event,indent=4))
    # Update refund status in your DB

def handle_charge_succeeded(event):
    obj = event['data']['object']
    StripeCharge.objects.update_or_create(
        charge_id=obj['id'],
        defaults={
            "payment_intent_id": obj.get("payment_intent"),
            "amount": obj["amount"],
            "currency": obj["currency"],
            "paid": obj["paid"],
            "status": obj["status"],
            "captured": obj["captured"],
            "receipt_url": obj.get("receipt_url"),
            "customer_email": obj.get("billing_details", {}).get("email"),
            "customer_name": obj.get("billing_details", {}).get("name"),
            "billing_country": obj.get("billing_details", {}).get("address", {}).get("country"),
            "brand": obj.get("payment_method_details", {}).get("card", {}).get("brand"),
            "last4": obj.get("payment_method_details", {}).get("card", {}).get("last4"),
            "exp_month": obj.get("payment_method_details", {}).get("card", {}).get("exp_month"),
            "exp_year": obj.get("payment_method_details", {}).get("card", {}).get("exp_year"),
            "network_transaction_id": obj.get("payment_method_details", {}).get("card", {}).get("network_transaction_id"),
            "created": make_aware(datetime.datetime.fromtimestamp(obj["created"])),
            "livemode": obj.get("livemode", False),
        }
    )

def handle_charge_updated(event):
    handle_charge_succeeded(event)
    # Optional: update metadata, receipt URL, etc.
      
def handle_checkout_session_completed(event):
    obj = event['data']['object']
    session_id = obj["id"]
    order_obj = Order.objects.filter(stripe_session_id=session_id).first()
    if order_obj:
     

        contact_name = order_obj.contact_name_sched
        contact_phone = re.sub(r"[^\d+]", "", str(order_obj.contact_phone_sched))
        contact_email = order_obj.contact_email_sched
        token_obj = OAuthServices.get_valid_access_token_obj()
        search_response = ContactServices.search_contacts(token_obj.LocationId,query={
             "locationId":"n7iGMwfy1T5lZZacxygj",
                "page": 1,
                "pageLimit": 20,
                "filters": [
                    {
                    "field": "email",
                    "operator": "eq",
                    "value": "kujyr@mailinator.com"
                    },
                     {
                    "field": "phone",
                    "operator": "eq",
                    "value": "+16229781609"
                    },
                ],
                "sort": [
                    {
                    "field": "dateAdded",
                    "direction": "desc"
                    }
                ]
        })
        if len(search_response.get("contacts", [])) > 0:
            contact_data = search_response["contacts"][0]
            print(f"Found existing contact: {json.dumps(contact_data, indent=4)}")
        else:
            contact ={
            "firstName": contact_name.split()[0] if contact_name else "",
            "lastName": " ".join(contact_name.split()[1:]) if contact_name else "",
            "name": contact_name,
            "locationId": token_obj.LocationId,
            "email": contact_email,
            "phone": contact_phone,
            "country": "US",  
            "type": "customer"  
            }
            contact_data = ContactServices.post_contact(token_obj.LocationId, contact)
            ContactServices.save_contact(contact_data)
        invoice_payload = build_invoice_payload(
            order_obj, contact=contact_data, location_id=token_obj.LocationId
        )
        response = InvoiceServices.post_invoice(token_obj.LocationId, invoice_payload)
        print(f"Invoice response: {json.dumps(response, indent=4)}")
        send_invoice(response)
        record_payment(response)
    session_obj ,created = CheckoutSession.objects.update_or_create(
        session_id=obj["id"],
        defaults={
            "payment_intent": obj.get("payment_intent"),
            "amount_subtotal": obj.get("amount_subtotal"),
            "amount_total": obj.get("amount_total"),
            "currency": obj.get("currency"),
            "payment_status": obj.get("payment_status"),
            "customer_email": obj.get("customer_details", {}).get("email"),
            "customer_name": obj.get("customer_details", {}).get("name"),
            "metadata": obj.get("metadata", {}),
            "created": make_aware(datetime.datetime.fromtimestamp(obj["created"]))
        }
    )
    
    return session_obj

def build_invoice_payload(order, contact, location_id):
    """
    Build JSON payload for invoice based on given order.
    """

    def build_item(name, description, price, currency="USD", qty=1):
        return {
            "name": name,
            "description": description or "",

            "currency": currency,
            "amount": float(price),
            "qty": qty,
            "taxes": [],
            "isSetupFeeItem": False,
            "type": "one_time",
            "taxInclusive": True,
            "discount": {
                "value": 0,
                "type": "percentage",
                "validOnProductIds": []
            }
        }

    items = []
    if order.service_type == "a_la_carte":
        for service in order.a_la_carte_services.all():
            # Main service item
            items.append(build_item(
                name=service.name,
                description=service.description,
            
                price=service.price
            ))

            # Submenu (if exists)
            if hasattr(service, "submenu"):
                submenu = service.submenu
                items.append(build_item(
                    name=f"{service.name} - {submenu.label}",
                    description=submenu.option,
                    price=submenu.amount
                ))

            # Addons
            for addon in service.addons.all():
                items.append(build_item(
                    name=f"{service.name} - {addon.name}",
                    description=f"Addon for {service.name}",
            
                    price=addon.price
                ))
    elif order.service_type == "bundled":
        items.append(build_item(
            name=order.bundle_item,
            description=order.bundle_group,
            price=order.total_price
        ))
    address={
            "addressLine1": order.streetAddress or "",
            "addressLine2": order.unit or "",
            "city": order.city or "",
            "state": order.state or "",
            "countryCode": "US",
            "postalCode": order.postal_code or ""
        }
    invoice_data = {
        "altId": location_id,
        "altType": "location",
        "name": f"Invoice for {order.get_service_type_display()} Order",
        "businessDetails": {
     
            "name": order.contact_name_sched or "",
            "phoneNo": order.contact_phone_sched or "",
            "email": order.contact_email_sched or "",
            "address": address,
         
        },
        # "customValues": [],
        "currency": "USD",
        "items": items,
        "termsNotes": "<p>This is a default terms.</p>",
        "title": "INVOICE",
        "contactDetails": {
            "id": contact.get("id"),
            "name": order.contact_name_sched or "",
            "phoneNo": re.sub(r"[^\d+]", "", str(order.contact_phone_sched)) or "",
            "email": order.contact_email_sched or "",
            "additionalEmails": [],
            "companyName": "",
            "address": address,
            "customFields": []
        },
        "invoiceNumber": f"{order.stripe_session_id}",
        "issueDate": now().date().isoformat(),
        "dueDate": now().date().isoformat(),
        "sentTo": {
            "email": [order.contact_email_sched] if order.contact_email_sched else [],
            "emailCc": [],
            "emailBcc": [],
            "phoneNo": [order.contact_phone_sched] if order.contact_phone_sched else []
        },
        "liveMode": False,
        "invoiceNumberPrefix": "INV-",
        "paymentMethods": {
            "stripe": {}
        },
        "attachments": []
    }
    # print("Invoice data payload:", json.dumps(invoice_data, indent=4))
    return invoice_data

def send_invoice(invoice_data):
    oauth_obj = OAuthToken.objects.get(LocationId=invoice_data.get("altId"))
    payload = {
    "altId": invoice_data.get("altId"),
    "altType": "location",
    "userId": oauth_obj.userId,
    "action": "send_manually",
    "liveMode":invoice_data.get("liveMode", False),
    }
    response = InvoiceServices.send_invoice(invoice_data.get("altId"), invoice_data.get("_id"), payload)
    print(f"Send invoice response: {json.dumps(response, indent=4)}")

def record_payment(invoice_data):
    oauth_obj = OAuthToken.objects.get(LocationId=invoice_data.get("altId"))
    payload = {
        "altId": invoice_data.get("altId"),
        "altType": "location",
        "mode": "cash",
        # "card": {
        #     "brand": "string",
        #     "last4": "string"
        # },
        # "cheque": { "number": "129-129-129-912" },
        "notes": "This was a Completed Payment from Order Form",
        "amount":invoice_data.get("total"),
        # "meta": {},

    }
    response = InvoiceServices.record_payment(invoice_data.get("altId"), invoice_data.get("_id"), payload)
    print(f"Record payment response: {json.dumps(response, indent=4)}")