from django.core.management.base import BaseCommand
from tolt.services import ToltService
from tolt.models import Customer
import json
import time


class Command(BaseCommand):
    help = "Fetch all customers from Tolt and save/update them in the database"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Fetching Tolt customers..."))

        starting_after = None
        total_saved = 0
        total_updated = 0
        page_num = 1

        while True:
            try:
                response = ToltService.fetch_customers(
                    starting_after=starting_after,
                    per_page=2
                )
                print(json.dumps(response, indent=3))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Request failed: {e}"))
                break

            if not response.get("success"):
                self.stderr.write(self.style.ERROR(f"Tolt API error: {response}"))
                break

            data_block = response.get("data", {})
            customers = data_block.get("data", [])

            if not customers:
                self.stdout.write(self.style.WARNING("No more customers received."))
                break

            for item in customers:
                obj, created = Customer.create_or_update_from_api(item)
                if created:
                    total_saved += 1
                else:
                    total_updated += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Page {page_num}: {len(customers)} customers processed."
                )
            )

            # Pagination: stop if no more pages
            if not data_block.get("has_more"):
                break

            # Set cursor for next request
            starting_after = customers[-1]["id"]
            page_num += 1
            time.sleep(0.2)

        self.stdout.write(self.style.SUCCESS("Sync complete!"))
        self.stdout.write(self.style.SUCCESS(f"Customers created: {total_saved}"))
        self.stdout.write(self.style.SUCCESS(f"Customers updated: {total_updated}"))
