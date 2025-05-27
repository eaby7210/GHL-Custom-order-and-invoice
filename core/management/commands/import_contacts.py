import os
import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Contact  
from django.utils.timezone import now

class Command(BaseCommand):
    help = "Import contacts from a CSV file into the Contact model"

    def add_arguments(self, parser):
        parser.add_argument("csv_filename", type=str, help="CSV file name (located in BASE_DIR)")

    def handle(self, *args, **kwargs):
        csv_filename = kwargs["csv_filename"]
        base_dir = getattr(settings, "BASE_DIR", None)

        if not base_dir:
            self.stderr.write(self.style.ERROR("BASE_DIR is not defined in settings."))
            return

        csv_file_path = os.path.join(base_dir, csv_filename)

        if not os.path.exists(csv_file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file_path}"))
            return

        # Prompt for location ID once
        location_id = input("Enter the location ID for these contacts: ").strip()

        try:
            with open(csv_file_path, newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)

                contacts_to_create = []
                contacts_to_update = []

                # Load existing contacts once into a dictionary
                existing_contacts = {str(c.id): c for c in Contact.objects.all()}

                for row in reader:
                    contact_id = row.get("Contact Id", "").strip()
                    if not contact_id:
                        continue  # Skip invalid rows

                    first_name = row.get("First Name", "").strip()
                    last_name = row.get("Last Name", "").strip()
                    email = row.get("Email", "").strip()
                    phone = row.get("Phone", "").strip()
                    created = row.get("Created", "").strip()
                    last_activity = row.get("Last Activity", "").strip()
                    tags = row.get("Tags", "").strip().lower()

                    created_at = self.parse_date(created) or now()
                    updated_at = self.parse_date(last_activity) or created_at

                    # Guess type and dnd from tags
                    contact_type = "lead" if "lead" in tags else "customer" if "customer" in tags else None
                    dnd = "dnd" in tags

                    if contact_id in existing_contacts:
                        # Update existing contact
                        contact = existing_contacts[contact_id]
                        contact.first_name = first_name
                        contact.last_name = last_name
                        contact.email = email
                        contact.phone = phone
                        contact.date_added = created_at
                        contact.date_updated = updated_at
                        contact.type = contact_type
                        contact.dnd = dnd
                        contact.location_id = location_id
                        contacts_to_update.append(contact)
                    else:
                        # Create new contact
                        contacts_to_create.append(
                            Contact(
                                id=contact_id,
                                first_name=first_name,
                                last_name=last_name,
                                email=email,
                                phone=phone,
                                date_added=created_at,
                                date_updated=updated_at,
                                type=contact_type,
                                dnd=dnd,
                                location_id=location_id,
                            )
                        )

                # Perform bulk operations
                if contacts_to_create:
                    Contact.objects.bulk_create(contacts_to_create)
                if contacts_to_update:
                    Contact.objects.bulk_update(
                        contacts_to_update,
                        ["first_name", "last_name", "email", "phone", "date_added", "date_updated", "type", "dnd", "location_id"]
                    )

            self.stdout.write(self.style.SUCCESS(
                f"Successfully imported {len(contacts_to_create)} new contacts and updated {len(contacts_to_update)} existing contacts."
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error importing contacts: {e}"))

    def parse_date(self, date_str):
        """Helper method to parse ISO date format"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None
