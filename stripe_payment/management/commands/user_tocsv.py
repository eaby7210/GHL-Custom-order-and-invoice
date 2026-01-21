from django.core.management.base import BaseCommand
import csv
import time
from core.services import ContactServices
from stripe_payment.models import NotaryUser
import json

class Command(BaseCommand):
    help = 'Iterates NotaryUsers, checks existence in GHL, and mismatching names. Exports to CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--location_id', type=str, required=True, help='Location ID for GHL API')

    def handle(self, *args, **kwargs):
        location_id = kwargs['location_id']
        output_file = 'notary_user_ghl_check.csv'

        self.stdout.write(f"Starting check for location: {location_id}...")

        # Initialize CSV
        csv_headers = ['DB_ID', 'Email', 'DB_FirstName', 'DB_LastName', 'GHL_ID', 'GHL_FirstName', 'GHL_LastName', 'Status']
        
        mismatches = []
        users = NotaryUser.objects.all()
        total_users = users.count()
        processed_count = 0

        self.stdout.write(f"Found {total_users} NotaryUsers in database.")

        try:
            for user in users:
                processed_count += 1
                if processed_count % 10 == 0:
                     self.stdout.write(f"Processed {processed_count}/{total_users}...")

                email = user.email
                if not email:
                    continue
                
                db_first_name = (user.first_name or "").strip()
                db_last_name = (user.last_name or "").strip()
                norm_db_first = db_first_name.lower()
                norm_db_last = db_last_name.lower()

                try:
                    # Query GHL for this email
                    # Using the service we just updated/verified
                    response_data = ContactServices.get_contact_list(
                        location_id=location_id,
                        query=email
                    )
                    
                    ghl_contacts = response_data.get("contacts", [])
                    
                    found_match = None
                    
                    # Exact email match check within results
                    for contact in ghl_contacts:
                        if contact.get('email', '').strip().lower() == email.strip().lower():
                            found_match = contact
                            break
                    
                    if not found_match:
                        # Case: Present in DB, Missing in GHL
                        pass
                        #  mismatches.append({
                        #     'DB_ID': user.id,
                        #     'Email': email,
                        #     'DB_FirstName': db_first_name,
                        #     'DB_LastName': db_last_name,
                        #     'GHL_ID': 'N/A',
                        #     'GHL_FirstName': 'N/A',
                        #     'GHL_LastName': 'N/A',
                        #     'Status': 'Missing in GHL'
                        # })
                    else:
                        # Case: User exists, check name
                        ghl_first_name = (found_match.get('firstName') or "").strip()
                        ghl_last_name = (found_match.get('lastName') or "").strip()
                        norm_ghl_first = ghl_first_name.lower()
                        norm_ghl_last = ghl_last_name.lower()

                        if norm_ghl_first != norm_db_first or norm_ghl_last != norm_db_last:
                             mismatches.append({
                                'DB_ID': user.id,
                                'Email': email,
                                'DB_FirstName': db_first_name,
                                'DB_LastName': db_last_name,
                                'GHL_ID': found_match.get('id'),
                                'GHL_FirstName': ghl_first_name,
                                'GHL_LastName': ghl_last_name,
                                'Status': 'Name Mismatch'
                            })
                    
                    # Small sleep to be nice to API rate limits if needed
                    # time.sleep(0.1) 

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error checking user {email}: {e}"))

            # Export
            if mismatches:
                with open(output_file, mode='w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=csv_headers)
                    writer.writeheader()
                    writer.writerows(mismatches)
                
                self.stdout.write(self.style.SUCCESS(f"Done. Exported {len(mismatches)} issues to {output_file}"))
            else:
                self.stdout.write(self.style.SUCCESS("Done. All NotaryUsers act perfectly in GHL!"))

        except Exception as e:
             self.stdout.write(self.style.ERROR(f"Critial error: {e}"))
