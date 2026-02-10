
from django.core.management.base import BaseCommand
import stripe
from django.conf import settings
import json

class Command(BaseCommand):
    help = 'Retrieves and prints details of a Stripe PaymentIntent by ID'

    def add_arguments(self, parser):
        parser.add_argument('payment_intent_id', type=str, help='The ID of the PaymentIntent to retrieve')

    def handle(self, *args, **options):
        payment_intent_id = options['payment_intent_id']
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            self.stdout.write(self.style.SUCCESS(f"Successfully retrieved PaymentIntent: {payment_intent_id}"))
            
            # Convert the Stripe object to a dictionary for pretty printing
            if hasattr(intent, 'to_dict_recursive'):
                intent_dict = intent.to_dict_recursive()
            elif hasattr(intent, 'to_dict'):
                intent_dict = intent.to_dict()
            else:
                intent_dict = intent

            self.stdout.write(json.dumps(intent_dict, indent=4, default=str))

            # Try to find related Checkout Session
            sessions = stripe.checkout.Session.list(payment_intent=payment_intent_id, limit=1)
            if sessions and sessions.data:
                session = sessions.data[0]
                self.stdout.write(self.style.SUCCESS(f"\nRelated Checkout Session Found: {session.id}"))
                self.stdout.write(json.dumps(session.to_dict_recursive() if hasattr(session, 'to_dict_recursive') else session, indent=4, default=str))
            else:
                self.stdout.write(self.style.WARNING("\nNo related Checkout Session found for this PaymentIntent."))

        except stripe.error.StripeError as e:
            self.stdout.write(self.style.ERROR(f"Stripe Error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
