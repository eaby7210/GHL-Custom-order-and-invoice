import stripe
import json
from django.core.management.base import BaseCommand
from django.conf import settings
from stripe_payment.models import Order, StripeWebhookEventLog
from stripe_payment.views import process_order

class Command(BaseCommand):
    help = 'Rerun process_order for a specific Stripe event and Order'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=str, help='Stripe Event ID (evt_...)')
        parser.add_argument('order_id', type=int, help='Local Order ID')

    def handle(self, *args, **kwargs):
        event_id = kwargs['event_id']
        order_id = kwargs['order_id']
        
        stripe.api_key = settings.STRIPE_SECRET_KEY

        self.stdout.write(f"Fetching Order {order_id}...")
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Order {order_id} not found."))
            return

        self.stdout.write(f"Fetching Stripe Event {event_id}...")
        try:
            # Try fetching from Stripe API for fresh data
            event = stripe.Event.retrieve(event_id)
            # Convert to dict wrapper behavior similar to webhook payload if needed? 
            # The process_order expects a dict with 'data' -> 'object' structure usually found in webhook JSON.
            # stripe.Event.retrieve returns a StripeObject which behaves like a dict but structure might slightly differ 
            # from the raw webhook JSON wrapper.
            # Webhook JSON: { "id": "evt_...", "type": "...", "data": { "object": { ... } } }
            # stripe.Event.retrieve returns the Event object directly.
            
            # process_order uses: obj = event['data']['object']
            # So we need to ensure the passed 'event' structure matches.
            # The stripe library object supports __getitem__.
            
            # Let's double check if we can use the local log if available for exact replay?
            # User said "take an stripe event_id".
            # Using API is safer.
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not fetch from Stripe API: {e}"))
            self.stdout.write("Checking local Webhook Logs...")
            log = StripeWebhookEventLog.objects.filter(event_id=event_id).first()
            if log:
                # Reconstruct event dict
                event_dict = {
                    'id': log.event_id,
                    'object': 'event',
                    'type': log.event_type,
                    'data': {
                        'object': json.loads(log.event_data)
                    }
                }
                # Convert dict to Stripe Event Object to support dot notation (like event.data.object.id)
                # required by build_invoice_payload
                event = stripe.Event.construct_from(event_dict, stripe.api_key)
            else:
                self.stdout.write(self.style.ERROR(f"Event {event_id} not found in Stripe or DB."))
                return

        self.stdout.write(self.style.SUCCESS(f"Processing Order {order_id} with Event {event_id}..."))
        
        try:
            process_order(event, order)
            self.stdout.write(self.style.SUCCESS("Function execution completed (check logs for specific output)."))

        except Exception as e:
             self.stdout.write(self.style.ERROR(f"Error executing process_order: {e}"))
             import traceback
             self.stdout.write(traceback.format_exc())
