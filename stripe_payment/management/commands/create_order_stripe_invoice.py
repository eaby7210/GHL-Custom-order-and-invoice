"""
Create a draft Stripe Invoice using views.create_stripe_invoice_for_order.

Fetches payment-related data from a Stripe Event (evt_...) and client profile
from NotaryDashServices.get_client_one_user(company_id, user_id).

Example:

    python manage.py create_order_stripe_invoice \\
        --order-id 42 \\
        --event-id evt_xxx \\
        --company-id 123 \\
        --client-id 456
"""

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from stripe_payment.models import Order
from stripe_payment.services import NotaryDashServices
from stripe_payment.views import create_stripe_invoice_for_order


def _stripe_object_to_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise CommandError(f"Cannot convert Stripe value to dict: {type(obj)!r}")


class Command(BaseCommand):
    help = (
        "Create a draft Stripe Invoice for an order (see "
        "create_stripe_invoice_for_order). Loads data.object from Stripe "
        "Event.retrieve(event_id) and client_user from get_client_one_user."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--order-id",
            type=int,
            required=True,
            help="Local Order primary key.",
        )
        parser.add_argument(
            "--event-id",
            type=str,
            required=True,
            help=(
                "Stripe Event id (evt_...). data.object must be "
                "checkout.session or payment_intent."
            ),
        )
        parser.add_argument(
            "--company-id",
            type=str,
            default=None,
            help=(
                "Notary client id for NotaryDash clients/{id}/users/{user_id}. "
                "Defaults to order.company_id."
            ),
        )
        parser.add_argument(
            "--client-id",
            type=str,
            default=None,
            help=(
                "Notary user id for get_client_one_user. "
                "Defaults to order.user_id."
            ),
        )
        parser.add_argument(
            "--stripe-customer-id",
            type=str,
            default=None,
            help=(
                "Override Stripe cus_... (default: NotaryClientCompany "
                "stripe_customer_id)."
            ),
        )
        parser.add_argument(
            "--currency",
            type=str,
            default="usd",
            help="Three-letter ISO currency (default: usd).",
        )
        parser.add_argument(
            "--skip-event-discount",
            action="store_true",
            help=(
                "Do not apply amount_discount from the event payment object."
            ),
        )
        parser.add_argument(
            "--skip-manual-capture",
            action="store_true",
            help=(
                "Do not set payment_settings card capture_method=manual."
            ),
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        order_id = options["order_id"]
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist as exc:
            raise CommandError(f"Order id={order_id} not found.") from exc

        company_id = options["company_id"] or order.company_id
        client_id = options["client_id"] or order.user_id
        if not company_id:
            raise CommandError(
                "Missing company id: pass --company-id or set order.company_id."
            )
        if not client_id:
            raise CommandError(
                "Missing client user id: pass --client-id or set order.user_id."
            )

        self.stdout.write(
            "Fetching NotaryDash user "
            f"client_id={company_id!r} user_id={client_id!r}..."
        )
        raw_user = NotaryDashServices.get_client_one_user(company_id, client_id)
        client_user = raw_user.get("data", {}) if raw_user else {}
        if not client_user:
            raise CommandError(
                "get_client_one_user returned no data; check ids and API."
            )

        event_id = options["event_id"]
        self.stdout.write(f"Fetching Stripe event {event_id!r}...")
        try:
            event = stripe.Event.retrieve(event_id)
        except stripe.StripeError as exc:
            raise CommandError(f"Stripe Event.retrieve failed: {exc}") from exc

        inner = None
        if hasattr(event, "data") and event.data is not None:
            inner = getattr(event.data, "object", None)
        if inner is None:
            try:
                inner = event["data"]["object"]
            except (KeyError, TypeError):
                inner = None
        event_obj = _stripe_object_to_dict(inner)
        if not event_obj.get("object"):
            raise CommandError(
                "Event has no usable data.object with an 'object' field; "
                "use checkout.session or payment_intent events."
            )

        invoice = create_stripe_invoice_for_order(
            order,
            event_obj,
            client_user,
            stripe_customer_id=options["stripe_customer_id"],
            currency=options["currency"],
            apply_event_discount=not options["skip_event_discount"],
            manual_capture=not options["skip_manual_capture"],
        )

        msg = (
            f"Draft Stripe invoice {invoice.id} created "
            f"(status={invoice.status}, order={order_id})."
        )
        self.stdout.write(self.style.SUCCESS(msg))
