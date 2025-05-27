from django.core.management.base import BaseCommand
from core.services import OAuthServices

class Command(BaseCommand):
    help = "Fetch a fresh access token for a given locationId."

    def handle(self, *args, **kwargs):
        try:
            location_id = input("Enter the LocationId: ").strip()
            if not location_id:
                self.stderr.write(self.style.ERROR("LocationId is required."))
                return

            access_token = OAuthServices.refresh_access_token(location_id)
            self.stdout.write(self.style.SUCCESS(f"Successfully retrieved new access token: {access_token}"))
        
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
