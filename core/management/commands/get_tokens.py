from django.core.management.base import BaseCommand
from core.services import OAuthServices

class Command(BaseCommand):
    help = "Fetch a fresh access token using the provided authorization code."

    def add_arguments(self, parser):
       parser.add_argument("--auth-code", type=str, required=True, help="Authorization code for generating fresh access token")


    def handle(self, *args, **kwargs):
        auth_code = kwargs["auth_code"]
        
        try:
            token_obj = OAuthServices.get_fresh_token(auth_code)
            self.stdout.write(self.style.SUCCESS(f"Successfully retrieved new access token: {token_obj.access_token}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
