import stripe
from stripe import Coupon as stripe_coupon, PromotionCode, ListObject
from django.conf import settings
from decimal import Decimal
from stripe_payment.models import (
    Coupon, Order,ALaCarteService,
    
)
import json

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_session(order: Order, domain):
    """
    Creates a Stripe Checkout Session for the given order.
    `domain` should be something like 'https://yourfrontenddomain.com'
    """
    import stripe
    from django.conf import settings
    import json

    stripe.api_key = settings.STRIPE_SECRET_KEY

    line_items = []

    # --- Build line items ---
    if order.service_type == "bundled":
        if order.bundle_item:
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": order.bundle_item,
                        "description": f"Bundle - {order.bundle_item} of {order.bundle_group} group",
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
                selected_options = item.options.filter(value=True).values_list("label", flat=True)
                option_suffix = f" ({' + '.join(selected_options)})" if selected_options else ""
                product_name = f"{item.title}{option_suffix}"
                price_value = item.price or item.base_price or 0

                line_items.append({
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": product_name,
                            "description": service.title,
                            "metadata": {
                                "service_id": service.service_id,
                                "item_id": item.item_id,
                                "options": ", ".join(selected_options),
                            }
                        },
                        "unit_amount": int(price_value * 100),
                    },
                    "quantity": 1,
                })

    # --- Base total ---
    total_price_cents = sum(li["price_data"]["unit_amount"] * li["quantity"] for li in line_items)
    print(f"[DEBUG] Base total: {total_price_cents / 100:.2f} USD")

    # --- Add Order Protection (4% of total) ---
    if order.order_protection:
        protection_price_cents = int(total_price_cents * 0.04)
        print(f"[DEBUG] Adding Order Protection: {protection_price_cents / 100:.2f} USD")
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Order Protection",
                    "description": "Optional order protection (4% of order total)",
                },
                "unit_amount": protection_price_cents,
            },
            "quantity": 1,
        })

    # --- Handle discounts (combined logic) ---
    coupon_data = None

    if order.coupon_code and order.discount_percent and order.discount_percent > 0:
        coupon = get_coupon_by_promo_code(order.coupon_code)
        if coupon:
            first = float(coupon.percent_off or 0)
            second = float(order.discount_percent or 0)
            combined_discount = 100 - ((100 - first) * (100 - second) / 100)

            print(f"[DEBUG] Applying combined discount: {first}% (coupon) + {second}% (extra) = {combined_discount:.2f}%")

            temp_coupon = stripe.Coupon.create(
                percent_off=combined_discount,
                duration="once",
                max_redemptions=1,
                name=f"Combined {first}% + {second}%",
            )
            coupon_data = {"coupon": temp_coupon.id}
            print(f"[DEBUG] Created temp combined coupon: {temp_coupon.id}")

    elif order.coupon_code:
        coupon = get_coupon_by_promo_code(order.coupon_code)
        if coupon:
            print(f"[DEBUG] Applying coupon from DB: {coupon.id} - {coupon.percent_off}% off")
            coupon_data = {"coupon": coupon.id}

    elif order.discount_percent and order.discount_percent > 0:
        discount_value = float(order.discount_percent)
        print(f"[DEBUG] Applying single discount_percent: {discount_value}%")
        temp_coupon = stripe.Coupon.create(
            percent_off=discount_value,
            duration="once",
            max_redemptions=1,
            name=f"Discount {discount_value}%",
        )
        coupon_data = {"coupon": temp_coupon.id}
        print(f"[DEBUG] Created temp discount coupon: {temp_coupon.id}")

    print("[DEBUG] Final line items:", json.dumps(line_items, indent=2))

    # --- Create Checkout Session ---
    session = stripe.checkout.Session.create(
        payment_method_types=["card", "link"],
        mode="payment",
        line_items=line_items,
        success_url=f"{domain}?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{domain}?status=cancel",
        metadata={
            "order_id": str(order.id),  # type: ignore
            "contact_name": (order.contact_first_name + " " + order.contact_last_name)
            if order.contact_first_name and order.contact_last_name
            else "",
            "contact_phone": order.contact_phone_sched or "",
            "contact_email": order.contact_email_sched or "",
            "preferred_datetime": order.preferred_datetime.isoformat() if order.preferred_datetime else "",
            "unit": order.unit or "",
        },
        discounts=[coupon_data] if coupon_data else [],
        payment_intent_data={
            "capture_method": "manual",
        },
    )

    print(f"[DEBUG] Stripe Checkout Session created: {session.id}")
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
