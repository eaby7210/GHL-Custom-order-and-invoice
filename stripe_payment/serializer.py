from rest_framework import serializers, viewsets, mixins
from .models import (
    Order, ALaCarteService,
    StripeCharge, CheckoutSession, Invoice, BusinessDetails, Discount,
    NotaryUser, NotaryClientCompany,
    Bundle, BundleOption, BundleModalOption,
    ALaCarteItem, ALaCarteOption, ALaCarteSubMenuItem,
    ALaCarteItemModalOption, ALaCarteItemDisclosure
)


class NotaryUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaryUser
        fields = [
            "id", "email", "first_name", "last_name", "name", 
            "photo_url", "is_admin", "type", "disabled", 
            "country_code", "tz", "created_at", "last_login_at"
        ]

class NotaryClientCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaryClientCompany
        fields = [
            "id", "company_name", "type", "active", 
            "stripe_customer_id", "stripe_default_payment_method",
            "created_at", "updated_at"
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
            "postal_code", "unit", "service_type", 
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


