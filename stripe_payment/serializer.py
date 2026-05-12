from rest_framework import serializers, viewsets, mixins
from .models import (
    Order, ALaCarteService,
    StripeCharge, CheckoutSession, Invoice, BusinessDetails, Discount,
    NotaryUser, NotaryClientCompany,
    Bundle, BundleOption, BundleModalOption,
    ALaCarteItem, ALaCarteOption, ALaCarteSubMenuItem,
    ALaCarteItemModalOption, ALaCarteItemDisclosure
)


class NotaryClientCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaryClientCompany
        fields = [
            "id", "company_name", "type", "active", 
            "stripe_customer_id", "stripe_default_payment_method",
            "created_at", "updated_at"
        ]

class NotaryUserSerializer(serializers.ModelSerializer):
    last_company = NotaryClientCompanySerializer(read_only=True)

    class Meta:
        model = NotaryUser
        fields = [
            "id", "email", "first_name", "last_name", "name",
            "photo_url", "is_admin", "type", "disabled",
            "country_code", "tz", "created_at", "last_login_at",
            "last_company",
            "last_company_id",
            "partner_id",
            "typeform_partner_mapping_id",
        ]

class BundleOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BundleOption
        fields = ["id", "name", "description", "value", "price"]

class BundleModalOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BundleModalOption
        fields = ["id", "name", "description", "value", "price"]

class BundleSerializer(serializers.ModelSerializer):
    options = BundleOptionSerializer(many=True, read_only=True)
    modal_options = BundleModalOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Bundle
        fields = ["id", "name", "description", "base_price", "price", "options", "modal_options"]


class ALaCarteOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ALaCarteOption
        fields = ["id", "option_id", "label", "value", "disabled"]

class ALaCarteSubMenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ALaCarteSubMenuItem
        fields = ["id", "submenu_item_id", "label", "type", "value"]

class ALaCarteItemModalOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ALaCarteItemModalOption
        fields = ["id", "name", "description", "value", "price"]

class ALaCarteItemDisclosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ALaCarteItemDisclosure
        fields = ["id", "name", "value"]

class ALaCarteItemSerializer(serializers.ModelSerializer):
    options = ALaCarteOptionSerializer(many=True, read_only=True)
    submenu_items = ALaCarteSubMenuItemSerializer(many=True, read_only=True)
    modal_options = ALaCarteItemModalOptionSerializer(many=True, read_only=True)
    disclosures = ALaCarteItemDisclosureSerializer(many=True, read_only=True)

    class Meta:
        model = ALaCarteItem
        fields = [
            "id", "item_id", "title", "subtitle", "price", "base_price", 
            "protection_invalid", "options_type", "minimum_required",
            "options", "submenu_items", "modal_options", "disclosures"
        ]

class ALaCarteServiceSerializer(serializers.ModelSerializer):
    items = ALaCarteItemSerializer(many=True, read_only=True)

    class Meta:
        model = ALaCarteService
        fields = [
            "id", "service_id", "title", "subtitle", "form_title", 
            "form_description", "items"
        ]


class OrderSerializer(serializers.ModelSerializer):
    a_la_carte_services = ALaCarteServiceSerializer(many=True, read_only=True)
    bundles = BundleSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "unit_type", "address", "streetAddress", "city", "state",
            "postal_code", "unit", "service_type", "number_of_units",
            # Bundled service fields
            # "bundle_group", "bundle_item", 
            "bundles",
            
            "total_price", 
            
            # Occupancy & Access
            "occupancy_status",
            "access_lock_box", "lock_box_code", "lock_box_location", 
            "access_app_lock_box", "app_lock_link",
            "access_meet_contact", "access_hidden_key", "hidden_key_directions", 
            "access_community_access", "community_access_instructions", 
            "access_door_code", "door_code_value",
            
            # Scheduling & Contact
            "preferred_datetime", "preferred_timezone",
            "company_id", "user_id", "owner_id", "client_team_id", "notary_order_id",
            
            "point_of_contact", 
            "contact_first_name_sched", "contact_last_name_sched", 
            "contact_phone_sched_type", "contact_phone_sched", "contact_email_sched",
            
            "contact_first_name", "contact_last_name", 
            "contact_phone_type", "contact_phone", "contact_email",
            
            "cosigner_first_name", "cosigner_last_name", 
            "cosigner_phone_type", "cosigner_phone", "cosigner_email",
            
            "company_name", 
            # Consent
            "accepted_at", "tbd", "sp_instruction",
            
            # Stripe Relationship
            "stripe_session_id", "stripe_intent_id", "location_id",
            
            "coupon_code", "coupon_id", "coupon_percent", "coupon_fixed",
            
            "created_at", "invoice_id", 
            "order_protection", "order_protection_price", 
            "discount_percent", "discount_amount",
            "order_status_emails", "appointment_confirmed",
            
            # Rescheduling
            "rescheduling_option", "contact_first_name_resched", 
            "contact_last_name_resched", "contact_phone_resched",
            "processing_status",
            
            "a_la_carte_services"
        ]


class StripeChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeCharge
        fields = [
            "charge_id", "payment_intent_id", "amount", "currency", "paid",
            "status", "captured", "receipt_url", "customer_email",
            "customer_name", "billing_country", "brand", "last4",
            "exp_month", "exp_year", "network_transaction_id", "created",
            "livemode"
        ]


class CheckoutSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckoutSession
        fields = [
            "session_id", "payment_intent", "amount_subtotal", "amount_total",
            "currency", "payment_status", "customer_email", "customer_name",
            "metadata", "created"
        ]


class BusinessDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessDetails
        fields = ["id", "name", "phone_no"]


class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = ["id", "type", "value"]


class InvoiceSerializer(serializers.ModelSerializer):
    business_details = BusinessDetailsSerializer(read_only=True)
    discount = DiscountSerializer(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "_id", "status", "live_mode", "amount_paid", "alt_id", "alt_type",
            "name", "invoice_number", "currency", "issue_date", "due_date",
            "total", "title", "created_at", "updated_at", "business_details", "discount"
        ]


# ─────────────────────────────────────────────────────────────────────────────
#  SupabaseOrderSerializer — reverse-maps Django Order to V2 Supabase schema
# ─────────────────────────────────────────────────────────────────────────────

class SupabaseOrderSerializer(serializers.Serializer):
    """
    Serializes a Django Order instance into the shape expected by the
    V2 Supabase `orders` table so it can be upserted there.
    """

    unit_type = serializers.CharField()
    property_info = serializers.SerializerMethodField()
    selected_bundles = serializers.SerializerMethodField()
    selected_services = serializers.SerializerMethodField()
    property_access = serializers.SerializerMethodField()
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    scheduled_timezone = serializers.CharField(source="preferred_timezone", default="")
    bundle_subtotal = serializers.SerializerMethodField()
    service_subtotal = serializers.SerializerMethodField()
    bundle_discount = serializers.DecimalField(
        source="discount_amount", max_digits=10, decimal_places=2, default="0.00"
    )
    total = serializers.DecimalField(
        source="total_price", max_digits=10, decimal_places=2, default="0.00"
    )
    status = serializers.SerializerMethodField()
    external_id = serializers.CharField(source="notary_order_id", default=None)
    schedule_preference = serializers.SerializerMethodField()
    property_status = serializers.CharField(source="occupancy_status", default="")
    order_protection = serializers.BooleanField(default=False)
    appointment_confirm_with = serializers.CharField(source="point_of_contact", default="")
    appointment_confirm_contact = serializers.SerializerMethodField()
    reschedule_preference = serializers.CharField(source="rescheduling_option", default="")
    reschedule_contact = serializers.SerializerMethodField()
    cc_emails = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="stripe_session_id", default="")
    company_id = serializers.CharField(default="")
    user_id = serializers.CharField(default="")
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z")

    # ── property_info ──
    def get_property_info(self, obj):
        return {
            "streetAddress": obj.streetAddress or "",
            "unitAptSuite": obj.unit or "",
            "city": obj.city or "",
            "state": obj.state or "",
            "postalCode": obj.postal_code or "",
            "numberOfUnits": obj.number_of_units,
        }

    # ── property_access ──
    def get_property_access(self, obj):
        methods = []
        if obj.access_lock_box:
            methods.append("lockbox")
        if obj.access_app_lock_box:
            methods.append("app_lockbox")
        if obj.access_meet_contact:
            methods.append("meet_contact")
        if obj.access_door_code:
            methods.append("door_code")
        if obj.access_hidden_key:
            methods.append("hidden_key")
        if obj.access_community_access:
            methods.append("community_access")

        return {
            "accessMethods": methods,
            "lockboxCode": obj.lock_box_code or "",
            "lockboxLocation": obj.lock_box_location or "",
            "appLink": obj.app_lock_link or "",
            "doorCode": obj.door_code_value or "",
            "hiddenKeyDirections": obj.hidden_key_directions or "",
            "communityInstructions": obj.community_access_instructions or "",
            "specialInstructions": obj.sp_instruction or "",
            "contactFirstName": obj.contact_first_name or "",
            "contactLastName": obj.contact_last_name or "",
            "contactPhone": obj.contact_phone or "",
        }

    # ── selected_bundles ──
    def get_selected_bundles(self, obj):
        bundles = []
        for b in obj.bundles.all():
            bundles.append({
                "name": b.name,
                "description": b.description or "",
                "base_price": str(b.base_price),
                "price": str(b.price),
            })
        return bundles

    # ── selected_services ──
    def get_selected_services(self, obj):
        services = []
        for svc in obj.a_la_carte_services.all():
            for item in svc.items.all():
                services.append({
                    "id": item.item_id,
                    "name": item.title,
                    "description": item.subtitle or "",
                    "price": str(item.price or 0),
                    "category": svc.service_id or "",
                })
        return services

    # ── schedule fields ──
    def get_scheduled_date(self, obj):
        if obj.preferred_datetime:
            return obj.preferred_datetime.strftime("%Y-%m-%d")
        return None

    def get_scheduled_time(self, obj):
        if obj.tbd or not obj.preferred_datetime:
            return "TBD"
        return obj.preferred_datetime.strftime("%H:%M:%S")

    def get_schedule_preference(self, obj):
        if obj.tbd:
            return "schedule_for_me"
        return "choose_time"

    # ── subtotals ──
    def get_bundle_subtotal(self, obj):
        total = sum(b.base_price for b in obj.bundles.all())
        return str(total)

    def get_service_subtotal(self, obj):
        total = sum(
            item.price or 0
            for svc in obj.a_la_carte_services.all()
            for item in svc.items.all()
        )
        return str(total)

    # ── status ──
    def get_status(self, obj):
        return "order_received"

    # ── contact JSONB fields ──
    def get_appointment_confirm_contact(self, obj):
        return {
            "firstName": obj.contact_first_name_sched or "",
            "lastName": obj.contact_last_name_sched or "",
            "phone": obj.contact_phone_sched or "",
            "email": obj.contact_email_sched or "",
        }

    def get_reschedule_contact(self, obj):
        return {
            "firstName": obj.contact_first_name_resched or "",
            "lastName": obj.contact_last_name_resched or "",
            "phone": obj.contact_phone_resched or "",
        }

    # ── cc_emails ──
    def get_cc_emails(self, obj):
        if obj.order_status_emails:
            return [e.strip() for e in obj.order_status_emails.split("\n") if e.strip()]
        return []


