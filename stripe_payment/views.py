# views.py
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, mixins
from rest_framework import status
from stripe_payment.models import (
    Order, ALaCarteService,
    StripeCharge, CheckoutSession, NotaryClientCompany,
    StripeWebhookEventLog, Bundle
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
                print(f"Company name {company_name}")
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
            
        # Create order (removed bundle_group and bundle_item fields)
        order = Order.objects.create(
            unit_type=unit_type,
            address=address,
            state=state,
            city=city,
            postal_code=postal_code,
            streetAddress = data.get("street"),
            tbd=tbd,
            unit=unit,
            service_type=service_type,
            accepted_at=accepted_at,
            preferred_datetime=preferred_datetime,
         
            occupancy_vacant = occupancy_status == "vacant",
            occupancy_occupied = occupancy_status == "occupied",
            occupancy_status = occupancy_status,
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
            # For bundled services, total_price will be calculated from bundle prices
            # For a_la_carte, use the provided total
            total_price = data.get("a_la_carte_total") if service_type == "a_la_carte" else None,
            order_protection= data.get("order_protection"),
            order_protection_price = str(data.get("order_protection_price", '0.00'))
        )
  
        #Save bundles
        bundles_data = data.get("bundles", [])
        a_la_carte_data = data.get("a_la_carteOrder", [])
        total_bundle_price = Decimal('0.00')
        
        for b in bundles_data:
            bundle_price = Decimal(str(b.get("price", 0)))
            total_bundle_price += bundle_price
            
            Bundle.objects.create(
                order=order,
                name=b.get("name"),
                description=b.get("description"),
                base_price=Decimal(str(b.get("basePrice", 0))),
                price=bundle_price,
            )
        
        # Update order total_price for bundled services
        if service_type == "bundled" and total_bundle_price > 0:
            order.total_price = total_bundle_price
            order.save()

        # Handle A La Carte services
        if a_la_carte_data:
            order.discount_percent = Decimal(
                data.get("progress", {}).get("currentPercent", 0)
            )
            ALaCarteService.from_api(order, data)

            total_ala_price =0
            for svc_id, svc_total in (data.get("serviceTotals") or {}).items():
                total_ala_price += Decimal(svc_total.get("subtotal", 0))

        if bundles_data and a_la_carte_data:
            order.service_type = "mixed"
        elif bundles_data:
            order.service_type = "bundled"
        elif a_la_carte_data:
            order.service_type = "a_la_carte"


        order.total_price = total_bundle_price + total_ala_price
        order.save()

        frontend_domain = request.headers.get("Origin") 
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
    print("=== STRIPE WEBHOOK RECEIVED ===")
    print(f"Request method: {request.method}")
    print(f"Request path: {request.path}")
    
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', None)
    print(f"Stripe webhook received with payload length: {len(payload)}")
    print(f"Signature header present: {sig_header is not None}")
    
    # endpoint_secret = "whsec_f15e56f0881d7d269a0eed0131e76fe54a895bc712d81de8868f2e5388198683"
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    # print(f"Webhook secret configured: {bool(endpoint_secret)}")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        print("✅ Webhook signature verified successfully")
    except ValueError as e:
        print(f"❌ Invalid payload: {e}")
        return HttpResponse(status=400)
    except SignatureVerificationError as e:
        print(f"❌ Invalid signature: {e}")
        return HttpResponse(status=400)
     
    event_id = event.get('id', None)
    event_created = event.get('created', None)
    event_type = event['type']
    
    print(f"Event ID: {event_id}")
    print(f"Event type: {event_type}")
    print(f"Event created: {event_created}")
    
    data_object = event['data']['object']
    
    # Check if event already processed
    evt_log = StripeWebhookEventLog.objects.filter(event_id=event_id).first()
    if evt_log:
        print(f"⚠️ Event {event_id} already processed at {evt_log.created_at}")
        return HttpResponse(status=200)
    
    # Create event log
    evt_log = StripeWebhookEventLog(
        event_id=event_id,
        event_type=event_type,
        created_at=make_aware(datetime.datetime.fromtimestamp(event_created)) if event_created else None,
        event_data=json.dumps(data_object, indent=4),
    )
    
    payment_indent_id = data_object.get("payment_intent", None)
    print(f"Payment intent ID: {payment_indent_id}")
    
    # Handle different event types
    if event_type == 'charge.succeeded':
        print("Processing charge.succeeded...")
        handle_charge_succeeded(event)
        return HttpResponse(status=200)
        
    elif event_type == 'charge.failed':
        print("Processing charge.failed...")
        handle_charge_failed(event)
        return HttpResponse(status=200)
        
    elif event_type == 'charge.refunded':
        print("Processing charge.refunded...")
        handle_charge_refunded(event)
        return HttpResponse(status=200)
        
    elif event_type == 'charge.updated':
        print("Processing charge.updated...")
        handle_charge_updated(event)
        return HttpResponse(status=200)
        
    elif event_type == 'checkout.session.completed':
        print("=== Processing checkout.session.completed ===")
        print(f"Session ID: {data_object.get('id')}")
        print(f"Payment status: {data_object.get('payment_status')}")
        print(f"Amount total: {data_object.get('amount_total')}")
        
        session_obj = handle_checkout_session_completed(event)
        print(f"handle_checkout_session_completed returned: {session_obj is not None}")
        
        if not session_obj:
            msg = "Failed to process CheckoutSession. Expiring session due to server error."
            print(f"❌ {msg}")
            evt_log.error_message = msg
            evt_log.processed = True
            evt_log.save()
            
            # Expire the session
            try:
                stripe.checkout.Session.expire(data_object.get("id"))
                print("✅ Session expired successfully")
            except Exception as e:
                print(f"❌ Failed to expire session: {e}")
            
            return HttpResponse(status=500)
        else:
            print("✅ Session processed successfully, attempting to capture payment...")
            try:
                if payment_indent_id:
                    stripe.PaymentIntent.capture(payment_indent_id)
                    print("✅ Payment captured successfully")
                else:
                    print("⚠️ No payment intent ID found")
                
                evt_log.error_message = "No errors"
                evt_log.processed = True
                evt_log.save()
                print("✅ Event log saved successfully")
                
            except StripeError as e:
                msg = e.user_message or str(e)
                print(f"❌ Payment capture failed: {msg}")
                evt_log.error_message = msg
                evt_log.processed = True
                evt_log.save()
                return HttpResponse(status=500)
            
            return HttpResponse(status=200)
    else:
        print(f"⚠️ Unhandled event type: {event_type}")
        return HttpResponse(status=200)  # Changed from 500 to 200 for unhandled events
    


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
    print("=== HANDLE_CHECKOUT_SESSION_COMPLETED STARTED ===")
    print(f"Event received: {event.get('type', 'Unknown')}")
    
    try:
        obj = event['data']['object']
        session_id = obj["id"]
        payment_intent_id = obj["payment_intent"]
        print(f"Session ID: {session_id}")
        
        order_obj = Order.objects.filter(stripe_session_id=session_id).first()
        print(f"Order found: {order_obj is not None}")
        
        if not order_obj:
            print("ERROR: No order found with this session ID")
            return None
        
        print(f"Order ID: {order_obj.id}, Company ID: {order_obj.company_id}, User ID: {order_obj.user_id}")
        
        # contact_name = (order_obj.contact_first_name_sched + " " + order_obj.contact_last_name_sched) if order_obj.contact_first_name_sched and order_obj.contact_last_name_sched else ""
        company_id = order_obj.company_id
        user_id = order_obj.user_id
        
        print("Calling NotaryDashServices.get_client_one_user...")
        client_user = NotaryDashServices.get_client_one_user(company_id, user_id)
        client_user = client_user.get("data", {}) if client_user else {}
        print(f"Client user retrieved: {bool(client_user)}")
        try:
            contact_phone = format_phone_number(order_obj.contact_phone_sched)
        except:
            contact_phone = order_obj.contact_phone_sched
        contact_email = client_user.get("email")
        print(f"Contact phone: {contact_phone}, Contact email: {contact_email}")
        
        print("Getting OAuth token...")
        token_obj = OAuthServices.get_valid_access_token_obj()
        print(f"Token location ID: {token_obj.LocationId if token_obj else 'None'}")
        
        print("Searching for existing contacts...")
        search_response = ContactServices.search_contacts(token_obj.LocationId, query={
            "locationId": "n7iGMwfy1T5lZZacxygj",
            "page": 1,
            "pageLimit": 20,
            "filters": [
                {
                    "field": "email",
                    "operator": "eq",
                    "value": contact_email
                },
                # {
                #     "field": "phone",
                #     "operator": "eq",
                #     "value": contact_phone
                # },
            ],
            "sort": [
                {
                    "field": "dateAdded",
                    "direction": "desc"
                }
            ]
        })
        
        # print(f"Contact search response: {json.dumps(search_response, indent=4)}")
        
        if len(search_response.get("contacts", [])) > 0:
            contact_data = search_response["contacts"][0]
            # print(f"Found existing contact: {json.dumps(contact_data, indent=4)}")
        else:
            client_attr = client_user.get("attr")
            notary_phone = (client_attr.get("phone") if client_attr.get("phone") else client_attr.get("mobile_phone") ) #type: ignore
            ghl_phone = notary_phone if notary_phone else contact_phone 
            print("Creating new contact...")
            contact = {
                "firstName": client_user.get("first_name") if client_user.get("first_name") else order_obj.contact_first_name_sched,
                "lastName": client_user.get("last_name") if client_user.get("last_name") else order_obj.contact_last_name_sched,
                # "name": contact_name,
                "locationId": token_obj.LocationId,
                "email": contact_email,
                "phone": ghl_phone,
                "country": "US",  
                "type": "customer"  
            }
            contact_data, status = ContactServices.post_contact(token_obj.LocationId, contact)
            print(f"Contact creation status: {status}")
            
            if status != 201:
                contact_id = contact_data.get("meta", {}).get("contactId", None)
                print(f"Contact creation failed with status {status}. Attempting to retrieve existing contact by ID: {contact_id}")
                if contact_id:
                    contact_data = ContactServices.get_contact(token_obj.LocationId, contact_id)
                    contact_data["id"] = contact_id
                    # print(f"Contact creation conflicted with: {contact_data.get('id')} Using {json.dumps(contact_data, indent=4)}")
            ContactServices.save_contact(contact_data)
        
        print("=== ABOUT TO CALL BUILD_INVOICE_PAYLOAD ===")
        print(f"Parameters: order_obj={order_obj.id}, contact={contact_data.get('id', 'Unknown')}, location_id={token_obj.LocationId}")
        
        invoice_payload, notary_order = build_invoice_payload(
            order_obj, contact=contact_data, location_id=token_obj.LocationId,
            session_obj=obj, client_user=client_user
        )
        
        print("=== BUILD_INVOICE_PAYLOAD COMPLETED ===")
        print(f"Invoice payload returned: {invoice_payload is not None}")
        
        if not invoice_payload:
            print("ERROR: build_invoice_payload returned None")
            return None
        else:
            print("Calling InvoiceServices.post_invoice...")
            response = InvoiceServices.post_invoice(token_obj.LocationId, invoice_payload)
            # print(f"Invoice response: {json.dumps(response, indent=4)}")
            
            if response:
                print("Invoice created successfully, updating order...")
                order_obj.location_id = token_obj.LocationId
                order_obj.invoice_id = response.get("_id")
                order_obj.save()
                print(f"Order updated with invoice_id: {order_obj.invoice_id}")
            else:
                print("Failed to create invoice, skipping sending and payment recording.")
                return None
                
            print("Sending invoice...")
            send_invoice(response)
            print("Recording payment...")
            record_payment(response)
        if payment_intent_id:
            try:
                pi = stripe.PaymentIntent.retrieve(payment_intent_id)
                existing_metadata = pi.metadata or {}
                order_id = str(notary_order.get("data", {}).get("order_id"))
                new_metadata = {
                    **existing_metadata,
                    "notarydash_order_id":order_id,
                }
                stripe.PaymentIntent.modify(payment_intent_id, metadata=new_metadata)
                print(f"✅ Metadata updated for PaymentIntent {payment_intent_id}")
            except Exception as e:
                print(f"❌ Failed to update PaymentIntent metadata: {e}")
        else:
            print("⚠️ No payment_intent ID found in session")
    
    except Exception as e:
        print(f"ERROR in handle_checkout_session_completed: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None
    
    print("Creating/updating CheckoutSession...")
    session_obj, created = CheckoutSession.objects.update_or_create(
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
    
    print(f"CheckoutSession {'created' if created else 'updated'}: {session_obj.session_id}")
    print("=== HANDLE_CHECKOUT_SESSION_COMPLETED FINISHED ===")
    
    return session_obj

def build_notary_order(order :Order, inv_data, prd_name, client_user,session_obj):
    
    """
    Build Notary order payload based on given order and contact.

    """
    print(f"=== BUILD NOTARY ORDER DEBUG START ===")
    print(f"Order ID: {order.id}")
    print(f"Order service_type: {order.service_type}")
    print(f"Order total_price: {order.total_price}")
    print(f"Product name: {prd_name}")
    print(f"Product name passed: {prd_name}")
    # print(f"Session obj: {session_obj}")
    # print(f"Client user: {client_user}")
    print(f"Order occupancy_status: {getattr(order, 'occupancy_status', None)}")
    print(f"Order occupancy variables : occupied-{order.occupancy_occupied} vacant-{order.occupancy_vacant}")
    print(f"Order street: {getattr(order, 'streetAddress', None)}")
    print(f"Order city: {getattr(order, 'city', None)}")
    print(f"Order state: {getattr(order, 'state', None)}")
    print(f"Order postalCode: {getattr(order, 'postalCode', None)}")
    print(f"Order contact_phone: {getattr(order, 'contact_phone', None)}")

    
    final_price = session_obj.amount_total/100 if session_obj else 0
  
    company_id = order.company_id
    client_id = order.user_id
    
    payment_intent_id = session_obj.get("payment_intent")
    transaction_details = {
        "transaction_id": payment_intent_id,
    
      
    
    }
    
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
            "order":order,
            "transaction":transaction_details
            }
    )
    

    
    notary_product={
        "client_id": company_id,
        "owner_id": order.owner_id,
        "name": prd_name,
        "pay_to_notary": 0,
        "charge_client": final_price,
        "scanbacks_required": False,
        "attr": {
            "additional_instructions": html_content,
            # "scanbacks_instructions": "alias",
            },
        }
    
    # print(f"Notary product payload: {json.dumps(notary_product, indent=2)}")
    
    prd_response = None
    prd = {}
    print(f"Calling NotaryDashServices.create_products...")
    prd_response = NotaryDashServices.create_products(notary_product)
    
    print(f"Product creation response: {prd_response}")
    if prd_response:
        prd = prd_response.get("data", None)
        # print(f"prd: {json.dumps(prd, indent=4)}")
    else:
        print("ERROR: Product creation failed - no response from NotaryDashServices.create_products")
        
    formatted_datetime = order.preferred_datetime.strftime("%Y-%m-%d %H:%M:%S") if order.preferred_datetime else "TBD"
    print(f"Formatted datetime: {formatted_datetime}")
    notary_order = {
        "client_id": company_id,
        "client_contact_id": client_id,
        "location": {
            "when": "at" if order.preferred_datetime else "TBD",
            
            "on": formatted_datetime,
            "address": {
                "address_1": order.streetAddress or "" ,
                "address_2": order.unit or "",
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
    
    # print(f"Final notary order payload: {json.dumps(notary_order, indent=2)}")
    print(f"Calling NotaryDashServices.create_order...")
    
    ord_response = NotaryDashServices.create_order(notary_order)
    # print(f"Order creation response: {ord_response}")
    
    if ord_response and ord_response.get("data"):
        order_id = str(ord_response.get("data", {}).get("id"))
        print(f"SUCCESS: Notary order created with ID: {order_id}")
        inv_data["invoiceNumber"] = order_id
        print(f"Updated inv_data with invoiceNumber: {order_id}")
        print(f"=== BUILD NOTARY ORDER DEBUG END (SUCCESS) ===")
        return inv_data, ord_response
    else:
        print(f"ERROR: Notary order creation failed")
        # print(f"Response details: {json.dumps(ord_response, indent=2) if ord_response else 'None'}")
        print(f"=== BUILD NOTARY ORDER DEBUG END (FAILURE) ===")
        return None, None
        
def build_invoice_payload(order: Order , contact, location_id, session_obj,client_user):
    """
    Build JSON payload for invoice based on given order.
    """
    print(f"=== BUILD INVOICE PAYLOAD DEBUG START ===")
    print(f"Order ID: {order.id}")
    print(f"Order service_type: {order.service_type}")
    print(f"Location ID: {location_id}")
    # print(f"Contact: {contact}")
    # print(f"Session obj: {session_obj}")
    # print(f"Client user: {client_user}")

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
    notary_product_names = []
    session_total_price = session_obj.amount_total/100 if session_obj else 0
    total_bundle_price = 0
    total_ala_price = 0


    print(f"Building invoice items for order {order.id} (type: {order.service_type})")

    # 🟩 1. Always include Bundles if any
    bundles = order.bundles.all()
    if bundles.exists():
        print(f"Found {bundles.count()} bundles for order")

        for bundle in bundles:
            print(f"Processing bundle: {bundle.name} (${bundle.price})")
            total_bundle_price += float(bundle.price or 0)

            items.append(build_item(
                name=bundle.name,
                description=bundle.description,
                price=bundle.price
            ))
            notary_product_names.append(bundle.name)

    # 🟦 2. Include A La Carte services if any
    services = order.a_la_carte_services.all()
    if services.exists():
        print(f"Found {services.count()} A La Carte services")

        for service in services:
            for item in service.items.all():
                submenu_parts = []
                for sub in item.submenu_items.all():
                    if sub.value > 0:
                        label = f"{sub.label} X{sub.value}" if sub.value > 1 else sub.label
                        submenu_parts.append(label)

                # Selected options
                selected_options = item.options.filter(value=True).values_list("label", flat=True)

                # Build product name
                title_parts = [item.title]
                if submenu_parts:
                    title_parts.append(" + ".join(submenu_parts))

                option_suffix = f" ({' + '.join(selected_options)})" if selected_options else ""
                product_name = f"{' + '.join(title_parts)}{option_suffix}"

                price_value = item.price or item.base_price or 0
                total_ala_price += float(price_value)

                items.append(build_item(
                    name=product_name,
                    description=item.subtitle or service.title,
                    price=price_value
                ))
                notary_product_names.append(item.item_id)

    # 🟥 3. Handle "mixed" automatically
    if bundles.exists() and services.exists():
        order.service_type = "mixed"
        print(f"Order {order.id} contains both bundles and A La Carte — set as mixed")

    elif bundles.exists():
        order.service_type = "bundled"
    elif services.exists():
        order.service_type = "a_la_carte"

    # 🧮 4. Fallback / combined summary if no line items
    if not items:
        print("WARNING: No bundle or A La Carte items found — adding fallback line")
        items.append(build_item(
            name="Custom Order",
            description=f"{order.service_type.title()} Service",
            price=order.total_price or session_total_price or 0
        ))
        notary_product_names.append("Custom Order")

    # 🧾 5. Compute combined totals
    combined_total = total_bundle_price + total_ala_price
    print(f"Bundle Total: {total_bundle_price}, ALC Total: {total_ala_price}, Combined: {combined_total}") 
    if order.order_protection ==True:
        notary_product_names.append("with Protection")
        items.append(build_item(
                    name="Order Protection",
                    description="Optional Order Protection",
                    price=order.order_protection_price
                ))

    notary_product_names = " ".join(notary_product_names)
    print(f"Final notary product names: {notary_product_names}")
    print(f"Total items created: {len(items)}")

    
    address={
            "addressLine1": order.streetAddress  or "",
            "addressLine2": order.unit or "",
            "city": order.city or "",
            "state": order.state or "",
            "countryCode": "US",
            "postalCode": order.postal_code or ""
        }
    try:
        contact_ph = format_phone_number(order.contact_phone_sched)
    except:
        contact_ph = order.contact_phone_sched
    print(f"Formatted contact phone: {contact_ph}")
    print(f"discount amount: {session_obj.total_details.amount_discount}")
    
    print(f"Building invoice data structure...")
    invoice_data = {
        "altId": location_id,
        "altType": "location",
        "name": f"{order.company_name} - {order.get_service_type_display() if order.service_type !="mixed" else "Bundle+A La Carte"} ",
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
        "title": f"Invoice -{order.get_service_type_display() if order.service_type !="mixed" else "Bundle+A La Carte"}",
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
        "liveMode": not settings.STRIPE_TEST,
        "invoiceNumberPrefix": "INV-",
        "paymentMethods": {
            "stripe": {}
        },
        "attachments": []
    }
    
    print(f"Initial invoice data created with invoiceNumber: {invoice_data['invoiceNumber']}")
    print(f"Calling build_notary_order with product names: {notary_product_names}")
    
    invoice_data, notary_order = build_notary_order(order, inv_data=invoice_data, prd_name=notary_product_names, client_user=client_user, session_obj=session_obj)
    
    if invoice_data:
      
        print(f"Final invoice data has invoiceNumber: {invoice_data.get('invoiceNumber')}")
        print(f"=== BUILD INVOICE PAYLOAD DEBUG END (SUCCESS) ===")
    else:
        print("ERROR: build_notary_order returned None")
        print(f"=== BUILD INVOICE PAYLOAD DEBUG END (FAILURE) ===")
        
    return invoice_data, notary_order

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

