from django.core.management.base import BaseCommand
from core.services import ContactServices
import json

class Command(BaseCommand):
    help = 'Tests the GHL API query parameter by searching for a specific email'

    def add_arguments(self, parser):
        parser.add_argument('--location_id', type=str, required=True, help='Location ID for GHL API')
        parser.add_argument('--email', type=str, required=True, help='Email to search for using the query parameter')

    def handle(self, *args, **kwargs):
        location_id = kwargs['location_id']
        email = kwargs['email']

        self.stdout.write(f"Testing API query with email: {email} for location: {location_id}...")

        try:
            # Call the service method with the email as the query
            response_data = ContactServices.get_contact_list(
                location_id=location_id,
                query=email
            )

            contacts = response_data.get("contacts", [])
            
            self.stdout.write(f"API Response Status: Success")
            self.stdout.write(f"Contacts Found: {len(contacts)}")
            
            if contacts:
                self.stdout.write(json.dumps(contacts, indent=4))
                
                # Verification
                found = False
                for contact in contacts:
                    if contact.get('email', '').lower() == email.lower():
                        found = True
                        break
                
                if found:
                    self.stdout.write(self.style.SUCCESS(f"✅ Successfully found contact with email {email} using query parameter."))
                else:
                    self.stdout.write(self.style.WARNING(f"⚠️ Contacts returned, but exact email match not found in the list."))
            else:
                 self.stdout.write(self.style.WARNING(f"⚠️ No contacts found for query: {email}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ An error occurred: {e}"))
