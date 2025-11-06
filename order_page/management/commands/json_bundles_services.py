import json
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from order_page.models import BundleGroup, Bundle  # ✅ Change `yourapp` to your actual app name


class Command(BaseCommand):
    help = "Import bundle groups and bundles from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to the JSON file containing bundle group data."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = options["file_path"]

        # ---------------------------------------------------------------------
        # Load JSON file
        # ---------------------------------------------------------------------
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise CommandError(f"❌ Error reading file: {e}")

        header = data.get("header")
        subheader = data.get("subheader")
        bundles = data.get("BUNDLES", [])

        if not header or not bundles:
            raise CommandError("❌ Invalid JSON format: 'header' or 'BUNDLES' missing.")

        # ---------------------------------------------------------------------
        # Create or update BundleGroup
        # ---------------------------------------------------------------------
        group, created = BundleGroup.objects.update_or_create(
            header=header,
            defaults={
                "subheader": subheader,
                "name": header,
                "is_active": True,
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.MIGRATE_HEADING(f"📦 {action} BundleGroup: {group.header}"))

        # ---------------------------------------------------------------------
        # Create Bundles under this group
        # ---------------------------------------------------------------------
        for idx, bundle_data in enumerate(bundles, start=1):
            name = bundle_data.get("name")
            description = bundle_data.get("description", "")
            base_price = Decimal(bundle_data.get("basePrice", 0))
            discounted_price = Decimal(bundle_data.get("price", 0))

            if not name:
                self.stdout.write(self.style.WARNING(f"⚠️ Skipped bundle at index {idx} (missing name)."))
                continue

            bundle, created = Bundle.objects.update_or_create(
                group=group,
                name=name,
                defaults={
                    "description": description,
                    "base_price": base_price,
                    "discounted_price": discounted_price,
                    "sort_order": idx,
                    "is_active": True,
                },
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"✅ Added: {bundle.name}"))
            else:
                self.stdout.write(self.style.NOTICE(f"🔁 Updated: {bundle.name}"))

        self.stdout.write(self.style.SUCCESS("🎉 Import completed successfully!"))
