from rest_framework import serializers, viewsets, mixins
from .models import (
    Order, ALaCarteService,
    StripeCharge, CheckoutSession, Invoice, BusinessDetails, Discount
)



class ALaCarteServiceSerializer(serializers.ModelSerializer):


    class Meta:
        model = ALaCarteService
        fields = [
            "id", "key", "name", "price", "description", "prompt",
            "total_price", "addons_price", "submenu_input", "addons", "submenu"
        ]


class OrderSerializer(serializers.ModelSerializer):
    a_la_carte_services = ALaCarteServiceSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "unit_type", "address", "streetAddress", "city", "state",
            "postal_code", "unit", "service_type", "total_price", "occupancy_vacant",
            "occupancy_occupied", "access_lock_box", "lock_box_code",
            "lock_box_location", "access_app_lock_box", "access_meet_contact",
            "access_hidden_key", "hidden_key_directions", "access_community_access",
            "community_access_instructions", "access_door_code", "door_code_value",
            "preferred_datetime", "contact_name_sched", "contact_phone_sched",
            "contact_email_sched", "accepted_at", "tbd", "stripe_session_id",
            "created_at","invoice_id", "a_la_carte_services"
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


