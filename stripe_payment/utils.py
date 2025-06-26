import stripe
from django.conf import settings
from decimal import Decimal
import json

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_session(order, domain):
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
                    },
                    "unit_amount": int(order.total_price * 100),  # Stripe uses cents
                },
                "quantity": 1,
            })

    elif order.service_type == "a_la_carte":
        for service in order.a_la_carte_services.all():
            total = service.total_price or Decimal('0.00')

            # Prepare Add-ons metadata
            addon_metadata = {
                f"addon_{addon.name}": str(addon.price)
                for addon in service.addons.all()
            }

            # Prepare Submenu metadata (if exists)
            submenu_metadata = {}
            if hasattr(service, 'submenu') and service.submenu:
                submenu_metadata = {
                    "submenu_option": service.submenu.option,
                    "submenu_label": service.submenu.label,
                    "submenu_amount": str(service.submenu.amount)
                }
                if service.submenu.prompt_label:
                    print(service.submenu.prompt_label, service.submenu.prompt_value)
                    submenu_metadata["submenu_prompt"] = service.submenu.prompt_label
                    submenu_metadata["submenu_prompt_value"] = service.submenu.prompt_value

            # Combine metadata
            combined_metadata = {
                **addon_metadata,
                **submenu_metadata
            }

            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": service.name or "Custom Service",
                        "description": service.description or "",
                        "metadata": combined_metadata
                    },
                    "unit_amount": int(total * 100),
                },
                "quantity": 1,
            })

    # print("Creating Stripe session with line items:", json.dumps(line_items, indent=4))
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=line_items,
        success_url=f"{domain}?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{domain}?status=cancel",
        metadata={
            "order_id": str(order.id),
            "contact_name": (order.contact_first_name + " " + order.contact_last_name) if order.contact_first_name and order.contact_last_name else ""  ,
            "contact_phone": order.contact_phone_sched or "",
            "contact_email": order.contact_email_sched or "",
            "preferred_datetime": order.preferred_datetime.isoformat() if order.preferred_datetime else "",
            "unit": order.unit or ""
        },
        
      
    )

    return session
