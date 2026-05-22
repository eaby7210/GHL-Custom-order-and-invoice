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
    NotaryUser,
)
import json
import re
from typing import List, Optional

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


class NotaryFulfillmentError(Exception):
    """Stripe payment succeeded but NotaryDash order creation failed."""


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
        stripe.Customer.modify(customer_id, coupon=coupon_id)
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
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": bundle.name,
                            "description": f"Bundle - {bundle.description}"
                            if bundle.description
                            else f"Bundle - {bundle.name}",
                        },
                        "unit_amount": int(float(bundle.price or 0) * 100),
                    },
                    "quantity": 1,
                }
            )

    services = order.a_la_carte_services.all()
    for service in services:
        for item in service.items.all():
            # Gather options
            selected_options = item.options.filter(value=True).values_list(
                "label", flat=True
            )

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

            line_items.append(
                {
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
                                    f"{sub.label} ({sub.value})"
                                    for sub in item.submenu_items.all()
                                    if sub.value > 0
                                ),
                            },
                        },
                        "unit_amount": int(float(price_value) * 100),
                    },
                    "quantity": 1,
                }
            )

    if not line_items:
        line_items.append(
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Custom Order",
                        "description": f"{order.service_type.title()} Service",
                    },
                    "unit_amount": int(float(order.total_price or 0) * 100),
                },
                "quantity": 1,
            }
        )

    # --- Add Order Protection  ---
    if order.order_protection and int(Decimal(order.order_protection_price)) > 0:
        print(order.order_protection_price, type(order.order_protection_price))
        line_items.append(
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Order Protection",
                        "description": "Optional order protection",
                    },
                    "unit_amount": int(Decimal(order.order_protection_price) * 100),
                },
                "quantity": 1,
            }
        )

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


def sync_order_service_type_for_line_items(order: Order) -> None:
    """In-memory only; mirrors bundle / à la carte labeling for invoice line items."""
    bundles = order.bundles.all()
    services = order.a_la_carte_services.all()
    if bundles.exists() and services.exists():
        order.service_type = "mixed"
    elif bundles.exists():
        order.service_type = "bundled"
    elif services.exists():
        order.service_type = "a_la_carte"


def retrieve_invoice(inv_id: str) -> stripe.Invoice:
    """Retrieve a Stripe invoice by its ID."""
    try:
        return stripe.Invoice.retrieve(inv_id)
    except stripe.InvalidRequestError:
        return None


def void_draft_stripe_invoice_if_any(invoice_id: Optional[str]) -> None:
    """Void a draft invoice so a new checkout / intent can replace it."""
    if not invoice_id:
        return
    try:
        inv = stripe.Invoice.retrieve(invoice_id)
        if getattr(inv, "status", None) == "draft":
            stripe.Invoice.void_invoice(invoice_id)
    except stripe.InvalidRequestError:
        pass


def apply_stripe_invoice_discount_cents(
    invoice_id: str,
    discount_cents: int,
    currency: str,
    order_pk,
) -> None:
    """Apply a fixed-amount-off coupon to a draft invoice (idempotent if discounts exist)."""
    if discount_cents <= 0:
        return
    inv = stripe.Invoice.retrieve(invoice_id)
    discounts = getattr(inv, "discounts", None) or []
    if discounts:
        return
    cur = (currency or "usd").lower()
    coupon = stripe.Coupon.create(
        amount_off=int(discount_cents),
        currency=cur,
        duration="once",
        name=f"Checkout discount (order {order_pk})",
    )
    stripe.Invoice.modify(invoice_id, discounts=[{"coupon": coupon.id}])


# Stripe invoice custom field values are capped at 140 characters; max 4 fields per invoice.
_STRIPE_INVOICE_CUSTOM_FIELD_VALUE_MAX = 140
_STRIPE_INVOICE_CUSTOM_FIELD_NAME_MAX = 40
_STRIPE_INVOICE_CUSTOM_FIELDS_MAX = 4


def _normalize_us_phone_national_digits(raw) -> Optional[str]:
    """
    Return 10-digit national digits if ``raw`` looks like a US NANP number
    (optional country code 1); otherwise None.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or not digits.isdigit():
        return None
    # NANP NXX-NXX-XXXX: first digit of area code and exchange cannot be 0 or 1.
    if digits[0] in "01" or digits[3] in "01":
        return None
    return digits


def format_us_phone_for_invoice(raw) -> str:
    """
    If ``raw`` is a valid US number, return ``+1-XXX-XXX-XXXX``; otherwise the
    trimmed original string (empty when missing).
    """
    d = _normalize_us_phone_national_digits(raw)
    if d:
        return f"+1-{d[0:3]}-{d[3:6]}-{d[6:10]}"
    if raw is None:
        return ""
    return str(raw).strip()


def _stripe_invoice_custom_field_chunks(
    base_name: str, value: str
) -> List[dict[str, str]]:
    """Split a long value into 140-char Stripe custom field values; add (cont.) fields as needed."""
    if not value:
        return []
    out: List[dict[str, str]] = []
    rest = value
    idx = 0
    m = _STRIPE_INVOICE_CUSTOM_FIELD_VALUE_MAX
    while rest:
        if len(rest) <= m:
            label = base_name if idx == 0 else f"{base_name} (cont.)"
            out.append(
                {
                    "name": label[:_STRIPE_INVOICE_CUSTOM_FIELD_NAME_MAX],
                    "value": rest,
                }
            )
            break
        label = base_name if idx == 0 else f"{base_name} (cont.)"
        out.append(
            {
                "name": label[:_STRIPE_INVOICE_CUSTOM_FIELD_NAME_MAX],
                "value": rest[:m],
            }
        )
        rest = rest[m:]
        idx += 1
    return out


def stripe_invoice_address_custom_field_from_order(
    order: Order,
) -> Optional[List[dict[str, str]]]:
    """
    Stripe Invoice ``custom_fields`` for service location and contact.

    If the full joined address exceeds 140 characters but street (line1 + unit)
    alone does not, splits into a main street field and a second field for
    city, state, and postal. Any value still over the limit is split into
    additional ``(cont.)`` fields. At most four custom fields total (Stripe cap);
    Name and Phone are listed first, then address chunks.
    """
    line1 = (getattr(order, "streetAddress", None) or "").strip()
    line2 = (getattr(order, "unit", None) or "").strip()
    city = (getattr(order, "city", None) or "").strip()
    state = (getattr(order, "state", None) or "").strip()
    postal = (str(getattr(order, "postal_code", None) or "")).strip()
    if not (line1 or line2 or city or state or postal):
        return None

    fn = (getattr(order, "contact_first_name_sched", None) or "").strip()
    ln = (getattr(order, "contact_last_name_sched", None) or "").strip()
    name = f"{fn} {ln}".strip()
    if not name:
        fn = (getattr(order, "contact_first_name", None) or "").strip()
        ln = (getattr(order, "contact_last_name", None) or "").strip()
        name = f"{fn} {ln}".strip()
    if not name:
        name = (getattr(order, "company_name", None) or "").strip()
    if not name:
        name = f"Order #{order.id}"

    phone_raw = getattr(order, "contact_phone_sched", None) or getattr(
        order, "contact_phone", None
    )
    phone = format_us_phone_for_invoice(phone_raw)

    city_line = ", ".join(
        p for p in (city, f"{state} {postal}".strip() if (state or postal) else "") if p
    )
    addr_parts: list[str] = []
    if line1:
        addr_parts.append(line1)
    if line2:
        addr_parts.append(line2)
    if city_line:
        addr_parts.append(city_line)
    address_line = ", ".join(addr_parts)
    street_only = ", ".join(p for p in (line1, line2) if p)

    mx = _STRIPE_INVOICE_CUSTOM_FIELD_VALUE_MAX
    address_specs: list[tuple[str, str]] = []

    if len(address_line) <= mx:
        address_specs.append(("Service address", address_line))
    elif len(address_line) > mx and len(street_only) <= mx and city_line:
        address_specs.append(("Service address", street_only))
        address_specs.append(("City, State, ZIP", city_line))
    else:
        if line1:
            address_specs.append(("Address line 1", line1))
        if line2:
            address_specs.append(("Address line 2", line2))
        if city_line:
            address_specs.append(("City, State, ZIP", city_line))

    address_fields: List[dict[str, str]] = []
    for aname, aval in address_specs:
        address_fields.extend(_stripe_invoice_custom_field_chunks(aname, aval))

    result: List[dict[str, str]] = []
    if name:
        result.extend(_stripe_invoice_custom_field_chunks("Name", name))
    if phone:
        result.extend(_stripe_invoice_custom_field_chunks("Phone", phone))
    result.extend(address_fields)

    if len(result) > _STRIPE_INVOICE_CUSTOM_FIELDS_MAX:
        result = result[:_STRIPE_INVOICE_CUSTOM_FIELDS_MAX]

    return result


def stripe_invoice_description_for_order(order: Order) -> str:
    """Stripe invoice description; uses NotaryDash order_id when set, else DB pk."""
    no_id = getattr(order, "notary_order_id", None)
    if no_id is not None and str(no_id).strip():
        num = str(no_id).strip()
    else:
        num = str(order.id)
    return f"Order #{num} — {order.company_name or 'Notary services'}"


# Draft invoices get this until NotaryDash order_id exists; views patch before finalize.
STRIPE_INVOICE_DESCRIPTION_PENDING_NOTARY_ID = "Creating notary order ID…"


def create_draft_stripe_invoice_for_order(
    order: Order,
    *,
    stripe_customer_id=None,
    currency: str = "usd",
    description=None,
    extra_metadata=None,
):
    """
    Create a draft Stripe Invoice + InvoiceItems for ``order`` (no event-based discount).
    Caller should persist ``invoice.id`` on the order for webhook-time finalize/pay.
    """
    sync_order_service_type_for_line_items(order)
    customer_id = resolve_stripe_customer_id_for_order(order, stripe_customer_id)
    if not customer_id:
        raise ValueError(
            "Stripe customer required: pass stripe_customer_id= or set "
            "NotaryClientCompany.stripe_customer_id for order.company_id."
        )
    cur = (currency or "usd").lower()
    footer = stripe_invoice_footer_for_order(order)
    meta = {
        "order_id": str(order.id),
        "source": (
            f"NotaryDash Order #{order.notary_order_id}"
            if getattr(order, "notary_order_id", None)
            else "checkout_pending"
        ),
    }
    if getattr(order, "stripe_session_id", None):
        meta["stripe_session_id"] = str(order.stripe_session_id)
    if extra_metadata:
        for k, v in extra_metadata.items():
            if v is None:
                continue
            s = v if isinstance(v, str) else str(v)
            meta[str(k)[:40]] = s[:500]

    inv_params = {
        "customer": customer_id,
        "collection_method": "send_invoice",
        "days_until_due": 1,
        "auto_advance": False,
        "currency": cur,
        "description": (
            description
            if description is not None
            else STRIPE_INVOICE_DESCRIPTION_PENDING_NOTARY_ID
        ),
        "footer": footer,
        "metadata": meta,
    }

    # Natively inject promo-code discounts into the Stripe Invoice!
    if getattr(order, "coupon_code", None):
        coupon = get_coupon_by_promo_code(order.coupon_code.strip())
        if coupon:
            inv_params["discounts"] = [{"coupon": coupon.id}]

    address_field = stripe_invoice_address_custom_field_from_order(order)
    if address_field:
        inv_params["custom_fields"] = address_field
    invoice = stripe.Invoice.create(**inv_params)
    for line in native_stripe_invoice_lines_for_order(order):
        stripe.InvoiceItem.create(
            customer=customer_id,
            invoice=invoice.id,
            currency=cur,
            amount=line["amount"],
            description=line["description"],
            metadata=line.get("metadata") or {},
        )
    return stripe.Invoice.retrieve(invoice.id)


def create_stripe_session(order: Order, domain, customer_id=None):
    """
    Creates a Stripe Checkout Session for the given order using native invoice generation
    to eliminate duplicate transaction rows, auto-capturing funds upfront and relying on
    an automated refund webhook system if downstream fulfillment fails.
    """
    line_items = generate_order_line_items(order)
    total_price_cents = sum(
        li["price_data"]["unit_amount"] * li["quantity"] for li in line_items
    )

    coupon_data = None
    if order.coupon_code:
        coupon = get_coupon_by_promo_code(order.coupon_code.strip())
        if coupon:
            print(f"Coupon found: {coupon.id} - {coupon.percent_off}% off")
            coupon_data = {"coupon": coupon.id}

    invoice_data = {
        "description": stripe_invoice_description_for_order(order),
        "footer": stripe_invoice_footer_for_order(order),
        "metadata": {"order_id": str(order.id)},
    }

    address_field = stripe_invoice_address_custom_field_from_order(order)
    if address_field:
        invoice_data["custom_fields"] = address_field

    session_params = {
        "payment_method_types": ["card", "link"],
        "mode": "payment",
        "line_items": line_items,
        "success_url": f"{domain}?status=success&session_id={{CHECKOUT_SESSION_ID}}&client_id={order.user_id}",
        "cancel_url": f"{domain}?client_id={order.user_id}&company_id={order.company_id}&status=cancel",
        "invoice_creation": {"enabled": True, "invoice_data": invoice_data},
        "payment_intent_data": {
            "capture_method": "automatic",
            "setup_future_usage": "off_session",
            "metadata": {
                "_id": str(order.id),
                "contact_name": (
                    order.contact_first_name + " " + order.contact_last_name
                )
                if order.contact_first_name and order.contact_last_name
                else "",
                "contact_phone": order.contact_phone_sched or "",
                "contact_email": order.contact_email_sched or "",
                "preferred_datetime": order.preferred_datetime.isoformat()
                if order.preferred_datetime
                else "",
                "unit": order.unit or "",
                "client_id": order.company_id,
                "company_name": order.company_name,
                "user_id": order.user_id,
            },
        },
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


def get_coupon_by_promo_code(code) -> stripe_coupon | None:
    """
    Looks up a Stripe promotion code (not coupon ID) and returns the attached coupon if valid.
    """
    try:
        if code:
            code = code.strip()
        print(f"Looking up promotion code: {code}")
        promo_codes: ListObject["PromotionCode"] = stripe.PromotionCode.list(
            code=code, limit=1
        )
        print(f"Promotion code: {promo_codes}")
        # print(f"promocode {json.dumps(promo_codes, indent=4)}")
        if promo_codes.data:
            promo = promo_codes.data[0]
            if not promo.active:
                return None

            # Extract coupon ID based on observed output structure (promotion.coupon)
            # or standard structure (coupon.id)
            coupon_id = None

            if hasattr(promo, "promotion") and hasattr(promo.promotion, "coupon"):
                coupon_id = promo.promotion.coupon
            elif hasattr(promo, "coupon"):
                if hasattr(promo.coupon, "id"):
                    coupon_id = promo.coupon.id
                else:
                    coupon_id = (
                        promo.coupon
                    )  # Assuming string ID if not expanded object

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
                    "name": sc.name,
                    "stripe_coupon_id": sc.id,
                    "amount_off": sc.get("amount_off"),
                    "percent_off": sc.get("percent_off"),
                    "duration": sc.get("duration"),
                    "currency": sc.get("currency"),
                    "valid": sc.get("valid", True),
                },
            )
    except stripe.APIConnectionError as e:
        print(f"❌ Stripe Timeout syncing coupons: {e}")
        raise e
    except stripe.StripeError as e:
        print("Stripe error while syncing coupons:", e)
        raise


def get_coupon(user_coupon_code) -> stripe_coupon | None:
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
        methods = stripe.PaymentMethod.list(customer=customer_id, type="card")
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
            customer_id, invoice_settings={"default_payment_method": payment_method_id}
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


def payment_intent_from_paid_invoice(invoice):
    """
    Return the PaymentIntent for a paid invoice.

    Stripe Basil (2025-03-31+) removed Invoice.payment_intent. Use
    ``invoice.payments.data[].payment.payment_intent`` (expand that path on
    retrieve); ``id`` and ``status`` live on that PaymentIntent object.
    Older API versions may still set invoice.payment_intent.
    """
    legacy = getattr(invoice, "payment_intent", None)
    if legacy:
        if isinstance(legacy, str):
            return stripe.PaymentIntent.retrieve(legacy)
        return legacy

    payments = getattr(invoice, "payments", None)
    rows = getattr(payments, "data", None) if payments else None
    if not rows:
        return None

    resolved = []
    for inv_payment in rows:
        payment = getattr(inv_payment, "payment", None)
        if not payment or getattr(payment, "type", None) != "payment_intent":
            continue
        pi_ref = getattr(payment, "payment_intent", None)
        if not pi_ref:
            continue
        pi_obj = (
            stripe.PaymentIntent.retrieve(pi_ref) if isinstance(pi_ref, str) else pi_ref
        )
        if getattr(pi_obj, "status", None) == "succeeded":
            return pi_obj
        resolved.append((inv_payment, pi_obj))

    if not resolved:
        return None

    for inv_payment, pi_obj in resolved:
        if getattr(inv_payment, "status", None) == "paid":
            return pi_obj

    return resolved[-1][1]


def _client_user_dict_for_order(order: Order) -> dict:
    try:
        uid = int(str(order.user_id)) if order.user_id not in (None, "") else None
    except (TypeError, ValueError):
        uid = None
    if uid is None:
        return {}
    nu = NotaryUser.objects.filter(pk=uid).first()
    if not nu:
        return {}
    return {
        "id": nu.pk,
        "email": nu.email or "",
        "name": nu.name or "",
        "first_name": nu.first_name or "",
        "last_name": nu.last_name or "",
        "attr": nu.attr if isinstance(nu.attr, dict) else {},
    }


def _fulfill_notary_order_after_invoice_pay(order: Order, payment_intent) -> None:
    """
    Create NotaryDash product/order and patch the paid Stripe invoice description.
    Only call after Invoice.pay succeeds.
    """
    from .views import build_notary_order, _ghl_invoice_items_and_notary_product_names

    if getattr(order, "notary_order_id", None):
        return

    client_user = _client_user_dict_for_order(order)
    _, notary_product_names = _ghl_invoice_items_and_notary_product_names(order, {})
    event_obj = {
        "object": "payment_intent",
        "id": payment_intent.id,
        "amount": getattr(payment_intent, "amount", None) or 0,
    }

    notary_order = build_notary_order(order, notary_product_names, client_user, event_obj)
    if not notary_order:
        raise NotaryFulfillmentError(
            f"Payment captured for order {order.id} but NotaryDash fulfillment failed."
        )

    if order.notary_order_id and order.invoice_id:
        try:
            stripe.Invoice.modify(
                order.invoice_id,
                description=stripe_invoice_description_for_order(order),
            )
        except Exception as e:
            print(
                f"⚠️ Paid invoice {order.invoice_id} not updated with notary id "
                f"(order {order.id}): {e}"
            )


def create_payment_intent(
    amount,
    currency,
    customer_id,
    payment_method_id,
    metadata=None,
    order=None,
    frontend_domain=None,
):
    """
    Creates and confirms a PaymentIntent for a specific payment method (saved card)
    by routing directly through a Stripe Invoice to avoid transaction duplication.
    NotaryDash fulfillment runs only after Invoice.pay succeeds.
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
        final_metadata["order_id"] = str(order.id)  # Ensure order_id is present
        final_metadata["stripe_payment_flow"] = "invoice_pay_saved_card"

        void_draft_stripe_invoice_if_any(getattr(order, "invoice_id", None))

        # 1. Draft the Invoice
        try:
            draft_inv = create_draft_stripe_invoice_for_order(
                order,
                stripe_customer_id=customer_id,
                currency=currency or "usd",
            )
            order.invoice_id = draft_inv.id
            order.save(update_fields=["invoice_id"])
            final_metadata["stripe_invoice_id"] = draft_inv.id
        except ValueError as e:
            print(f"⚠️ Could not create draft Stripe invoice for order {order.id}: {e}")
            return None, None

    try:
        # Instead of raw PaymentIntent create, let the invoice natively
        # auto-generate the PaymentIntent & execute the charge
        if order and order.invoice_id:
            # Native Auto-generation & capture:
            stripe.Invoice.pay(
                order.invoice_id,
                payment_method=payment_method_id,
                off_session=True,
            )
            invoice = stripe.Invoice.retrieve(
                order.invoice_id,
                expand=["payments.data.payment.payment_intent"],
            )
            intent = payment_intent_from_paid_invoice(invoice)
            if not intent:
                raise ValueError(
                    "Paid invoice has no PaymentIntent (check Basil invoice.payments)"
                )
            # Apply metadata
            stripe.PaymentIntent.modify(intent.id, metadata=final_metadata)

            if order:
                try:
                    _fulfill_notary_order_after_invoice_pay(order, intent)
                except NotaryFulfillmentError:
                    raise
                except Exception as e:
                    print(f"❌ NotaryDash fulfillment after payment: {e}")
                    raise NotaryFulfillmentError(
                        f"Payment captured for order {order.id} but NotaryDash "
                        f"fulfillment failed: {e}"
                    ) from e

        else:
            # Fallback for generic payments entirely devoid of generic Orders
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                off_session=True,
                confirm=True,
                capture_method="automatic",
                metadata=final_metadata,
            )

        # Determine Redirect URL
        redirect_url = None

        if order and frontend_domain:
            redirect_url = f"{frontend_domain}?status=success&payment_intent_id={intent.id}&client_id={order.user_id}"

        return intent, redirect_url

    except stripe.error.CardError as e:
        print(f"❌ Stripe CardError / 3DS requirement triggered: {e}")
        # MUST re-raise CardError to ensure FormSubmissionAPIView detects it
        # and issues a 400 response for 3DS action requirement
        raise e
    except stripe.error.APIConnectionError as e:
        print(f"❌ Stripe Timeout creating PaymentIntent via invoice: {e}")
        return None, None
    except Exception as e:
        print(f"❌ Error creating PaymentIntent: {e}")
        import traceback

        traceback.print_exc()
        return None, None
