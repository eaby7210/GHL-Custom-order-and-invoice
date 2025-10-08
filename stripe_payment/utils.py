import stripe
from stripe import Coupon as stripe_coupon, PromotionCode, ListObject
from django.conf import settings
from decimal import Decimal
from stripe_payment.models import (
    Coupon, Order,ALaCarteService,
    
)
from decimal import Decimal
import json

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_session(order: Order, domain):
    """
    Creates a Stripe Checkout Session for the given order.
    `domain` should be something like 'https://yourfrontenddomain.com'
    """
    line_items = []

    if order.service_type == "bundle":
        # Get all bundles for this order
        bundles = order.bundles.all()
        
        if bundles.exists():
            for bundle in bundles:
                line_items.append({
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": bundle.name,
                            "description": f"Bundle - {bundle.description}" if bundle.description else f"Bundle - {bundle.name}",
                        },
                        "unit_amount": int(float(bundle.price) * 100),
                    },
                    "quantity": 1,
                })
        else:
            # Fallback if no bundles found
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Bundled Service",
                        "description": "Bundle service",
                    },
                    "unit_amount": int((order.total_price if order and order.total_price else 0) * 100),
                },
                "quantity": 1,
            })

    elif order.service_type == "a_la_carte":
        services: list[ALaCarteService] = order.a_la_carte_services.all()  # type: ignore

        for service in services:
            items = service.items.all()  # type: ignore

            for item in items:
                # Collect selected options (only where value=True)
                selected_options = item.options.filter(value=True).values_list("label", flat=True)

                # Collect submenu details
                submenu_parts = []
                for sub in item.submenu_items.all():
                    if sub.value > 0:
                        if sub.value == 1:
                            submenu_parts.append(f"{sub.label}")
                        else:
                            submenu_parts.append(f"{sub.label} X{sub.value}")

                # Build combined parts
                title_parts = [item.title]
                if submenu_parts:
                    title_parts.append(" + ".join(submenu_parts))

                # Add option suffix if any
                option_suffix = ""
                if selected_options:
                    option_suffix = f" ({' + '.join(selected_options)})"

                # Final product name
                product_name = f"{' + '.join(title_parts)}"
                if option_suffix:
                    product_name = f"{product_name} {option_suffix}"

                # Determine price
                price_value = item.price or item.base_price or 0

                # Construct Stripe line item
                line_items.append({
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": product_name,
                            "description": service.title,
                            "metadata": {
                                "options": ", ".join(selected_options),
                                "submenu": ", ".join(
                                    f"{sub.label} ({sub.value})" for sub in item.submenu_items.all() if sub.value > 0
                                ),
                            },
                        },
                        "unit_amount": int(price_value * 100),  # Stripe needs cents
                    },
                    "quantity": 1,
                })

    total_price_cents = sum(li["price_data"]["unit_amount"] * li["quantity"] for li in line_items)

    # --- Add Order Protection  ---
    if order.order_protection:
        print(order.order_protection_price, type(order.order_protection_price))
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Order Protection",
                    "description": "Optional order protection",
                },
                "unit_amount": int(Decimal(order.order_protection_price)*100),
            },
            "quantity": 1,
        })

    coupon_data = None
    if order.coupon_code:
        coupon = get_coupon_by_promo_code(order.coupon_code)
        if coupon:
            print(f"Coupon found: {coupon.id} - {coupon.percent_off}% off")
            # Create discount object correctly
            coupon_data = stripe.checkout.Session.CreateParamsDiscount(
                # Use "promotion_code" if it's a customer-facing code
                # Or use "coupon" if it's a direct coupon ID
                coupon= coupon.id
            )
    # print("Creating Stripe session with line items:", json.dumps(line_items, indent=4))
    session = stripe.checkout.Session.create(
        payment_method_types=["card","link"],
        mode="payment",
        line_items=line_items,
        success_url=f"{domain}?status=success&session_id={{CHECKOUT_SESSION_ID}}&client_id={order.user_id}",
        cancel_url=f"{domain}?client_id={order.user_id}&company_id={order.company_id}&status=cancel",
        metadata={
            "order_id": str(order.id), # type: ignore
            "contact_name": (order.contact_first_name + " " + order.contact_last_name) if order.contact_first_name and order.contact_last_name else ""  ,
            "contact_phone": order.contact_phone_sched or "",
            "contact_email": order.contact_email_sched or "",
            "preferred_datetime": order.preferred_datetime.isoformat() if order.preferred_datetime else "",
            "unit": order.unit or ""
        },
        allow_promotion_codes=True,
        # discounts=[coupon_data] if coupon_data else [],
        payment_intent_data={
        "capture_method": "manual",
    }
    )

    return session


def get_coupon_by_promo_code(code)-> stripe_coupon |None:
    """
    Looks up a Stripe promotion code (not coupon ID) and returns the attached coupon if valid.
    """
    try:
        promo_codes : ListObject["PromotionCode"] = stripe.PromotionCode.list(code=code, limit=1)
        # print(f"promocode {json.dumps(promo_codes, indent=4)}")
        if promo_codes.data:
            promo = promo_codes.data[0]
            if not promo.active:
                return None
            coupon = promo.coupon
            return coupon if coupon and coupon.valid else None
        return None
    except stripe.StripeError as e:
        print(f"Stripe error while retrieving promotion code: {e}")
        return None


def sync_stripe_coupons():
    """
    Fetches all coupons from Stripe and updates local DB.
    """
    try:
        coupons = stripe.Coupon.list()  # or use `auto_paging_iter()` for more
        for sc in coupons.auto_paging_iter():
            # print(f"Syncing coupon: {sc.id} - /n{json.dumps(sc, indent=4)}")
            Coupon.objects.update_or_create(
                code=sc.id,  # Use Stripe ID as the user-facing code
                defaults={
                    'name':sc.name,
                    'stripe_coupon_id': sc.id,
                    'amount_off': sc.get('amount_off'),
                    'percent_off': sc.get('percent_off'),
                    'duration': sc.get('duration'),
                    'currency': sc.get('currency'),
                    'valid': sc.get('valid', True),
                }
            )
    except stripe.StripeError as e:
        print("Stripe error while syncing coupons:", e)
        raise

def get_coupon(user_coupon_code)->stripe_coupon | None:
    """
    Syncs Stripe coupons to local DB, then retrieves the matched coupon.
    """
    try:
        coupon = get_coupon_by_promo_code(user_coupon_code.strip())
        if coupon:
            print(f"Coupon found: {coupon.id} - {coupon.percent_off}% off")
            return coupon

    except Exception as e:
        print(f"Error during coupon retrieval: {e}")
        return None
