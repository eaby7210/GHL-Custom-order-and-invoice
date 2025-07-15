import stripe
from stripe import Coupon as stripe_coupon, PromotionCode, ListObject
from django.conf import settings
from decimal import Decimal
from stripe_payment.models import (
    Coupon, Order,ALaCarteService,
    ALaCarteAddOn, ALaCarteSubMenu
)
import json

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_session(order :Order, domain):
    """
    Creates a Stripe Checkout Session for the given order.
    `domain` should be something like 'https://yourfrontenddomain.com'
    """
    line_items = []

    if order.service_type == "bundled":
        if order.bundle_item:
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": order.bundle_item,
                        "description": f"Bundle - {order.bundle_item} of {order.bundle_group} group",
                    },
                    "unit_amount": int((order.total_price if order and order.total_price else 0) * 100),  # Stripe uses cents
                },
                "quantity": 1,
            })

    elif order.service_type == "a_la_carte":
        services : list[ALaCarteService] = order.a_la_carte_services.all() # type: ignore
        for service in services:
            total = service.total_price or Decimal('0.00')
            price = service.price or Decimal('0.00')

            # Prepare Add-ons metadata
            addons :list[ALaCarteAddOn] = service.addons.all()  # type: ignore
          
            for addon in addons:
                line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"{service.name}-Addon {addon.name}" or "Custom Service",
                        "description": f"Addon - {str(addon)}" or "",
                        "metadata":{
                            "addon_name": addon.name,
                            "addon_key": addon.key,
                            "addon_price": str(addon.price) if addon.price else "0.00",
                        }
                    },
                    "unit_amount": int((addon.price if addon.price else 0) * 100),
                },
                "quantity": 1,
            })
                

            # Prepare Submenu metadata (if exists)
            submenu_metadata = {}
             
            if hasattr(service, 'submenu') and service.submenu: # type: ignore
                service_submenu :ALaCarteSubMenu = service.submenu # type: ignore
                submenu_metadata = {
                    "submenu_option": service_submenu.option,
                    "submenu_label": service_submenu.label,
                    "submenu_amount": str(service_submenu.amount)
                }
                line_items.append({
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"{service.name}-Submenu Option {service_submenu.label}" or "Custom Service Option",
                            "description": f"Submenu {service_submenu.label}-{service_submenu.option} for {service.name}" or "",
                            "metadata":{
                                "submenu_name": service.name,
                                "addon_key": addon.key,
                            }
                        },
                            "unit_amount": int((service_submenu.amount) * 100),
                        },
                        "quantity": 1,
                    })
                if service_submenu.prompt_label:
                    # print(service_submenu.prompt_label, service_submenu.prompt_value)
                    submenu_metadata["submenu_prompt"] = service_submenu.prompt_label
                    submenu_metadata["submenu_prompt_value"] = service_submenu.prompt_value

            # Combine metadata
            # combined_metadata = {
            #     **addon_metadata,
            #     **submenu_metadata,
            #     "Total Price": f"${str(total)}",
            # }

            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": service.name or "Custom Service",
                        "description": service.description or "",
                        # "metadata": combined_metadata
                    },
                    "unit_amount": int(price * 100),
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
        payment_method_types=["card"],
        mode="payment",
        line_items=line_items,
        success_url=f"{domain}?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{domain}?status=cancel",
        metadata={
            "order_id": str(order.id), # type: ignore
            "contact_name": (order.contact_first_name + " " + order.contact_last_name) if order.contact_first_name and order.contact_last_name else ""  ,
            "contact_phone": order.contact_phone_sched or "",
            "contact_email": order.contact_email_sched or "",
            "preferred_datetime": order.preferred_datetime.isoformat() if order.preferred_datetime else "",
            "unit": order.unit or ""
        },
        # allow_promotion_codes=True,
        discounts=[coupon_data] if coupon_data else [],
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
