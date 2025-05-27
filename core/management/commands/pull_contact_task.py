from django.core.management.base import BaseCommand
from core.models import Contact
from core.services import TaskServices


class Command(BaseCommand):
    help = "Pull tasks for a specific contact using contact ID"

    def handle(self, *args, **kwargs):
        contact_id = input("Enter the Contact ID: ").strip()

        try:
            contact = Contact.objects.get(id=contact_id)
        except Contact.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Contact with ID {contact_id} not found."))
            return

        location_id = contact.location_id
        self.stdout.write(f"📥 Pulling tasks for Contact ID {contact_id} (Location ID: {location_id})")

        task_data_list = TaskServices.get_task_list(location_id, contact)
        if not task_data_list:
            self.stdout.write(self.style.WARNING("⚠️ No tasks found for this contact."))
            return

        created_count = 0
        updated_count = 0

        for task_data in task_data_list:
            result = TaskServices.save_task(task_data)
            if result:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Task pull complete. Created: {created_count}, Updated: {updated_count}"))
