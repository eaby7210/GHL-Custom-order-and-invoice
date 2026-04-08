import stripe
from stripe import Coupon as stripe_coupon, PromotionCode, ListObject
from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from decimal import Decimal
from stripe_payment.models import (
    Coupon,
    Order,
    ALaCarteService,
    NotaryClientCompany,
)
import json
import re
from typing import Optional

stripe.api_key = settings.STRIPE_SECRET_KEY

# === CONFIGURE STRIPE TIMEOUT ===
# Set a timeout for all Stripe requests to prevent Gunicorn worker hangs.
# Default Gunicorn timeout is often 30s. We set Stripe timeout to 20s to fail before the worker is killed.
# stripe.max_network_retries = 10
try:
    from stripe._http_client import RequestsClient
    httpClient = RequestsClient(timeout=60) 
    stripe.default_http_client = httpClient
except Exception as e:
    print(f"⚠️ Could not set custom Stripe timeout: {e}")
# ================================

def create_stripe_customer(company_name, email=None, metadata=None):
    """
    Creates a Stripe customer.
    Allowed duplicates as per requirements.
    """
    try:
        customer_data = {
            "name": company_name,
        }
        if email:
            customer_data["email"] = email
        
        if metadata:
            customer_data["metadata"] = metadata

        customer = stripe.Customer.create(**customer_data)
        print(f"✅ Created Stripe Customer: {customer.id} for {company_name}")
        return customer
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout creating Customer: {e}")
        return None
    except Exception as e:

        print(f"❌ Error creating Stripe Customer: {e}")
        return None

def apply_coupon_to_customer(customer_id, coupon_id):
    """
    Applies a coupon to a customer.
    This counts against the coupon's redemption limit.
    """
    try:
        stripe.Customer.modify(
            customer_id,
            coupon=coupon_id
        )
        print(f"✅ Applied coupon {coupon_id} to customer {customer_id}")
        return True
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout applying coupon: {e}")
        return False
    except Exception as e:
        print(f"❌ Error applying coupon to customer: {e}")
        return False

def generate_order_line_items(order: Order):
    """
    Generates the line items list for an order, used for both Stripe Session and PaymentIntent metadata.
    """
    line_items = []

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
                    "unit_amount": int(float(bundle.price or 0) * 100),
                },
                "quantity": 1,
            })


    services = order.a_la_carte_services.all()
    for service in services:
        for item in service.items.all():
            # Gather options
            selected_options = item.options.filter(value=True).values_list("label", flat=True)

            # Gather submenu info
            submenu_parts = []
            for sub in item.submenu_items.all():
                if sub.value > 0:
                    label = f"{sub.label} X{sub.value}" if sub.value > 1 else sub.label
                    submenu_parts.append(label)

            # Build product name
            product_name = item.title
            if submenu_parts:
                product_name += " + " + " + ".join(submenu_parts)
            if selected_options:
                product_name += f" ({' + '.join(selected_options)})"

            # Price logic
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
                            "submenu": ", ".join(
                                f"{sub.label} ({sub.value})" for sub in item.submenu_items.all() if sub.value > 0
                            ),
                        },
                    },
                    "unit_amount": int(float(price_value) * 100),
                },
                "quantity": 1,
            })


    if not line_items:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Custom Order",
                    "description": f"{order.service_type.title()} Service",
                },
                "unit_amount": int(float(order.total_price or 0) * 100),
            },
            "quantity": 1,
        })
    
    # --- Add Order Protection  ---
    if order.order_protection and int(Decimal(order.order_protection_price))>0:
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
        
    return line_items


# Stripe Invoice.footer max length (API); same cap as test_stripe_invoice command.
STRIPE_INVOICE_FOOTER_MAX_LEN = 5000


def _truncate_stripe_invoice_footer(text):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= STRIPE_INVOICE_FOOTER_MAX_LEN:
        return text
    return text[: STRIPE_INVOICE_FOOTER_MAX_LEN - 3] + "..."


def _normalize_stripe_footer_text(text):
    if not text:
        return ""
    out_lines = []
    prev_blank = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if not prev_blank:
                out_lines.append("")
            prev_blank = True
        else:
            prev_blank = False
            out_lines.append(stripped)
    return "\n".join(out_lines).strip()


def _html_to_stripe_footer(html_fragment):
    plain = strip_tags(html_fragment or "")
    plain = plain.replace("\n", " ")
    plain = re.sub(r"\s+", " ", plain).strip()
    return _truncate_stripe_invoice_footer(plain)


def stripe_invoice_footer_for_order(order: Order) -> str:
    """
    Plain-text Stripe Invoice.footer from the same templates as
    management/commands/test_stripe_invoice.py (not HTML).
    """
    order_status_emails_list = []
    raw_emails = getattr(order, "order_status_emails", None) or ""
    if raw_emails:
        order_status_emails_list = raw_emails.split("\n")
    ctx = {"order": order, "order_status_emails_list": order_status_emails_list}
    footer = None
    try:
        raw = render_to_string("invoice_notes_stripe_footer.txt", ctx)
        footer = _normalize_stripe_footer_text(raw)
    except TemplateDoesNotExist:
        pass
    if footer is None:
        try:
            html = render_to_string("invoice_notes.html", ctx)
            footer = _html_to_stripe_footer(html)
        except TemplateDoesNotExist:
            footer = (
                f"[Order #{order.id}] Add templates/invoice_notes_stripe_footer.txt "
                "or invoice_notes.html."
            )
            footer = _truncate_stripe_invoice_footer(footer)
    return _truncate_stripe_invoice_footer(footer)


def native_stripe_invoice_lines_for_order(order: Order):
    """
    Line specs for stripe.InvoiceItem.create: amount (positive cents), description,
    metadata — derived from generate_order_line_items (bundles, a la carte,
    fallback, order protection).
    """
    lines = []
    for li in generate_order_line_items(order):
        pd = li["price_data"]
        qty = int(li.get("quantity") or 1)
        amt = int(pd["unit_amount"]) * qty
        prod = pd.get("product_data") or {}
        name = prod.get("name") or "Line item"
        desc = prod.get("description") or ""
        description = name if not desc else f"{name} — {desc}"
        if len(description) > 500:
            description = description[:497] + "..."
        meta = {}
        for k, v in (prod.get("metadata") or {}).items():
            meta[str(k)[:40]] = str(v)[:500]
        meta.setdefault("source", "generate_order_line_items")
        lines.append({"amount": amt, "description": description, "metadata": meta})
    return lines


def discount_amount_cents_from_event_dict(event_obj) -> int:
    """Match build_invoice_payload: checkout.session total_details vs PI amount_details."""
    if not event_obj:
        return 0
    obj_type = event_obj.get("object")
    if obj_type == "checkout.session":
        td = event_obj.get("total_details") or {}
    else:
        td = event_obj.get("amount_details") or {}
    try:
        return int(td.get("amount_discount") or 0)
    except (TypeError, ValueError):
        return 0


def resolve_stripe_customer_id_for_order(
    order: Order, explicit_customer_id: Optional[str] = None
) -> Optional[str]:
    if explicit_customer_id:
        return explicit_customer_id
    cid = getattr(order, "company_id", None)
    if cid in (None, ""):
        return None
    try:
        company = NotaryClientCompany.objects.only("stripe_customer_id").get(pk=cid)
        return company.stripe_customer_id or None
    except (NotaryClientCompany.DoesNotExist, ValueError, TypeError):
        return None


def create_stripe_session(order: Order, domain, customer_id=None):
    """
    Creates a Stripe Checkout Session for the given order.
    `domain` should be something like 'https://yourfrontenddomain.com'
    """
    line_items = generate_order_line_items(order)
    total_price_cents = sum(li["price_data"]["unit_amount"] * li["quantity"] for li in line_items)

    coupon_data = None
    if order.coupon_code:
        coupon = get_coupon_by_promo_code(order.coupon_code.strip())
        if coupon:
            print(f"Coupon found: {coupon.id} - {coupon.percent_off}% off")
            # Create discount object correctly
            # Create discount object correctly
            coupon_data = {
                # Use "promotion_code" if it's a customer-facing code
                # Or use "coupon" if it's a direct coupon ID
                "coupon": coupon.id
            }
    
    session_params = {
        "payment_method_types": ["card", "link"],
        "mode": "payment",
        "line_items": line_items,
        "success_url": f"{domain}?status=success&session_id={{CHECKOUT_SESSION_ID}}&client_id={order.user_id}",
        "cancel_url": f"{domain}?client_id={order.user_id}&company_id={order.company_id}&status=cancel",
        
        "payment_intent_data": {
            "capture_method": "manual",
            "setup_future_usage": "off_session",
            "metadata": {
                "_id": str(order.id), # type: ignore
                "contact_name": (order.contact_first_name + " " + order.contact_last_name) if order.contact_first_name and order.contact_last_name else ""  ,
                "contact_phone": order.contact_phone_sched or "",
                "contact_email": order.contact_email_sched or "",
                "preferred_datetime": order.preferred_datetime.isoformat() if order.preferred_datetime else "",
                "unit": order.unit or "",
                "client_id": order.company_id,
                "company_name": order.company_name,
                "user_id": order.user_id,
            },
        }

    }
    if coupon_data:
        print(f"applying coupon")
        session_params["discounts"] = [coupon_data]
    else:
        session_params["allow_promotion_codes"] = True

    if customer_id:
        session_params["customer"] = customer_id
    else:
        session_params["customer_creation"] = "always"
    # print("Creating Stripe session with line items:", json.dumps(line_items, indent=4))
    try:
        session = stripe.checkout.Session.create(**session_params)
        return session
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout creating Session: {e}")
        raise e
    except Exception as e:
        print(f"❌ Error creating Stripe Session: {e}")
        raise e


def get_coupon_by_promo_code(code)-> stripe_coupon |None:
    """
    Looks up a Stripe promotion code (not coupon ID) and returns the attached coupon if valid.
    """
    try:
        if code:
            code = code.strip()
        print(f"Looking up promotion code: {code}")
        promo_codes : ListObject["PromotionCode"] = stripe.PromotionCode.list(code=code, limit=1)
        print(f"Promotion code: {promo_codes}")
        # print(f"promocode {json.dumps(promo_codes, indent=4)}")
        if promo_codes.data:
            promo = promo_codes.data[0]
            if not promo.active:
                return None
            
            # Extract coupon ID based on observed output structure (promotion.coupon)
            # or standard structure (coupon.id)
            coupon_id = None
            
            if hasattr(promo, 'promotion') and hasattr(promo.promotion, 'coupon'):
                 coupon_id = promo.promotion.coupon
            elif hasattr(promo, 'coupon'):
                 if hasattr(promo.coupon, 'id'):
                     coupon_id = promo.coupon.id
                 else:
                     coupon_id = promo.coupon # Assuming string ID if not expanded object

            if coupon_id:
                # Retrieve the full coupon object to ensure we have all fields and validity
                coupon = stripe_coupon.retrieve(coupon_id)
                return coupon if coupon and coupon.valid else None
                
            return None
        return None
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout retrieving promotion code: {e}")
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
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout syncing coupons: {e}")
        raise e
    except stripe.StripeError as e:
        print("Stripe error while syncing coupons:", e)
        raise

def get_coupon(user_coupon_code)->stripe_coupon | None:
    """
    Syncs Stripe coupons to local DB, then retrieves the matched coupon.
    """
    try:
        print(f"Retrieving coupon for code: {user_coupon_code}")
        coupon = get_coupon_by_promo_code(user_coupon_code.strip())
        if coupon:
            print(f"Coupon found: {coupon.id} - {coupon.percent_off}% off")
            return coupon

    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout retrieving coupon: {e}")
        return None
    except Exception as e:
        print(f"Error during coupon retrieval: {e}")
        return None

def list_payment_methods(customer_id):
    """
    List card payment methods for a customer.
    """
    try:
        methods = stripe.PaymentMethod.list(
            customer=customer_id,
            type="card"
        )
        return methods.data
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout listing payment methods: {e}")
        return []
    except stripe.InvalidRequestError as e:
        print(f"⚠️ Invalid Request (likely wrong environment): {e}")
        return []
    except Exception as e:
        print(f"Error listing payment methods: {e}")
        return []

def attach_payment_method(payment_method_id, customer_id):
    """
    Attach a payment method to a customer.
    """
    try:
        stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer_id,
        )
        return True
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout attaching payment method: {e}")
        raise e
    except stripe.InvalidRequestError as e:
        if "No such PaymentMethod" in str(e):
             print(f"Payment method not found (possibly cross-account issue): {e}")
             raise e
        # If already attached, usually safer to ignore or log
        print(f"Payment attachment warning: {e}")
        return False
    except Exception as e:
        print(f"Error attaching payment method: {e}")
        raise e

def set_default_payment_method(customer_id, payment_method_id):
    """
    Set the default payment method for a customer's invoice settings.
    """
    try:
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": payment_method_id}
        )
        return True
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout setting default payment method: {e}")
        raise e
    except Exception as e:
        print(f"Error setting default payment method: {e}")
        raise e

def create_stripe_setup_intent(customer_id):
    """
    Creates a Stripe SetupIntent for saving a card correctly.
    """
    try:
        intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=["card"],
        )
        return intent
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout creating SetupIntent: {e}")
        return None
    except Exception as e:
        print(f"Error creating setup intent: {e}")
        return None




def create_payment_intent(amount, currency, customer_id, payment_method_id, metadata=None, order=None, frontend_domain=None):
    """
    Creates and confirms a PaymentIntent for a specific payment method (saved card).
    If order is provided, generates line items summary for metadata.
    """
    final_metadata = metadata or {}
    
    if order:
        line_items = generate_order_line_items(order)
        # Format line items for metadata (Stripe limit 500 chars).
        items_summary = []
        for item in line_items:
                p_data = item.get("price_data", {}).get("product_data", {})
                name = p_data.get("name", "Unknown")
                qty = item.get("quantity", 1)
                items_summary.append(f"{qty}x {name}")
        
        items_str = ", ".join(items_summary)
        if len(items_str) > 495:
            items_str = items_str[:495] + "..."
        
        final_metadata["line_items"] = items_str
        final_metadata["order_id"] = str(order.id) # Ensure order_id is present

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            customer=customer_id,
            payment_method=payment_method_id,
            off_session=True,
            confirm=True,
            capture_method='manual',
            metadata=final_metadata
        )
        
        # Determine Redirect URL
        redirect_url = None
        
        if order and frontend_domain:
            redirect_url = f"{frontend_domain}?status=success&payment_intent_id={intent.id}&client_id={order.user_id}"

        return intent, redirect_url

    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout creating PaymentIntent: {e}")
        return None, None
    except Exception as e:
        print(f"❌ Error creating PaymentIntent: {e}")
        import traceback
        traceback.print_exc()
        return None, None
