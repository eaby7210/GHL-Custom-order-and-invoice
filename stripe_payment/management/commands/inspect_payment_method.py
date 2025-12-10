from django.core.management.base import BaseCommand
import stripe
from django.conf import settings
import json

class Command(BaseCommand):
    help = 'Inspect a Stripe Payment Method'

    def add_arguments(self, parser):
        parser.add_argument('payment_method_id', type=str, help='The ID of the Payment Method')

    def handle(self, *args, **kwargs):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        pm_id = kwargs['payment_method_id']

        self.stdout.write(f"Inspect Payment Method: {pm_id}")
        self.stdout.write(f"Using Secret Key: {settings.STRIPE_SECRET_KEY[:8]}...")

        try:
            pm = stripe.PaymentMethod.retrieve(pm_id)
            self.stdout.write(self.style.SUCCESS(f"✅ Found Payment Method: {pm.id}"))
            self.stdout.write(f"Type: {pm.type}")
            if pm.type == 'card':
                self.stdout.write(f"Card: {pm.card.brand} - {pm.card.last4} (exp {pm.card.exp_month}/{pm.card.exp_year})")
            
            cust_id = pm.customer
            self.stdout.write(f"Attached to Customer: {cust_id}")

            if cust_id:
                cust = stripe.Customer.retrieve(cust_id)
                self.stdout.write(f"Customer Default Source: {cust.default_source}")
                self.stdout.write(f"Customer Default Payment Method: {cust.invoice_settings.default_payment_method}")
            
        except stripe.InvalidRequestError as e:
            self.stdout.write(self.style.ERROR(f"❌ Stripe Error: {e}"))
            if "No such PaymentMethod" in str(e):
                self.stdout.write(self.style.WARNING("This usually means the Payment Method does not exist on this account. Check if keys match."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
