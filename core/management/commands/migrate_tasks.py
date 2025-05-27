from django.core.management.base import BaseCommand
from core.models import OAuthToken
import os, json
from core.services import TaskServices

class Command(BaseCommand):
    help = "Migrate tasks from one location to another based on contact phone numbers."

    def handle(self, *args, **options):
        locations = list(OAuthToken.objects.values_list("LocationId", flat=True).distinct())

        if not locations:
            self.stdout.write(self.style.ERROR("No locations found in OAuth model."))
            return

        self.stdout.write("📍 Available Location IDs:")
        for i, loc_id in enumerate(locations, start=1):
            self.stdout.write(f"{i}. {loc_id}")

        try:
            source_index = int(input("\n🔁 Enter the number of the *source* location: ")) - 1
            target_index = int(input("➡️ Enter the number of the *target* location: ")) - 1

            source_location_id = locations[source_index]
            target_location_id = locations[target_index]

            self.stdout.write(self.style.WARNING(
                f"\n⚠️  You are about to migrate tasks FROM {source_location_id} TO {target_location_id}.\n"
            ))

            confirm = input("Type 'yes' to continue: ").strip().lower()
            if confirm != "yes":
                self.stdout.write(self.style.ERROR("❌ Migration aborted by user."))
                return

            task_plan = TaskServices.generate_task_plan(source_location_id, target_location_id)
            output_path = os.path.join(os.getcwd(), "task_plan.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(task_plan, f, indent=4)

            self.stdout.write(f"\n🧾 Total tasks ready to migrate: {len(task_plan)}")

            confirm_migration = input("Do you want to proceed with migrating these tasks? (yes/no): ").strip().lower()
            if confirm_migration != "yes":
                self.stdout.write(self.style.ERROR("❌ Migration aborted by user."))
                return

            migrated_tasks = TaskServices.migrate_tasks(task_plan, target_location_id)
            self.stdout.write(f"\n✅ Successfully migrated {len(migrated_tasks)} tasks.")

            rollback_confirm = input("Do you want to rollback the migrated tasks? (yes/no): ").strip().lower()
            if rollback_confirm == "yes":
                TaskServices.rollback_tasks(migrated_tasks, target_location_id)
            else:
                self.stdout.write("\n✅ Migration confirmed. No rollback performed.")

        except (IndexError, ValueError):
            self.stdout.write(self.style.ERROR("Invalid selection. Please enter valid numbers from the list."))
