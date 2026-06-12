"""
Verify Stripe billing updates after an invoice is paid (test mode).

Stripe behavior (verified against test API):
- Invoice metadata: updatable after pay
- Invoice description: NOT updatable after finalize/pay (draft only)
- PaymentIntent metadata: updatable after succeeded

Usage:
  pipenv run bash -c 'export STRIPE_LIVE=False && python manage.py test_stripe_post_pay_update'
"""

import json

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from stripe_payment.utils import (
    create_stripe_customer,
    payment_intent_from_paid_invoice,
)


class Command(BaseCommand):
    help = (
        "Pay a test Stripe Invoice, then verify post-pay metadata/PI updates "
        "(uses STRIPE_SECRET_KEY_TEST when STRIPE_LIVE=False)."
    )

    def handle(self, *args, **options):
        if not settings.STRIPE_TEST:
            raise CommandError(
                "Refusing to run: STRIPE_LIVE is True. "
                "Set STRIPE_LIVE=False (or export before pipenv) to use test keys."
            )

        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.stdout.write(f"Using test key: {settings.STRIPE_SECRET_KEY[:12]}...")

        cust = create_stripe_customer(
            "Post-pay update test",
            email="post-pay-update-test@example.com",
            metadata={"source": "test_stripe_post_pay_update"},
        )
        if not cust:
            raise CommandError("Failed to create test customer.")
        self.stdout.write(f"Customer: {cust.id}")

        pm = stripe.PaymentMethod.create(
            type="card",
            card={"token": "tok_visa"},
        )
        stripe.PaymentMethod.attach(pm.id, customer=cust.id)

        invoice = stripe.Invoice.create(
            customer=cust.id,
            collection_method="charge_automatically",
            auto_advance=False,
            currency="usd",
            description="Order #99999 — Post-pay update test",
            metadata={"order_id": "99999", "source": "checkout_pending"},
        )
        stripe.InvoiceItem.create(
            customer=cust.id,
            invoice=invoice.id,
            currency="usd",
            amount=500,
            description="Test line item",
        )
        invoice = stripe.Invoice.finalize_invoice(invoice.id)
        invoice = stripe.Invoice.pay(
            invoice.id,
            payment_method=pm.id,
            off_session=True,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Paid invoice {invoice.id} status={invoice.status}")
        )

        invoice = stripe.Invoice.retrieve(
            invoice.id,
            expand=["payments.data.payment.payment_intent"],
        )
        pi = payment_intent_from_paid_invoice(invoice)
        if not pi:
            raise CommandError("No PaymentIntent on paid invoice.")

        fake_notary_id = "12345678"

        # Metadata on paid invoice — allowed
        inv_meta = stripe.Invoice.modify(
            invoice.id,
            metadata={
                "order_id": "99999",
                "source": f"NotaryDash Order #{fake_notary_id}",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Invoice metadata after pay: {json.dumps(dict(inv_meta.metadata or {}))}"
            )
        )

        # Description on paid invoice — rejected by Stripe
        desc_blocked = False
        try:
            stripe.Invoice.modify(
                invoice.id,
                description=f"Order #{fake_notary_id} — Post-pay update test",
            )
        except stripe.InvalidRequestError as e:
            desc_blocked = True
            self.stdout.write(
                self.style.WARNING(
                    f"Invoice description after pay blocked (expected): {e.user_message or e}"
                )
            )

        # PaymentIntent metadata after pay — allowed
        pi_after = stripe.PaymentIntent.modify(
            pi.id,
            metadata={
                **dict(pi.metadata or {}),
                "notarydash_order_id": fake_notary_id,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"PaymentIntent metadata after pay: "
                f"{json.dumps(dict(pi_after.metadata or {}))}"
            )
        )

        if (inv_meta.metadata or {}).get("source") != f"NotaryDash Order #{fake_notary_id}":
            raise CommandError("Invoice metadata was not updated.")
        if not desc_blocked:
            raise CommandError(
                "Expected Stripe to reject description update on paid invoice."
            )
        if (pi_after.metadata or {}).get("notarydash_order_id") != fake_notary_id:
            raise CommandError("PaymentIntent metadata was not updated.")

        self.stdout.write(
            self.style.SUCCESS(
                "OK: post-pay invoice metadata + PaymentIntent metadata work; "
                "description must be set on draft before finalize."
            )
        )
