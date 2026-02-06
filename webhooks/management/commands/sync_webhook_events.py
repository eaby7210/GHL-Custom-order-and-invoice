from django.core.management.base import BaseCommand
from webhooks.models import WebhookEvent
from webhooks.constants import WEBHOOK_EVENT_DESCRIPTIONS

class Command(BaseCommand):
    help = 'Syncs webhook events defined in constants to the database'

    def handle(self, *args, **options):
        self.stdout.write("Syncing webhook events...")
        
        count = 0
        for event_name, description in WEBHOOK_EVENT_DESCRIPTIONS.items():
            obj, created = WebhookEvent.objects.update_or_create(
                name=event_name,
                defaults={'description': description}
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} event: {event_name}")
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f"Successfully synced {count} webhook events."))
