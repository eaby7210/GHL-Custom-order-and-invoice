from django.core.management.base import BaseCommand
from core.models import OAuthToken
from core.services import TaskServices  # adjust path to where TaskServices is defined


class Command(BaseCommand):
    help = "Pull tasks for a selected LocationId from existing OAuthToken entries"

    def handle(self, *args, **options):
        tokens = OAuthToken.objects.all()
        if not tokens.exists():
            self.stdout.write(self.style.ERROR("No OAuth tokens found."))
            return

        self.stdout.write("Available Location IDs:\n")
        location_map = {}
        for idx, token in enumerate(tokens, start=1):
            label = f"{token.LocationId} ({token.company_name or 'No Name'})"
            location_map[str(idx)] = token.LocationId
            self.stdout.write(f"{idx}. {label}")

        selected = input("\nEnter the number of the Location ID you want to pull tasks for: ").strip()
        location_id = location_map.get(selected)

        if not location_id:
            self.stdout.write(self.style.ERROR("Invalid selection. Exiting."))
            return

        self.stdout.write(self.style.SUCCESS(f"Fetching tasks for Location ID: {location_id}..."))
        TaskServices.pull_tasks(location_id)
        self.stdout.write(self.style.SUCCESS("Task pulling complete."))
