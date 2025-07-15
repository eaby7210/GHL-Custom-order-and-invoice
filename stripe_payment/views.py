# views.py
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, mixins
from rest_framework import status
from stripe_payment.models import (
    Order, ALaCarteService, ALaCarteAddOn, ALaCarteSubMenu,
    StripeCharge, CheckoutSession, NotaryClientCompany,
    StripeWebhookEventLog
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializer import OrderSerializer
from core.services import OAuthServices, ContactServices
from core.models import Contact, OAuthToken
from django.utils.dateparse import parse_datetime
from decimal import Decimal
import json
from .utils import create_stripe_session, get_coupon
from .services import InvoiceServices, NotaryDashServices
import stripe
# from stripe.error import SignatureVerificationError
from stripe._error import SignatureVerificationError, StripeError
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
from django.template.loader import render_to_string
import datetime

import re
from django.utils.timezone import now

class FormSubmissionAPIView(APIView):
    def post(self, request):
        data = request.data
        print("Received data:", json.dumps(data, indent=4)) 
        streetAddress = data.get("streetAddress")
        city = data.get("city")
        state = data.get("state")
        
        company_id = data.get("company_id")
        user_id= data.get("user_id")
        owner_id = None
        company_name = None
        coupon_code = data.get("coupon_code")
        coupon = None
        if coupon_code:
            coupon:stripe.Coupon |None = get_coupon(coupon_code)
            if coupon:
                print(f"Coupon found: {coupon.id} - {coupon.percent_off}% off")
            else:
                print(f"Coupon not found or invalid: {coupon_code}")
        else:
            print("No coupon code provided.")
        if (not company_id) or (not user_id):
            msg = "Company ID and User ID are required."
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = NotaryDashServices.get_client(company_id)
            if not response:
                return Response({"message":"Error on fetching Client"},status=status.HTTP_400_BAD_REQUEST)
            else:
                owner_id = response.get("data",{}).get("owner_id")
                company_name = response.get("data",{}).get("company_name")
                if not owner_id:
                    print(f"Error on fetching Owner ID for company {company_id} response: {json.dumps(response, indent=4)} ")
                    return Response({"message":"Error on fetching Owner ID"},status=status.HTTP_400_BAD_REQUEST)
                client = NotaryDashServices.get_client_one_user(company_id,user_id)
                if not client:
                    return Response({"message":"Error on fetching Client User"},status=status.HTTP_400_BAD_REQUEST)
            
         
        postal_code = data.get("postalCode")
        unit_type = data.get("unitType")
        address = data.get("address")
        
        unit = data.get("unit")
        service_type = data.get("serviceType")
        occupancy_status = data.get("occupancy_status")

        accepted_at = parse_datetime(data.get("acceptedAt")) if data.get("acceptedAt") else None
        tbd = data.get("tbd", False)
        preferred_datetime = parse_datetime(data.get("preferred_datetime")) if data.get("preferred_datetime") else None
        if preferred_datetime is not None:
            preferred_datetime = make_aware(preferred_datetime)
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
         
            occupancy_vacant = occupancy_status == "vacant",
            occupancy_occupied = occupancy_status == "occupied",
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
            contact_first_name_sched=data.get("contact_first_name_sched"),
            contact_last_name_sched=data.get("contact_last_name_sched"),
            contact_phone_sched_type=data.get("contact_phone_type_sched"),
            contact_phone_sched=data.get("contact_phone_sched"),
            contact_email_sched=data.get("contact_email_sched"),
            
            contact_first_name=data.get("contact_first_name"),
            contact_last_name=data.get("contact_last_name"),
            contact_phone_type=data.get("contact_phone_type"),
            contact_phone=data.get("contact_phone"),
            
            cosigner_first_name=data.get("cosigner_first_name_sched"),
            cosigner_last_name=data.get("cosigner_last_name_sched"),
            cosigner_phone_type=data.get("cosigner_phone_type_sched"),
            cosigner_phone=data.get("cosigner_phone_sched"),
            # cosigner_email=data.get("cosigner_email"),
            
            sp_instruction=data.get("special_instructions"),
            
            coupon_code=coupon_code,
            coupon_id=coupon.id if coupon else None,
            coupon_percent = coupon.percent_off if coupon and coupon.percent_off else Decimal('0.00'),
            coupon_fixed = coupon.amount_off if coupon and coupon.amount_off else Decimal('0.00'),
            
            company_id = company_id,
            user_id= user_id,
            owner_id=owner_id,
            
            company_name=company_name,
            total_price = Decimal(data.get("bundlePrice", 0)) if data.get("bundlePrice") else data.get("a_la_carte_total")
        )
  
        
    

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
                    submenu_input=item.get("submenu_input"),
                    reduced_names=item.get("reduced_name", ""),
                )

                
                for addon_key, addon_data in item.get("addOns", {}).items():
                    # addon_data is expected to be a dict with 'label' and 'price'
                    ALaCarteAddOn.objects.create(
                        service=service,
                        key=addon_key,
                        name=addon_data.get("label", addon_key),
                        price=Decimal(addon_data.get("price", 0))
    )

                # Submenu
                submenu = item.get("submenu")
                if submenu:
                    print(f"Submenu for service {service.name}: {json.dumps(submenu, indent=4)}")
                    ALaCarteSubMenu.objects.create(
                        service=service,
                        option=submenu.get("option"),
                        label=submenu.get("label"),
                        prompt_label=submenu.get("prompt"),
                        prompt_value=submenu.get("prompt_value"),
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
    
    def get(self, request, stripe_session_id):
        try:
            token_obj = OAuthServices.get_valid_access_token_obj()
            order = Order.objects.get(stripe_session_id=stripe_session_id)
            response = InvoiceServices.get_invoice(token_obj.LocationId, order.invoice_id)

            if not response:
                return self._handle_response(request, {"error": "Invoice not found"}, status.HTTP_404_NOT_FOUND)

            return self._handle_response(request, response, status.HTTP_200_OK)

        except Order.DoesNotExist:
            return self._handle_response(request, {"error": "Order not found"}, status.HTTP_404_NOT_FOUND)

    def _handle_response(self, request, data, status_code):
        # If HTML is expected (Browsable API), render custom template
        # print(f"format: {request.accepted_renderer.format}")
        # print(f"accepted_media_type: {request.accepted_media_type}")
        # print(f"data: {json.dumps(data, indent=4)}")
        if request.accepted_media_type == 'text/html':
            data["items"] = data.pop("invoiceItems", data.get("items", []))

            return render(request, "order_product_detail.html", {"invoice_data": data}, status=status_code)
        # Else, return JSON response
        return Response(data, status=status_code)

@api_view(['GET'])
def notary_view(request):
    if request.method == "GET":
        company_id =request.query_params.get('company_id')
        user_id = request.query_params.get('user_id')
        print(f"got is {company_id} {user_id}")
        if (not company_id) or (not user_id):
            msg = "Company ID and User ID are required."
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = NotaryDashServices.get_client(company_id)
            if not response:
                return Response({"message":"Error on fetching Client"},status=status.HTTP_400_BAD_REQUEST)
            else:
                owner_id = response.get("data").get("owner_id")
                if not owner_id:
                    print(f"Error on fetching Owner ID for company {company_id} response: {json.dumps(response, indent=4)} ")
                    return Response({"message":"Error on fetching Owner ID"},status=status.HTTP_400_BAD_REQUEST)
                client = NotaryDashServices.get_client_one_user(company_id,user_id)
                if not client:
                    return Response({"message":"Error on fetching Client User"},status=status.HTTP_400_BAD_REQUEST)
            return Response({
                "message": "Successfully fetched Notary Client",
                "client": company_id,
                "user_id": user_id,
                "owner_id": owner_id
            }, status=status.HTTP_200_OK)
    return Response({
        "message": "Notary view is not implemented yet"},status= status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def stripe_coupon(request, coupon_code):
    """
    Retrieve a Stripe coupon by its code.
    """
    if request.method == "GET":
        coupon = get_coupon(coupon_code)
        if coupon:
            return Response({
                "id": coupon.id if coupon.id else coupon.stripe_coupon_id, #type: ignore
                "name": coupon.name if coupon.name else "No Name",
                "percent_off": coupon.percent_off,
                "valid": coupon.valid
                
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Coupon not found or invalid"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"error": "Method not allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
      
@csrf_exempt
def stripe_webhook(request):
        
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', None)
    print(f"Stripe webhook received with payload: {payload}")
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
    event_id = event.get('id', None)
    event_created = event.get('created', None)
    # Process the event type
    event_type = event['type']
    print(f"Event type: {event_type}")
    data_object = event['data']['object']
    evt_log = StripeWebhookEventLog.objects.filter(event_id=event_id).first()
    if evt_log:
        print(f"Event {event_id} already processed at {evt_log.created_at}")
        return HttpResponse(status=200)
    evt_log = StripeWebhookEventLog(
        event_id=event_id,
        event_type=event_type,
        created_at=make_aware(datetime.datetime.fromtimestamp(event_created)) if event_created else None,
        event_data=json.dumps(data_object, indent=4),
    )
    payment_indent_id = data_object.get("payment_intent", None) 

    # print(f"Received Stripe event: {payload} event: {json.dumps(event, indent=4)}")
    # print("Event: \n", json.dumps(event,indent=4))
    if event_type == 'charge.succeeded':
        handle_charge_succeeded(event)
        return HttpResponse(status=200)
    elif event_type == 'charge.failed':
        handle_charge_failed(event)
        return HttpResponse(status=200)
    elif event_type == 'charge.refunded':
        handle_charge_refunded(event)
        return HttpResponse(status=200)
    elif event_type == 'charge.updated':
        handle_charge_updated(event)
        return HttpResponse(status=200)
    elif event_type == 'checkout.session.completed':
        session_obj = handle_checkout_session_completed(event)
        print(f"Checkout session completed: {json.dumps(event, indent=4)}")
        if not session_obj:
            msg = "Failed to process CheckoutSession. Expiring session due to server error."
            evt_log.error_message = msg
            evt_log.processed = True
            evt_log.save()
            
            # ✅ Proper way to cancel when using manual capture with Checkout
            try:
                stripe.checkout.Session.expire(data_object.get("id"))
            except Exception as e:
                print(f"Failed to expire session: {e}")
            
            return HttpResponse(status=500)
        else:
            try:
                stripe.PaymentIntent.capture(payment_indent_id)
                evt_log.error_message = "No errors"
                evt_log.processed = True
                evt_log.save()

            except StripeError as e:
                # Handle capture failure
                msg = e.user_message
                evt_log.error_message = msg
                evt_log.processed =True
                evt_log.save()
                return HttpResponse(status=500)
            return HttpResponse(status=200)

    else:
        print(f"Unhandled event type: {event_type}")
    
    return HttpResponse(status=500)
    
    
 

def format_phone_number(phone):
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Handle leading '1' (US country code)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits
    elif len(digits) == 10:
        digits = '1' + digits
    else:
        raise ValueError(f"Invalid phone number length: {phone}")

    return f"+{digits}"

def handle_charge_failed(event):
    print("❌ Charge failed:", json.dumps(event,indent=4))
    # Log failure or alert user

def handle_charge_refunded(event):
    print("↩️ Charge refunded:", json.dumps(event,indent=4))
    # Update refund status in your DB

def handle_charge_succeeded(event):
    import time
    time.sleep(1)  # Simulate processing delay
    obj = event['data']['object']
    # print(f"Stripe charge suceed: {json.dumps(event, indent=4)}")
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
    import time
    time.sleep(1)
    handle_charge_succeeded(event)
    # Optional: update metadata, receipt URL, etc.
      
def handle_checkout_session_completed(event):
    # print(f"Checkout session completed: {json.dumps(event, indent=4)}")
    obj = event['data']['object']
    session_id = obj["id"]
    order_obj = Order.objects.filter(stripe_session_id=session_id).first()
    
    if order_obj:
        # contact_name = (order_obj.contact_first_name_sched + " " + order_obj.contact_last_name_sched) if order_obj.contact_first_name_sched and order_obj.contact_last_name_sched else ""
        company_id = order_obj.company_id
        user_id= order_obj.user_id
        client_user = NotaryDashServices.get_client_one_user(company_id, user_id)
        client_user = client_user.get("data", {}) if client_user else {}
        contact_phone = format_phone_number(order_obj.contact_phone_sched)
        contact_email = client_user.get("email")
        token_obj = OAuthServices.get_valid_access_token_obj()
        search_response = ContactServices.search_contacts(token_obj.LocationId,query={
             "locationId":"n7iGMwfy1T5lZZacxygj",
                "page": 1,
                "pageLimit": 20,
                "filters": [
                    {
                    "field": "email",
                    "operator": "eq",
                    "value": contact_email
                    },
                     {
                    "field": "phone",
                    "operator": "eq",
                    "value": contact_phone
                    },
                ],
                "sort": [
                    {
                    "field": "dateAdded",
                    "direction": "desc"
                    }
                ]
        })
        print(json.dumps(search_response, indent=4))
        if len(search_response.get("contacts", [])) > 0:
            contact_data = search_response["contacts"][0]
            print(f"Found existing contact: {json.dumps(contact_data, indent=4)}")
        else:
            contact ={
            "firstName":order_obj.contact_first_name_sched if order_obj.contact_first_name_sched else "",
            "lastName": order_obj.contact_last_name_sched if order_obj.contact_last_name_sched else "",
            # "name": contact_name,
            "locationId": token_obj.LocationId,
            "email": contact_email,
            "phone": contact_phone,
            "country": "US",  
            "type": "customer"  
            }
            contact_data, status = ContactServices.post_contact(token_obj.LocationId, contact)
            if status != 201:
                contact_id = contact_data.get("meta", {}).get("contactId", None)
                print(f"Contact creation failed with status {status}. Attempting to retrieve existing contact by ID: {contact_id}")
                if contact_id:
                    contact_data = ContactServices.get_contact(token_obj.LocationId, contact_id)
                    contact_data["id"] = contact_id
                    # print(f"Contact creation conflicted with: {contact_data.get('id')} Using {json.dumps(contact_data, indent=4)}")
            ContactServices.save_contact(contact_data)
        invoice_payload = build_invoice_payload(
            order_obj, contact=contact_data, location_id=token_obj.LocationId,
            session_obj=obj,client_user=client_user
        )
        if not invoice_payload:
            return None
        else:
            response = InvoiceServices.post_invoice(token_obj.LocationId, invoice_payload)
            print(f"Invoice response: {json.dumps(response, indent=4)}")
            if response:
                order_obj.location_id = token_obj.LocationId
                order_obj.invoice_id = response.get("_id")
                order_obj.save()
            else:
                print("Failed to create invoice, skipping sending and payment recording.")
                return None
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

def build_notary_order(order :Order, inv_data, prd_name, client_user,session_obj):
    
    """
    Build Notary order payload based on given order and contact.

    """
    final_price = float(order.total_price) if order.total_price else 0
    discount_amount = inv_data.get("discount",{}).get("value",0)
    total_amount = session_obj.amount_total if session_obj else None
    total_amount = total_amount/100 if total_amount else None
    print(f"final price= {final_price} - discount: {discount_amount} {total_amount}")
    final_price = final_price - discount_amount
    company_id = order.company_id
    client_id = order.user_id
    
    
    html_content = render_to_string(
        "order_product_detail.html", 
        context={
            "invoice_data":inv_data,
            "order":order
            }
        )
    order_html_content = render_to_string(
        "order_detail.html", 
        context={
            "invoice_data":inv_data,
            "order":order
            }
    )
    notary_product={
        "client_id": company_id,
        "owner_id": order.owner_id,
        "name": prd_name,
        "pay_to_notary": 0,
        "charge_client": total_amount if total_amount else final_price,
        "scanbacks_required": False,
        "attr": {
            "additional_instructions": html_content,
            # "scanbacks_instructions": "alias",
            },
        }
    prd_response = None
    prd = {}
    prd_response = NotaryDashServices.create_products(notary_product)
    if prd_response:
        prd = prd_response.get("data", None)
        print(f"prd: {json.dumps(prd, indent=4)}")
    formatted_datetime = order.preferred_datetime.strftime("%Y-%m-%d %H:%M:%S") if order.preferred_datetime else "TBD"
    notary_order = {
        "client_id": company_id,
        "client_contact_id": client_id,
        "location": {
            "when": "at" if order.preferred_datetime else "TBD",
            
            "on": formatted_datetime,
            "address": {
                "address_1": order.streetAddress or order.unit,
                # "address_2": order.unit or "",
                "city": order.city or "",
                "zip": order.postal_code or "",
                "state": order.state or "",
            }
            },
            "signer": {
                "first_name": order.contact_first_name_sched if order.contact_first_name_sched else "",
                "last_name": order.contact_last_name_sched if order.contact_last_name_sched else "",
                "mobile_phone": re.sub(r"[^\d+]", "", str(order.contact_phone_sched)) if order.contact_phone_sched else ""
            },
            "product": {
                "parent_id": prd.get("id") if prd_response else None,
                "name": prd.get("name") if prd_response else prd_name,
                "pay_to_notary": prd.get("pay_to_notary", 0) if prd_response else 0,
                "charge_client": prd.get("charge_client", order.total_price) if prd_response else order.total_price,
                "scanbacks_required": False
            },
            "attr": {
                # "lender": "possimus",
                # "file_number": "sapiente",
                # "loan_number": "natus",
                "special_instructions": order_html_content or order.sp_instruction,
                # "delivery_instructions": "impedit"
            },
            "team": { "id": 3680 }
        }
    # "appt_time": formatted_datetime,
    if formatted_datetime!= "TBD":
        notary_order['location']['appt_time'] = formatted_datetime
    if order.cosigner_first_name and order.cosigner_last_name:
        notary_order["cosigner"] = {
            "first_name": order.cosigner_first_name if order.cosigner_first_name else "",
            "last_name": order.cosigner_last_name if order.cosigner_last_name else "",
            "mobile_phone": re.sub(r"[^\d+]", "", str(order.cosigner_phone)) if order.cosigner_phone else "",
            "type": "cosigner"
        }
    
    ord_response = NotaryDashServices.create_order(notary_order)
    # print("Notary order response:", json.dumps(ord_response, indent=4))
    if ord_response and ord_response.get("data"):
        inv_data["invoiceNumber"] = str(ord_response.get("data", {}).get("id"))
        return inv_data
    else:
        
        return None
        
def build_invoice_payload(order , contact, location_id, session_obj,client_user):
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
    notary_product_names=[]
    if order.service_type == "a_la_carte":
        
        for service in order.a_la_carte_services.all():
            # Main service item
            notary_product_names.append(service.reduced_names)
            items.append(build_item(
                name=service.name,
                description=service.description,
            
                price=service.price
            ))

            # Submenu (if exists)
            if hasattr(service, "submenu"):
                submenu = service.submenu
                items.append(build_item(
                    name=f"{service.name} submenu {("- "+ submenu.label) if submenu.label else ""}",
                    description=f"{("Selected option: "+ submenu.option + " -") if submenu.option else ""} {"Prompt: " + submenu.prompt_label if submenu.prompt_label else ""} - {submenu.prompt_value if submenu.prompt_value else ""}",
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
        notary_product_names.append(order.bundle_item)
        items.append(build_item(
            name=order.bundle_item,
            description=order.bundle_group,
            price=order.total_price
        ))
    notary_product_names = " ".join(notary_product_names)
    print(f"Notary product names: {notary_product_names}")
    address={
            "addressLine1":  order.unit or "",
            # "addressLine2": order.unit or "",
            "city": order.city or "",
            "state": order.state or "",
            "countryCode": "US",
            "postalCode": order.postal_code or ""
        }
    contact_ph = format_phone_number(order.contact_phone_sched)
    print(f"Formatted contact phone: {contact_ph}")
    print(f"discount amount: {session_obj.total_details.amount_discount}")
    invoice_data = {
        "altId": location_id,
        "altType": "location",
        "name": f"{order.company_name} - {order.get_service_type_display()} ",
        "businessDetails": {
     
            "name": order.company_name or "",
            "phoneNo": contact_ph or "",
            "email": client_user.get("email", ""),
            "address": address,
         
        },
        # "customValues": [],
        "currency": "USD",
        "items": items,
        "discount": {
            "value": (float(session_obj.total_details.amount_discount)/100),
            "type": "fixed",
            # "validOnProductIds": "[ '6579751d56f60276e5bd4154' ]"
        },
        "termsNotes": "<p>This is a default terms.</p>",
        "title": f"Invoice -{order.get_service_type_display()}",
        "contactDetails": {
            "id": contact.get("id"),
            "name": order.contact_first_name_sched + " " + order.contact_last_name_sched if order.contact_first_name_sched and order.contact_last_name_sched else "",
            "phoneNo": contact_ph or "",
            "email": client_user.get("email", ""),
            "additionalEmails": [],
            "companyName": "",
            "address": address,
            "customFields": []
        },
        "invoiceNumber": f"{str(order.stripe_session_id)}",
        "issueDate": now().date().isoformat(),
        "dueDate": now().date().isoformat(),
        "sentTo": {
            "email": [client_user.get("email")] if client_user.get("email") else [],
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
    
    invoice_data = build_notary_order(order, inv_data=invoice_data, prd_name=notary_product_names, client_user=client_user, session_obj=session_obj)
    print("Invoice data payload:", json.dumps(invoice_data, indent=4))
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
    # print(f"Send invoice response: {json.dumps(response, indent=4)}")

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
    # print(f"Record payment response: {json.dumps(response, indent=4)}")
    



class OrderRetrieveView(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = Order.objects.prefetch_related('a_la_carte_services').all()
    serializer_class = OrderSerializer
    lookup_field = "stripe_session_id"

