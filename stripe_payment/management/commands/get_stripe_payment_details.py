from django.core.management.base import BaseCommand
import stripe
from django.conf import settings
import json

class Command(BaseCommand):
    help = 'Retrieves and prints details of a Stripe Payment (PaymentIntent, Session, or Event)'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--payment-intent', '-p', type=str, help='The ID of the PaymentIntent to retrieve')
        group.add_argument('--session', '-s', type=str, help='The ID of the Checkout Session to retrieve')
        group.add_argument('--event', '-e', type=str, help='The ID of the Webhook Event to retrieve')

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            if options.get('event'):
                event_id = options['event']
                event = stripe.Event.retrieve(event_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully retrieved Event: {event_id}"))
                self._print_json(event)
                
                # Check if it contains a Checkout Session or PaymentIntent
                if getattr(event, 'data', None) and getattr(event.data, 'object', None):
                    obj = event.data.object
                    if getattr(obj, 'object', None) == 'checkout.session':
                        self.stdout.write(self.style.SUCCESS(f"\nEmbedded Checkout Session Event Date:"))
                        self._print_json(obj)
                        if getattr(obj, 'payment_intent', None):
                            self._retrieve_and_print_payment_intent(obj.payment_intent)
                    elif getattr(obj, 'object', None) == 'payment_intent':
                        self.stdout.write(self.style.SUCCESS(f"\nEmbedded PaymentIntent Event Data:"))
                        self._print_json(obj)
            
            elif options.get('session'):
                session_id = options['session']
                session = stripe.checkout.Session.retrieve(session_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully retrieved Checkout Session: {session_id}"))
                self._print_json(session)
                
                if getattr(session, 'payment_intent', None):
                    self._retrieve_and_print_payment_intent(session.payment_intent)

            elif options.get('payment_intent'):
                payment_intent_id = options['payment_intent']
                self._retrieve_and_print_payment_intent(payment_intent_id)

        except stripe.error.StripeError as e:
            self.stdout.write(self.style.ERROR(f"Stripe Error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            
    def _retrieve_and_print_payment_intent(self, payment_intent_id):
        if not isinstance(payment_intent_id, str):
            payment_intent_id = getattr(payment_intent_id, 'id', str(payment_intent_id))
            
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully retrieved PaymentIntent: {payment_intent_id}"))
        self._print_json(intent)

        # Try to find related Checkout Session
        sessions = stripe.checkout.Session.list(payment_intent=payment_intent_id, limit=1)
        if sessions and sessions.data:
            session = sessions.data[0]
            self.stdout.write(self.style.SUCCESS(f"\nRelated Checkout Session Found: {session.id}"))
            self._print_json(session)
        else:
            self.stdout.write(self.style.WARNING("\nNo related Checkout Session found for this PaymentIntent."))

    def _print_json(self, stripe_obj):
        if hasattr(stripe_obj, 'to_dict_recursive'):
            obj_dict = stripe_obj.to_dict_recursive()
        elif hasattr(stripe_obj, 'to_dict'):
            obj_dict = stripe_obj.to_dict()
        else:
            obj_dict = stripe_obj

        self.stdout.write(json.dumps(obj_dict, indent=4, default=str))
