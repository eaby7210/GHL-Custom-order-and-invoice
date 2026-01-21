from django.core.management.base import BaseCommand, CommandError
from order_page.services import TypeformService
import json

class Command(BaseCommand):
    help = 'Fetches a form definition from Typeform API and updates the local database'

    def add_arguments(self, parser):
        parser.add_argument('form_id', type=str, help='The ID of the Typeform form to sync')

    def handle(self, *args, **options):
        form_id = options['form_id']
        
        self.stdout.write(f"Syncing Typeform ID: {form_id}...")
        
        service = TypeformService()
        
        # Ensure we have a token
        if not service.access_token:
            raise CommandError("Typeform access token not configured in settings. Check TYPEFORM_ACCESS_TOKEN.")

        try:
            form_obj = service.sync_form(form_id)
            # data = service.get_form(form_id)
            self.stdout.write(self.style.SUCCESS(f"Successfully synced form: {form_obj.title} ({form_obj.form_id})"))
            # self.stdout.write(self.style.SUCCESS(f"Successfully got data {json.dumps(data, indent=2)}"))

            
            # Optional: Print stats
            self.stdout.write(f" - Fields: {form_obj.fields.count()}")
            self.stdout.write(f" - Welcome Screens: {form_obj.welcome_screens.count()}")
            self.stdout.write(f" - Thank You Screens: {form_obj.thankyou_screens_models.count()}")
            self.stdout.write(f" - Logic Rules: {form_obj.logics.count()}")
            
        except Exception as e:
            raise CommandError(f"Failed to sync form: {str(e)}")
