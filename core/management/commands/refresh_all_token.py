from django.core.management.base import BaseCommand
from core.services import OAuthServices
from core.models import OAuthToken  

class Command(BaseCommand):
    help = "Refresh access tokens for all stored OAuthToken location IDs."

    def handle(self, *args, **kwargs):
        try:
            location_ids = list(OAuthToken.objects.values_list('LocationId', flat=True))
            if not location_ids:
                self.stdout.write(self.style.WARNING("No LocationIds found."))
                return

            self.stdout.write(self.style.SUCCESS(f"Found {len(location_ids)} LocationIds. Starting refresh..."))

            for location_id in location_ids:
                try:
                    token_obj = OAuthServices.refresh_access_token(location_id)
                    self.stdout.write(self.style.SUCCESS(f"[{location_id}] Token refreshed successfully: {token_obj}"))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"[{location_id}] Failed to refresh token: {e}"))
        
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Unexpected Error: {e}"))
