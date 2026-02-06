from django.core.management.base import BaseCommand
from webhooks.models import WebhookEvent, WebhookEndpoint
from webhooks.services import dispatch_webhook_event
import json

class Command(BaseCommand):
    help = 'Sends a test webhook event to all active endpoints.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--event',
            type=str,
            default='test.event',
            help='Name of the event to trigger (default: test.event)'
        )
        parser.add_argument(
            '--payload',
            type=str,
            default='{"message": "This is a test webhooks payload"}',
            help='JSON payload to send (default: {"message": ...})'
        )

    def handle(self, *args, **options):
        event_name = options['event']
        payload_str = options['payload']

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR('Invalid JSON payload'))
            return

        # Ensure event exists or create it for testing
        event, created = WebhookEvent.objects.get_or_create(
            name=event_name,
            defaults={'description': 'Test event created by management command'}
        )
        if created:
            self.stdout.write(self.style.WARNING(f"Created new event '{event_name}'"))
        
        # Check for active endpoints
        endpoints = WebhookEndpoint.objects.filter(events=event, is_active=True)
        if not endpoints.exists():
            self.stdout.write(self.style.WARNING(f"No active endpoints found for event '{event_name}'. Creating a dummy endpoint if none exist..."))
            # Optional: Create a dummy endpoint if user wants, or just warn
            # For now, just warn.

        self.stdout.write(f"Dispatching event '{event_name}' with payload: {payload}")
        dispatch_webhook_event(event_name, payload)
        self.stdout.write(self.style.SUCCESS(f"Successfully dispatched event '{event_name}'"))
