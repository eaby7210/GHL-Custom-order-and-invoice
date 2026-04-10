"""
Stripe Invoice test command (stripe==14.3.0 in requirements.txt).

Contrast with stripe_payment.utils:
- create_stripe_session: Checkout Session (payment mode), dynamic line_items,
  payment_intent_data (manual capture, metadata). No Stripe Invoice object.
- create_payment_intent: PaymentIntent for a saved card; line items only in
  metadata. No Stripe Invoice object.

This command uses Invoice + InvoiceItem, manual capture via
payment_settings, finalize_invoice, Invoice.pay(off_session=True) — aligned
with create_payment_intent (manual capture, saved card) — then
PaymentIntent.capture. Optionally Checkout Session with invoice_creation.

GHL invoices (views.build_invoice_payload) set termsNotes from
invoice_notes.html (HTML). Stripe Invoice.footer is plain text only (PDF/UI
do not interpret HTML); order footers use templates/invoice_notes_stripe_footer.txt
which mirrors invoice_notes.html. Fallback: strip_tags(invoice_notes.html).
"""

import importlib.metadata
import json
import re

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from stripe_payment.models import NotaryClientCompany, Order
from stripe_payment.utils import create_stripe_customer

# Stripe Invoice.footer max length (API)
STRIPE_INVOICE_FOOTER_MAX_LEN = 5000


class Command(BaseCommand):
    help = (
        "Create a Stripe Invoice (draft, custom lines, finalize) and optionally "
        "a Checkout Session with invoice_creation. "
        "Pinned version: stripe==14.3.0 (requirements.txt)."
    )

    def add_arguments(self, parser):
        src = parser.add_mutually_exclusive_group()
        src.add_argument(
            "--customer-id",
            type=str,
            help="Existing Stripe customer id (cus_...).",
        )
        src.add_argument(
            "--company-id",
            type=int,
            help=(
                "NotaryClientCompany primary key; uses "
                "company.stripe_customer_id."
            ),
        )
        parser.add_argument(
            "--flow",
            choices=("invoice", "checkout", "both"),
            default="invoice",
            help=(
                "invoice: draft items, manual capture settings, finalize, "
                "Invoice.pay(off_session), PaymentIntent.capture. checkout: "
                "Session with invoice_creation (browser). both: both steps."
            ),
        )
        parser.add_argument(
            "--payment-method-id",
            type=str,
            default=None,
            help=(
                "pm_... for Invoice.pay. If omitted, uses the customer's "
                "invoice_settings.default_payment_method, then "
                "NotaryClientCompany.stripe_default_payment_method when "
                "--company-id was used."
            ),
        )
        parser.add_argument(
            "--currency",
            default="usd",
            help="Three-letter ISO currency code.",
        )
        parser.add_argument(
            "--order-id",
            type=int,
            default=None,
            help=(
                "Order PK: footer from invoice_notes_stripe_footer.txt "
                "(plain text, same data as invoice_notes.html / GHL termsNotes)."
            ),
        )
        parser.add_argument(
            "--footer",
            type=str,
            default=None,
            help=(
                "Override invoice footer (plain text). Ignores --order-id. "
                f"Truncated to {STRIPE_INVOICE_FOOTER_MAX_LEN} chars for Stripe."
            ),
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            ver = importlib.metadata.version("stripe")
        except importlib.metadata.PackageNotFoundError:
            ver = "unknown"
        if ver not in ("unknown", "14.3.0"):
            msg = (
                f"stripe package is {ver}; requirements.txt pins "
                "stripe==14.3.0."
            )
            self.stdout.write(self.style.WARNING(msg))

        customer_id = self._resolve_customer_id(options)
        currency = options["currency"].lower()
        company_pm_fallback = self._company_default_payment_method(options)
        footer_text = self._resolve_stripe_invoice_footer(options)

        if options["flow"] in ("invoice", "both"):
            self._run_invoice_flow(
                customer_id,
                currency=currency,
                payment_method_id=options.get("payment_method_id"),
                fallback_payment_method_id=company_pm_fallback,
                footer_text=footer_text,
            )

        if options["flow"] in ("checkout", "both"):
            self._run_checkout_invoice_flow(
                customer_id,
                currency=currency,
                footer_text=footer_text,
            )

    def _resolve_customer_id(self, options):
        if options.get("customer_id"):
            return options["customer_id"]
        if options.get("company_id") is not None:
            try:
                company = NotaryClientCompany.objects.get(
                    pk=options["company_id"]
                )
            except NotaryClientCompany.DoesNotExist as exc:
                cid = options["company_id"]
                raise CommandError(
                    f"NotaryClientCompany id={cid} not found."
                ) from exc
            if not company.stripe_customer_id:
                raise CommandError(
                    f"Company {company.id} has no stripe_customer_id; "
                    "use --customer-id or create a customer first."
                )
            msg = (
                f"Using Stripe customer {company.stripe_customer_id} "
                f"({company.company_name})"
            )
            self.stdout.write(msg)
            return company.stripe_customer_id

        cust = create_stripe_customer(
            "Invoice test (test_stripe_invoice)",
            email="invoice-test@example.com",
            metadata={
                "source": "management_command",
                "command": "test_stripe_invoice",
            },
        )
        if not cust:
            raise CommandError("Failed to create ephemeral Stripe customer.")
        self.stdout.write(
            self.style.SUCCESS(f"Created ephemeral customer {cust.id}")
        )
        return cust.id

    def _company_default_payment_method(self, options):
        cid = options.get("company_id")
        if cid is None:
            return None
        try:
            company = NotaryClientCompany.objects.get(pk=cid)
        except NotaryClientCompany.DoesNotExist:
            return None
        return company.stripe_default_payment_method or None

    def _truncate_stripe_footer(self, text):
        if not text:
            return ""
        text = text.strip()
        if len(text) <= STRIPE_INVOICE_FOOTER_MAX_LEN:
            return text
        return text[: STRIPE_INVOICE_FOOTER_MAX_LEN - 3] + "..."

    def _html_to_stripe_footer(self, html_fragment):
        """Fallback: Stripe footer is plain text; collapse HTML to one line."""
        plain = strip_tags(html_fragment or "")
        plain = plain.replace("\n", " ")
        plain = re.sub(r"\s+", " ", plain).strip()
        return self._truncate_stripe_footer(plain)

    def _normalize_stripe_footer_text(self, text):
        """Trim lines; cap consecutive blank lines (readable in Stripe PDF)."""
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

    def _resolve_stripe_invoice_footer(self, options):
        if options.get("footer") is not None:
            return self._truncate_stripe_footer(options["footer"])

        oid = options.get("order_id")
        if oid is not None:
            try:
                order = Order.objects.get(pk=oid)
            except Order.DoesNotExist as exc:
                raise CommandError(f"Order id={oid} not found.") from exc
            order_status_emails_list = []
            raw_emails = getattr(order, "order_status_emails", None) or ""
            if raw_emails:
                order_status_emails_list = raw_emails.split("\n")
            ctx = {
                "order": order,
                "order_status_emails_list": order_status_emails_list,
            }
            footer = None
            try:
                raw = render_to_string(
                    "invoice_notes_stripe_footer.txt",
                    ctx,
                )
                footer = self._normalize_stripe_footer_text(raw)
            except TemplateDoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        "invoice_notes_stripe_footer.txt not found; "
                        "falling back to invoice_notes.html + strip_tags."
                    )
                )
            if footer is None:
                try:
                    html = render_to_string("invoice_notes.html", ctx)
                    footer = self._html_to_stripe_footer(html)
                except TemplateDoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            "invoice_notes.html not found; using placeholder."
                        )
                    )
                    footer = (
                        f"[Order #{order.id}] Add "
                        "templates/invoice_notes_stripe_footer.txt "
                        "or invoice_notes.html."
                    )
                    footer = self._truncate_stripe_footer(footer)
            footer = self._truncate_stripe_footer(footer)
            self.stdout.write(f"Footer from order {oid} ({len(footer)} chars).")
            return footer

        return self._truncate_stripe_footer(
            "Thank you — test invoice (test_stripe_invoice). "
            "Pass --order-id or --footer for GHL-style terms text."
        )

    def _resolve_invoice_payment_method_id(
        self,
        customer_id,
        *,
        payment_method_id,
        fallback_payment_method_id,
    ):
        if payment_method_id:
            self.stdout.write(f"Using payment method from flag: {payment_method_id}")
            return payment_method_id

        cust = stripe.Customer.retrieve(
            customer_id,
            expand=["invoice_settings.default_payment_method"],
        )
        inv_set = getattr(cust, "invoice_settings", None)
        dpm = getattr(inv_set, "default_payment_method", None) if inv_set else None
        if dpm:
            resolved = dpm if isinstance(dpm, str) else getattr(dpm, "id", None)
            if resolved:
                self.stdout.write(
                    f"Using customer invoice default payment method: {resolved}"
                )
                return resolved

        if fallback_payment_method_id:
            self.stdout.write(
                "Using NotaryClientCompany.stripe_default_payment_method: "
                f"{fallback_payment_method_id}"
            )
            return fallback_payment_method_id

        raise CommandError(
            "No payment method for Invoice.pay: pass --payment-method-id, "
            "set the Stripe customer's invoice_settings.default_payment_method, "
            "or use --company-id with stripe_default_payment_method set."
        )

    def _run_invoice_flow(
        self,
        customer_id,
        *,
        currency,
        payment_method_id,
        fallback_payment_method_id,
        footer_text,
    ):
        self.stdout.write(
            self.style.MIGRATE_HEADING("--- Native Invoice API (manual capture) ---")
        )

        pm_id = self._resolve_invoice_payment_method_id(
            customer_id,
            payment_method_id=payment_method_id,
            fallback_payment_method_id=fallback_payment_method_id,
        )

        inv_params = {
            "customer": customer_id,
            "collection_method": "charge_automatically",
            "auto_advance": False,
            "currency": currency,
            "description": (
                "Test invoice from Django test_stripe_invoice command"
            ),
            "footer": footer_text,
            "metadata": {
                "django_command": "test_stripe_invoice",
                "flow": "native_invoice_manual_capture",
            },
        }

        try:
            invoice = stripe.Invoice.create(**inv_params)
        except stripe.StripeError as e:
            raise CommandError(f"Invoice.create failed: {e}") from e

        self.stdout.write(
            f"Draft invoice: {invoice.id} (status={invoice.status})"
        )

        lines = [
            {
                "amount": 12_500,
                "description": "Custom line: bundled notary services (test)",
                "metadata": {"kind": "bundle", "test": "1"},
            },
            {
                "amount": 3_750,
                "description": "Custom line: order protection add-on",
                "metadata": {"kind": "protection"},
            },
            {
                "amount": 1_250,
                "description": "Custom line: expedited scheduling",
                "metadata": {"kind": "expedite"},
            },
        ]

        for line in lines:
            try:
                stripe.InvoiceItem.create(
                    customer=customer_id,
                    invoice=invoice.id,
                    currency=currency,
                    amount=line["amount"],
                    description=line["description"],
                    metadata=line["metadata"],
                )
            except stripe.StripeError as e:
                desc = line["description"]
                raise CommandError(
                    f"InvoiceItem.create failed for '{desc}': {e}"
                ) from e

        invoice = stripe.Invoice.retrieve(invoice.id)
        sub = getattr(invoice, "subtotal", None)
        tot = getattr(invoice, "total", None)
        self.stdout.write(
            f"Subtotal after lines: {sub} ({currency})  total={tot}"
        )

        try:
            stripe.Invoice.modify(
                invoice.id,
                payment_settings={
                    "payment_method_options": {
                        "card": {"capture_method": "manual"},
                    },
                },
            )
            self.stdout.write("Applied payment_settings.card.capture_method=manual")
        except stripe.InvalidRequestError as e:
            if "capture_method" in (getattr(e, "param", None) or ""):
                self.stdout.write(
                    self.style.WARNING(
                        "Stripe rejected capture_method on Invoice payment_settings "
                        "(current API); continuing without it — PI may not be "
                        "requires_capture after pay."
                    )
                )
            else:
                raise CommandError(
                    f"Invoice.modify (manual capture) failed: {e}"
                ) from e
        except stripe.StripeError as e:
            raise CommandError(f"Invoice.modify (manual capture) failed: {e}") from e

        try:
            invoice = stripe.Invoice.finalize_invoice(invoice.id)
        except stripe.StripeError as e:
            raise CommandError(f"finalize_invoice failed: {e}") from e

        self.stdout.write(
            self.style.SUCCESS(f"Finalized invoice {invoice.id} (status={invoice.status})")
        )

        try:
            invoice = stripe.Invoice.pay(
                invoice.id,
                payment_method=pm_id,
                off_session=True,
            )
        except stripe.StripeError as e:
            raise CommandError(
                f"Invoice.pay failed (no capture performed): {e}"
            ) from e

        self.stdout.write(
            self.style.SUCCESS(
                f"Invoice.pay succeeded (off_session) for invoice {invoice.id}"
            )
        )

        invoice = stripe.Invoice.retrieve(
            invoice.id,
            expand=["payment_intent"],
        )
        pi = getattr(invoice, "payment_intent", None)
        pi_id = pi if isinstance(pi, str) else (getattr(pi, "id", None) if pi else None)
        if not pi_id:
            raise CommandError(
                "Invoice has no payment_intent after pay; cannot capture."
            )

        pi_obj = (
            pi
            if not isinstance(pi, str)
            else stripe.PaymentIntent.retrieve(pi_id)
        )
        pi_status = getattr(pi_obj, "status", None)
        self.stdout.write(f"  payment_intent={pi_id} status={pi_status}")

        if pi_status != "requires_capture":
            self.stdout.write(
                self.style.WARNING(
                    f"Expected PaymentIntent status requires_capture for manual "
                    f"capture; got {pi_status}. Skipping capture."
                )
            )
        else:
            try:
                stripe.PaymentIntent.capture(pi_id)
            except stripe.StripeError as e:
                raise CommandError(f"PaymentIntent.capture failed: {e}") from e
            self.stdout.write(self.style.SUCCESS(f"Captured PaymentIntent {pi_id}"))

        invoice = stripe.Invoice.retrieve(
            invoice.id,
            expand=["payment_intent", "customer"],
        )
        self.stdout.write(f"  final invoice status={invoice.status}")
        self.stdout.write("\nInvoice (expanded) JSON:")
        self.stdout.write(self._to_json(invoice))

    def _run_checkout_invoice_flow(self, customer_id, *, currency, footer_text):
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "--- Checkout Session + invoice_creation ---"
            )
        )

        pd_desc = (
            "Mirrors dynamic price_data style used in create_stripe_session"
        )
        line_items = [
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": 4_200,
                    "product_data": {
                        "name": "Checkout test line (invoice_creation)",
                        "description": pd_desc,
                        "metadata": {"source": "test_stripe_invoice"},
                    },
                },
                "quantity": 2,
            }
        ]

        invoice_creation = {
            "enabled": True,
            "invoice_data": {
                "footer": footer_text,
                "description": (
                    "Checkout session test (invoice_creation); "
                    "footer mirrors GHL termsNotes via plain text."
                ),
                "metadata": {
                    "django_command": "test_stripe_invoice",
                    "path": "checkout_invoice_creation",
                },
            },
        }

        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="payment",
                line_items=line_items,
                invoice_creation=invoice_creation,
                success_url=(
                    "https://example.com/success?"
                    "session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url="https://example.com/cancel",
                payment_intent_data={
                    "capture_method": "manual",
                    "metadata": {
                        "django_command": "test_stripe_invoice",
                        "path": "checkout",
                    },
                },
            )
        except stripe.StripeError as e:
            raise CommandError(f"Checkout Session.create failed: {e}") from e

        self.stdout.write(
            self.style.SUCCESS(f"Checkout Session {session.id}")
        )
        self.stdout.write(f"  url={session.url}")
        self.stdout.write(
            "  Complete this URL in a browser (test mode). Stripe creates an "
            "Invoice when the session completes; retrieve the session to read "
            "the invoice id."
        )
        self.stdout.write("\nSession JSON:")
        self.stdout.write(self._to_json(session))

    def _to_json(self, stripe_obj):
        if hasattr(stripe_obj, "to_dict_recursive"):
            obj_dict = stripe_obj.to_dict_recursive()
        elif hasattr(stripe_obj, "to_dict"):
            obj_dict = stripe_obj.to_dict()
        else:
            obj_dict = stripe_obj
        return json.dumps(obj_dict, indent=2, default=str)
