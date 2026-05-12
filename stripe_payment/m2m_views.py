from rest_framework import generics, filters
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from .models import NotaryClientCompany, NotaryUser
from .serializer import NotaryClientCompanySerializer, NotaryUserSerializer
from core.permissions import IsM2MClient

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

from rest_framework import viewsets, status
from rest_framework.response import Response

class NotaryClientCompanyM2MViewSet(viewsets.ReadOnlyModelViewSet):
    """
    M2M ViewSet for NotaryClientCompany.
    Provides `list` and `retrieve` actions.
    """
    queryset = NotaryClientCompany.objects.all().order_by('-created_at')
    serializer_class = NotaryClientCompanySerializer
    permission_classes = [IsM2MClient]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['type', 'active', 'owner_id', 'parent_company_id']
    search_fields = ['company_name', 'stripe_customer_id', 'address']
    ordering_fields = ['created_at', 'updated_at', 'company_name']


class NotaryUserM2MViewSet(viewsets.ReadOnlyModelViewSet):
    """
    M2M ViewSet for NotaryUser.
    Provides `list`, `retrieve`, and `create` actions.
    """
    queryset = NotaryUser.objects.all().order_by('-created_at')
    serializer_class = NotaryUserSerializer
    permission_classes = [IsM2MClient]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['type', 'disabled', 'is_admin', 'last_company']
    search_fields = ['email', 'first_name', 'last_name', 'name']
    ordering_fields = ['created_at', 'last_login_at', 'email']

    def create(self, request, *args, **kwargs):
        from stripe_payment.services import NotaryDashServices
        from stripe_payment.utils import create_stripe_customer
        from rest_framework.response import Response
        from rest_framework import status
        
        data = request.data
        email = data.get("email")
        company_name = data.get("company")
        
        if not email:
            return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Handle Company (Client)
        client_obj = None
        client_id = None
        
        if company_name:
            client_obj = NotaryClientCompany.objects.filter(company_name=company_name).first()
            
            if client_obj:
                client_id = client_obj.id
            else:
                # Create Client in NotaryDash
                client_payload = {
                    "company_name": company_name,
                    "address": {
                        "street": data.get("address"),
                        "city": data.get("city"),
                        "state": data.get("state"),
                        "postal_code": data.get("zip_code"),
                        "country": data.get("country")
                    }
                }
                client_response = NotaryDashServices.create_client(client_payload)
                
                if client_response and client_response.get("data"):
                    client_data = client_response.get("data")
                    client_id = client_data.get("id")
                    
                    # Save locally
                    client_obj, _ = NotaryClientCompany.objects.update_or_create(
                        id=client_id,
                        defaults={
                            "owner_id": client_data.get("owner_id"),
                            "parent_company_id": client_data.get("parent_company_id"),
                            "type": client_data.get("type"),
                            "company_name": client_data.get("company_name"),
                            "parent_company_name": client_data.get("parent_company_name"),
                            "attr": client_data.get("attr", {}),
                            "address": client_data.get("address", {}),
                            "deleted_at": client_data.get("deleted_at"),
                            "created_at": client_data.get("created_at"),
                            "updated_at": client_data.get("updated_at"),
                            "active": client_data.get("active", True),
                        }
                    )
                    
                    # Create Stripe Customer for new client
                    if not client_obj.stripe_customer_id:
                        stripe_customer = create_stripe_customer(client_obj.company_name, email=email)
                        if stripe_customer:
                            client_obj.stripe_customer_id = stripe_customer.id
                            client_obj.save()
                else:
                    return Response({"message": "Failed to create client/company in NotaryDash"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not client_id:
             return Response({"message": "Company is required or failed to be created"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Handle User
        user_payload = {
            "user": {
                "first_name": data.get("first_name"),
                "last_name": data.get("last_name"),
                "email": email,
                "photo_url": data.get("avatar_url"),
                "attr": {
                    "phone": data.get("phone"),
                    "address": data.get("address"),
                    "city": data.get("city"),
                    "state": data.get("state"),
                    "zip_code": data.get("zip_code"),
                    "country": data.get("country"),
                    "timezone": data.get("timezone"),
                    "m2m_id": data.get("id") # Store original UUID if useful
                }
            },
            "email_credentials": True, # Ensure credentials can be generated/sent
            "teams": [{"id": data.get("team_id")}] if data.get("team_id") else []
        }

        user_response = NotaryDashServices.create_client_user(client_id, user_payload)
        
        if user_response and user_response.get("data"):
            user_data = user_response.get("data")
            user_id = user_data.get("id")
            
            if user_id:
                # Determine if first user
                is_first_user = not NotaryUser.objects.filter(last_company_id=client_id).exists()
                
                user_obj, _ = NotaryUser.objects.update_or_create(
                    id=user_id,
                    defaults={
                        "first_name": user_data.get("first_name"),
                        "last_name": user_data.get("last_name"),
                        "name": user_data.get("name") or f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                        "email": user_data.get("email"),
                        "photo_url": user_data.get("photo_url"),
                        "country_code": user_data.get("country_code"),
                        "tz": user_data.get("tz"),
                        "attr": user_data.get("attr", {}),
                        "last_login_at": user_data.get("last_login_at"),
                        "last_ip": user_data.get("last_ip"),
                        "last_company_id": user_data.get("last_company_id", client_id),
                        "email_unverified": user_data.get("email_unverified"),
                        "disabled": user_data.get("disabled"),
                        "deleted_at": user_data.get("deleted_at"),
                        "created_at": user_data.get("created_at"),
                        "updated_at": user_data.get("updated_at"),
                        "type": user_data.get("type"),
                    }
                )
                
                if is_first_user:
                    user_obj.is_admin = True
                    user_obj.save()
                    
                serializer = self.get_serializer(user_obj)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response({"message": "Failed to create user in NotaryDash"}, status=status.HTTP_400_BAD_REQUEST)


class NotaryUserQueryM2MViewSet(viewsets.ViewSet):
    """
    M2M list-only endpoint (same permission as ``OrderM2MViewSet``).

    GET: paginated ``NotaryUser`` rows. Optional query filters (AND together):

    - ``email`` — case-insensitive exact match
    - ``company_id`` or ``last_company`` — ``NotaryUser.last_company_id``
    - ``partner_id`` — Tolt ``Partner`` id (string)
    """

    permission_classes = [IsM2MClient]
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        qs = (
            NotaryUser.objects.all()
            .select_related("last_company", "partner", "typeform_partner_mapping")
            .order_by("-created_at")
        )
        email = request.query_params.get("email")
        company_id = request.query_params.get("company_id") or request.query_params.get(
            "last_company"
        )
        partner_id = request.query_params.get("partner_id")

        if email:
            qs = qs.filter(email__iexact=email.strip())
        if company_id is not None and str(company_id).strip() != "":
            try:
                qs = qs.filter(last_company_id=int(company_id))
            except (TypeError, ValueError):
                return Response(
                    {"detail": "company_id / last_company must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if partner_id is not None and str(partner_id).strip() != "":
            qs = qs.filter(partner_id=str(partner_id).strip())

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = NotaryUserSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
#  M2M Order View — receives Supabase DatabaseOrder, saves to Django models,
#  then posts to NotaryDash.
# ─────────────────────────────────────────────────────────────────────────────

import json
import re
import traceback
from decimal import Decimal
from datetime import datetime

from rest_framework import viewsets, status
from rest_framework.response import Response
from django.template.loader import render_to_string
from django.utils.timezone import make_aware
from django.utils.dateparse import parse_datetime

from .models import Order, Bundle, ALaCarteService, ALaCarteItem


def _parse_json_field(field, fallback=None):
    """Parse a JSON string field, returning the parsed value or fallback."""
    if fallback is None:
        fallback = {} if not isinstance(fallback, list) else []
    if not field:
        return fallback
    if isinstance(field, str):
        try:
            return json.loads(field)
        except (json.JSONDecodeError, ValueError):
            return fallback
    return field


def _resolve_notary_ids(data):
    """
    Resolve Supabase user_id / organization_id to NotaryDash IDs.

    The edge function now sends nd_user_id and nd_company_id directly in the
    payload (looked up from the Supabase users table).  When present we use
    them to fetch the local NotaryUser / NotaryClientCompany by PK.  If they
    are absent we fall back to the original attr__m2m_id lookup.

    Returns (company_id, nd_user_id, owner_id, client_team_id, company_name, error_msg).
    """
    supabase_user_id = data.get("user_id")
    direct_nd_user_id = data.get("nd_user_id")
    direct_nd_company_id = data.get("nd_company_id")

    if not supabase_user_id:
        return None, None, None, None, None, "user_id is required"

    notary_user = None

    # ── Try direct NotaryDash IDs first (provided by edge function) ──
    if direct_nd_user_id:
        try:
            notary_user = NotaryUser.objects.get(id=direct_nd_user_id)
        except NotaryUser.DoesNotExist:
            print(f"WARN: nd_user_id={direct_nd_user_id} not found locally, falling back to attr lookup")

    # ── Fallback: lookup by attr__m2m_id ──
    if not notary_user:
        notary_user = NotaryUser.objects.filter(attr__m2m_id=supabase_user_id).first()

    if not notary_user:
        return None, None, None, None, None, f"No NotaryUser found for user_id={supabase_user_id} / nd_user_id={direct_nd_user_id}"

    nd_user_id = str(notary_user.id)
    company_id = None
    company_name = None
    client_team_id = None

    # ── Resolve company — prefer direct nd_company_id ──
    if direct_nd_company_id:
        try:
            company = NotaryClientCompany.objects.get(id=direct_nd_company_id)
            company_id = str(company.id)
            company_name = company.company_name
        except NotaryClientCompany.DoesNotExist:
            print(f"WARN: nd_company_id={direct_nd_company_id} not found locally, trying other methods")

    # ── Fallback: resolve from organization_id attr ──
    if not company_id:
        supabase_org_id = data.get("organization_id")
        if supabase_org_id:
            company = NotaryClientCompany.objects.filter(attr__m2m_id=supabase_org_id).first()
            if company:
                company_id = str(company.id)
                company_name = company.company_name

    # ── Fallback: use the user's last_company ──
    if not company_id and notary_user.last_company_id:
        company_id = str(notary_user.last_company_id)
        try:
            company = NotaryClientCompany.objects.get(id=notary_user.last_company_id)
            company_name = company.company_name
        except NotaryClientCompany.DoesNotExist:
            pass

    if not company_id:
        return None, None, None, None, None, "Could not resolve NotaryDash company_id"

    # owner_id = nd_user_id (the user who placed the order)
    owner_id = nd_user_id

    # Derive team_id from user's attr if available
    client_team_id = notary_user.attr.get("team_id") if isinstance(notary_user.attr, dict) else None

    return company_id, nd_user_id, owner_id, client_team_id, company_name, None


def _map_access_methods(access_methods):
    """Map Supabase accessMethods list to Django boolean fields."""
    methods = access_methods or []
    return {
        "access_lock_box": "lockbox" in methods,
        "access_app_lock_box": "app_lockbox" in methods,
        "access_meet_contact": "meet_contact" in methods,
        "access_door_code": "door_code" in methods,
        "access_hidden_key": "hidden_key" in methods,
        "access_community_access": "community_access" in methods,
    }


def _build_preferred_datetime(scheduled_date, scheduled_time, scheduled_timezone):
    """
    Combine scheduled_date + scheduled_time into a timezone-aware datetime.
    Returns (datetime_or_None, is_tbd).
    """
    if not scheduled_date or scheduled_time in [None, "", "TBD"]:
        return None, True

    try:
        dt_str = f"{scheduled_date} {scheduled_time}" if scheduled_time and scheduled_time != "TBD" else scheduled_date
        dt = parse_datetime(dt_str)
        if dt is None:
            # Try basic date-only parse
            dt = datetime.strptime(scheduled_date, "%Y-%m-%d")
        if dt and not dt.tzinfo:
            dt = make_aware(dt)
        return dt, False
    except Exception:
        return None, True


def _create_order_from_supabase(data, company_id, nd_user_id, owner_id, client_team_id, company_name):
    """
    Map Supabase DatabaseOrder payload to a Django Order and save it.
    """
    property_info = _parse_json_field(data.get("property_info"), {})
    property_access = _parse_json_field(data.get("property_access"), {})
    appointment_contact = _parse_json_field(data.get("appointment_confirm_contact"), {})
    reschedule_contact = _parse_json_field(data.get("reschedule_contact"), {})
    cc_emails = _parse_json_field(data.get("cc_emails"), [])

    # Access method booleans
    access_flags = _map_access_methods(property_access.get("accessMethods"))

    # Occupancy
    property_status = data.get("property_status", "")
    occupancy_vacant = property_status == "vacant"
    occupancy_occupied = property_status in ["occupied", "owner_occupied", "tenant_occupied"]

    # Schedule
    preferred_datetime, is_tbd = _build_preferred_datetime(
        data.get("scheduled_date"),
        data.get("scheduled_time"),
        data.get("scheduled_timezone"),
    )

    # Determine service_type from what's present
    selected_bundles = _parse_json_field(data.get("selected_bundles"), [])
    selected_services = _parse_json_field(data.get("selected_services"), [])
    has_bundles = len(selected_bundles) > 0
    has_services = len(selected_services) > 0
    if has_bundles and has_services:
        service_type = "mixed"
    elif has_bundles:
        service_type = "bundled"
    elif has_services:
        service_type = "a_la_carte"
    else:
        service_type = "bundled"  # default

    # CC emails → newline-separated string
    order_status_emails = "\n".join(cc_emails) if cc_emails else None

    # Discount from bundle_discount
    discount_amount = Decimal(str(data.get("bundle_discount", "0.00")))

    order = Order.objects.create(
        unit_type=data.get("unit_type", "single"),
        streetAddress=property_info.get("streetAddress", ""),
        unit=property_info.get("unitAptSuite", ""),
        city=property_info.get("city", ""),
        state=property_info.get("state", ""),
        postal_code=property_info.get("postalCode", ""),
        number_of_units=property_info.get("numberOfUnits"),
        address=f"{property_info.get('streetAddress', '')} {property_info.get('unitAptSuite', '')}".strip(),

        service_type=service_type,
        total_price=Decimal(str(data.get("total", "0.00"))),

        # Occupancy & Access
        occupancy_vacant=occupancy_vacant,
        occupancy_occupied=occupancy_occupied,
        occupancy_status=property_status,
        **access_flags,
        lock_box_code=property_access.get("lockboxCode", ""),
        lock_box_location=property_access.get("lockboxLocation", ""),
        app_lock_link=property_access.get("appLink", ""),
        door_code_value=property_access.get("doorCode", ""),
        hidden_key_directions=property_access.get("hiddenKeyDirections", ""),
        community_access_instructions=property_access.get("communityInstructions", ""),
        sp_instruction=property_access.get("specialInstructions", ""),

        # Meet contact (from property_access)
        contact_first_name=property_access.get("contactFirstName", ""),
        contact_last_name=property_access.get("contactLastName", ""),
        contact_phone=property_access.get("contactPhone", ""),

        # Scheduling
        preferred_datetime=preferred_datetime,
        preferred_timezone=data.get("scheduled_timezone"),
        tbd=is_tbd,

        # Appointment confirmation contact → sched contact fields
        contact_first_name_sched=appointment_contact.get("firstName", ""),
        contact_last_name_sched=appointment_contact.get("lastName", ""),
        contact_phone_sched=appointment_contact.get("phone", ""),
        contact_email_sched=appointment_contact.get("email", "") or None,
        point_of_contact=data.get("appointment_confirm_with"),
        appointment_confirmed=data.get("appointment_confirm_with") == "me",

        # Rescheduling
        rescheduling_option=data.get("reschedule_preference"),
        contact_first_name_resched=reschedule_contact.get("firstName", ""),
        contact_last_name_resched=reschedule_contact.get("lastName", ""),
        contact_phone_resched=reschedule_contact.get("phone", ""),

        # IDs
        company_id=company_id,
        user_id=nd_user_id,
        owner_id=owner_id,
        client_team_id=client_team_id,
        company_name=company_name,

        # Order flags
        order_protection=data.get("order_protection", False),
        order_status_emails=order_status_emails,
        discount_amount=discount_amount,

        # Use order_number as an external reference via stripe_session_id field
        stripe_session_id=data.get("order_number"),

        # Mark as processing immediately
        processing_status="processing",

        # M2M orders are external (V2 app)
        is_external_odr=True,
    )

    return order, selected_bundles, selected_services


def _create_bundles(order, selected_bundles):
    """Create Bundle records from Supabase selected_bundles (with populated services)."""
    product_names = []

    for bundle_data in selected_bundles:
        discount_pct = Decimal(str(
            bundle_data.get("discount_percentage")
            or bundle_data.get("discountPercentage")
            or 0
        ))

        # Calculate base_price from populated services
        services = bundle_data.get("services", [])
        base_price = sum(Decimal(str(s.get("price", 0))) for s in services)

        # Discounted price
        if discount_pct > 0:
            price = base_price * (1 - discount_pct / 100)
        else:
            price = base_price

        bundle = Bundle.objects.create(
            order=order,
            name=bundle_data.get("name", ""),
            description=bundle_data.get("description", ""),
            base_price=base_price,
            price=price.quantize(Decimal("0.01")),
        )
        product_names.append(bundle.name)

    return product_names


def _create_a_la_carte_services(order, selected_services):
    """Create ALaCarteService + ALaCarteItem records from Supabase selected_services."""
    product_names = []

    for svc_data in selected_services:
        svc_id = svc_data.get("id") or svc_data.get("service_id") or ""
        svc_name = svc_data.get("name", "Service")
        svc_desc = svc_data.get("description", "")
        svc_price = Decimal(str(svc_data.get("price", 0)))
        svc_category = svc_data.get("category", "")

        service = ALaCarteService.objects.create(
            order=order,
            service_id=svc_category or svc_id,
            title=svc_name,
            subtitle=svc_desc,
        )

        ALaCarteItem.objects.create(
            service=service,
            item_id=svc_id,
            title=svc_name,
            subtitle=svc_desc,
            price=svc_price,
            base_price=svc_price,
        )

        product_names.append(svc_name)

    return product_names


def _post_to_notarydash(order, product_names):
    """
    Adapted from build_notary_order in views.py — creates product + order in
    NotaryDash, fires signal, and sends to Keap.  Skips invoice data and
    Stripe event objects.
    """
    from stripe_payment.services import NotaryDashServices
    from core.services import KeapSocketService

    print(f"=== M2M BUILD NOTARY ORDER START ===")
    print(f"Order ID: {order.id}, service_type: {order.service_type}")

    prd_name = " ".join(product_names) if product_names else "Supabase Order"
    final_price = float(order.total_price or 0) + float(order.order_protection_price or 0)

    # ── Render HTML for NotaryDash instructions (no invoice_data needed) ──
    order_status_emails_list = order.order_status_emails.split('\n') if order.order_status_emails else []

    html_content = render_to_string(
        "order_product_detail.html",
        context={"order": order}
    ).replace("\n", "").replace('"', "'")

    order_html_content = render_to_string(
        "order_detail.html",
        context={
            "order": order,
            "transaction": {"transaction_id": order.stripe_session_id or "M2M"},
            "order_status_emails_list": order_status_emails_list,
        }
    ).replace("\n", "").replace('"', "'")

    # ── Create NotaryDash Product ──
    notary_product = {
        "client_id": order.company_id,
        "owner_id": order.owner_id,
        "name": prd_name,
        "pay_to_notary": 0,
        "charge_client": final_price,
        "scanbacks_required": False,
        "attr": {
            "additional_instructions": html_content,
        },
    }

    prd_response = None
    prd = {}
    print(f"Calling NotaryDashServices.create_products...")
    prd_response = NotaryDashServices.create_products(notary_product)

    if prd_response:
        prd = prd_response.get("data") or {}
    else:
        print("ERROR: Product creation failed")

    # ── Create NotaryDash Order ──
    formatted_datetime = (
        order.preferred_datetime.strftime("%Y-%m-%d %H:%M:%S")
        if order.preferred_datetime else "TBD"
    )

    notary_order = {
        "client_id": order.company_id,
        "client_contact_id": order.user_id,
        "client_team_id": order.client_team_id,
        "owner_id": order.user_id,
        "location": {
            "when": "at" if order.preferred_datetime else "TBD",
            "on": formatted_datetime,
            "address": {
                "address_1": order.streetAddress or "",
                "address_2": order.unit or "",
                "city": order.city or "",
                "zip": order.postal_code or "",
                "state": order.state or "",
            },
        },
        "signer": {
            "first_name": order.contact_first_name_sched or "",
            "last_name": order.contact_last_name_sched or "",
            "mobile_phone": (
                re.sub(r"[^\d+]", "", str(order.contact_phone_sched))
                if order.contact_phone_sched else ""
            ),
        },
        "product": {
            "parent_id": prd.get("id") if prd_response else None,
            "name": prd.get("name") if prd_response else prd_name,
            "pay_to_notary": prd.get("pay_to_notary", 0) if prd_response else 0,
            "charge_client": (
                prd.get("charge_client", final_price)
                if prd_response else final_price
            ),
            "scanbacks_required": True,
        },
        "attr": {
            "special_instructions": order_html_content or order.sp_instruction,
        },
        "team": {"id": 3680},
    }

    if formatted_datetime != "TBD":
        notary_order["location"]["appt_time"] = formatted_datetime

    if order.cosigner_first_name and order.cosigner_last_name:
        notary_order["cosigner"] = {
            "first_name": order.cosigner_first_name or "",
            "last_name": order.cosigner_last_name or "",
            "mobile_phone": (
                re.sub(r"[^\d+]", "", str(order.cosigner_phone))
                if order.cosigner_phone else ""
            ),
            "type": "cosigner",
        }

    print(f"Calling NotaryDashServices.create_order...")
    ord_response = NotaryDashServices.create_order(notary_order)

    if ord_response and ord_response.get("data"):
        order_id_num = str(ord_response["data"].get("order_id"))
        order.notary_order_id = order_id_num
        order.processing_status = "completed"
        order.save()
        print(f"SUCCESS: Notary order created with ID: {order_id_num}")

        # Fire signal
        from .signals import notary_order_created
        notary_order_created.send(
            sender=order.__class__,
            notary_order=notary_order,
            order_response=ord_response,
        )

        # Send to Keap
        keap_response = KeapSocketService.send_data("gsync/unix-test/", ord_response)
        if keap_response and "error" not in keap_response:
            print(f"SUCCESS: Keap send successful")
        else:
            print(f"ERROR: Keap send failed")

        print(f"=== M2M BUILD NOTARY ORDER END (SUCCESS) ===")
        return ord_response
    else:
        order.processing_status = "failed"
        order.save(update_fields=["processing_status"])
        print(f"ERROR: Notary order creation failed")
        print(f"=== M2M BUILD NOTARY ORDER END (FAILURE) ===")
        return None


class OrderM2MViewSet(viewsets.ViewSet):
    """
    M2M ViewSet for processing Supabase orders.
    Receives a DatabaseOrder payload, saves to Order + Bundle + ALaCarteService
    models, then posts the order to NotaryDash.
    """
    permission_classes = [IsM2MClient]

    def create(self, request, *args, **kwargs):
        data = request.data
        print(f"=== M2M CREATE ORDER START ===")
        print(f"Received order: id={data.get('id')}, order_number={data.get('order_number')}, status={data.get('status')}")

        # ── 1. Resolve NotaryDash IDs from Supabase UUIDs ──
        company_id, nd_user_id, owner_id, client_team_id, company_name, err = _resolve_notary_ids(data)
        if err:
            print(f"ERROR resolving IDs: {err}")
            return Response(
                {"message": err, "status": "error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # ── 2. Create Order ──
            order, selected_bundles, selected_services = _create_order_from_supabase(
                data, company_id, nd_user_id, owner_id, client_team_id, company_name
            )
            print(f"Order created: pk={order.id}")

            # ── 3. Create Bundles ──
            bundle_names = _create_bundles(order, selected_bundles)
            print(f"Bundles created: {bundle_names}")

            # ── 4. Create A La Carte Services ──
            service_names = _create_a_la_carte_services(order, selected_services)
            print(f"A La Carte services created: {service_names}")

            # ── 5. Aggregate product names for NotaryDash ──
            product_names = bundle_names + service_names
            if order.order_protection and order.order_protection_price and order.order_protection_price > 0:
                product_names.append("+Prt")

            # ── 6. Post to NotaryDash ──
            ord_response = _post_to_notarydash(order, product_names)

            if ord_response:
                return Response(
                    {
                        "message": "Order created and posted to NotaryDash",
                        "order_id": order.id,
                        "notary_order_id": order.notary_order_id,
                        "status": "success",
                    },
                    status=status.HTTP_201_CREATED,
                )
            else:
                return Response(
                    {
                        "message": "Order saved but NotaryDash posting failed",
                        "order_id": order.id,
                        "status": "partial",
                    },
                    status=status.HTTP_207_MULTI_STATUS,
                )

        except Exception as e:
            print(f"ERROR in M2M create order: {e}")
            print(traceback.format_exc())
            return Response(
                {"message": f"Failed to process order: {str(e)}", "status": "error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
