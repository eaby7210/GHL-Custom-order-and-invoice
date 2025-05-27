from django.core.management.base import BaseCommand
from core.models import Contact
import json
import os
from django.conf import settings

LOG_DIR = os.path.join(settings.BASE_DIR, "logs")
MATCHED_CONTACTS_FILE = os.path.join(LOG_DIR, "matched_target_contacts.json")
UNMATCHED_CONTACTS_FILE = os.path.join(LOG_DIR, "unmatched_source_contacts.json")


class Command(BaseCommand):
    help = "Save matched and unmatched target contacts to separate JSON files."

    @staticmethod
    def save_contact_matches(source_location_id, target_location_id):
        os.makedirs(LOG_DIR, exist_ok=True)

        source_contacts = Contact.objects.filter(location_id=source_location_id, phone__isnull=False)
        target_contacts_by_phone = {
            c.phone.strip(): c for c in Contact.objects.filter(location_id=target_location_id, phone__isnull=False)
        }

        matched_contacts = []
        unmatched_contacts = []

        for source_contact in source_contacts:
            phone = source_contact.phone.strip()
            target_contact = target_contacts_by_phone.get(phone)

            if target_contact:
                matched_contacts.append({
                    "id": target_contact.id,
                    "first_name": target_contact.first_name,
                    "last_name": target_contact.last_name,
                    "email": target_contact.email,
                    "phone": target_contact.phone,
                    "location_id": target_contact.location_id
                })
            else:
                unmatched_contacts.append({
                    "id": source_contact.id,
                    "first_name": source_contact.first_name,
                    "last_name": source_contact.last_name,
                    "email": source_contact.email,
                    "phone": source_contact.phone,
                    "location_id": source_contact.location_id
                })

        # Save matched contacts
        try:
            with open(MATCHED_CONTACTS_FILE, "w") as f:
                json.dump({
                    "meta": {
                        "matched_target_contact_count": len(matched_contacts),
                        "total_source_contacts": len(source_contacts)
                    },
                    "matched_contacts": matched_contacts
                }, f, indent=2)
            print(f"✅ Matched contacts saved to {MATCHED_CONTACTS_FILE}")
        except Exception as e:
            print(f"❌ Failed to save matched contacts: {str(e)}")

        # Save unmatched contacts
        try:
            with open(UNMATCHED_CONTACTS_FILE, "w") as f:
                json.dump({
                    "meta": {
                        "unmatched_source_contact_count": len(unmatched_contacts),
                        "total_source_contacts": len(source_contacts)
                    },
                    "source_but_not_in_target": unmatched_contacts
                }, f, indent=2)
            print(f"✅ Unmatched contacts saved to {UNMATCHED_CONTACTS_FILE}")
        except Exception as e:
            print(f"❌ Failed to save unmatched contacts: {str(e)}")

    def handle(self, *args, **kwargs):
        try:
            Command.save_contact_matches('1XYDcIkUrFWFYq7nHqF6', 'HBMH06bPfTaKkZx49Y4x')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))
