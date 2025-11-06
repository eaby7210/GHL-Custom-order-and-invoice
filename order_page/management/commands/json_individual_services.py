import json
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from order_page.models import (
    IndividualService,
    ServiceForm,
    FormItem,
    OptionGroup,
    OptionItem,
    Submenu,
    SubmenuItem,
    SubmenuPriceChange,
    ModalOption,
    Disclosure,
)

class Command(BaseCommand):
    help = "Import services, forms, and options hierarchy from a JSON file"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to the JSON file")

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = options["file_path"]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                services_data = json.load(f)
        except Exception as e:
            raise CommandError(f"Error reading file: {e}")

        self.stdout.write(self.style.MIGRATE_HEADING(f"📦 Importing from {file_path}"))

        for idx, service_data in enumerate(services_data, start=1):
            self.import_service(service_data, sort_order=idx)

        self.stdout.write(self.style.SUCCESS("✅ Import completed successfully."))

    # -----------------------------------------------------------------------
    # Helper functions
    # -----------------------------------------------------------------------

    def import_service(self, data, sort_order=0):
        """Creates or updates an IndividualService and all nested models."""
        service_id = data.get("id")

        service, _ = IndividualService.objects.update_or_create(
            service_id=service_id,
            defaults={
                "title": data.get("title"),
                "subtitle": data.get("subtitle"),
                "header": data.get("header"),
                "subheader_html": data.get("subheader"),
                "order_protection": data.get("order_protection", False),
                "order_protection_disabled": data.get("order_protection_disabled", False),
                "order_protection_type": data.get("order_protection_type"),
                "order_protection_value": data.get("order_protection_value") or 0,
                "sort_order": sort_order,
            },
        )

        # ----------------------------
        # FORM CREATION
        # ----------------------------
        form_data = data.get("form")
        if form_data:
            form = self.create_form(form_data)
            service.form_ref = form #type:ignore
            service.save()

        # ----------------------------
        # DISCLOSURES
        # ----------------------------
        for d in data.get("disclosure", []):
            Disclosure.objects.create(
                service=service,
                type=d.get("type", "info"),
                message=d.get("message"),
            )

        self.stdout.write(self.style.SUCCESS(f"→ Imported Service: {service.title}"))
        return service

    def create_form(self, form_data):
        """Creates the ServiceForm, its FormItems, Options, Submenus, and Modals."""
        form = ServiceForm.objects.create(
            title=form_data.get("title"),
            description=form_data.get("description"),
        )

        # ----------------------------
        # FORM ITEMS
        # ----------------------------
        for idx, item_data in enumerate(form_data.get("items", []), start=1):
            form_item = self.create_form_item(item_data, sort_order=idx)
            form.items.add(form_item)

        # ----------------------------
        # SUBMENUS
        # ----------------------------
        submenu_data = form_data.get("submenu")
        if submenu_data:
            submenu = self.create_submenu(submenu_data)
            form.submenus.add(submenu)

        # ----------------------------
        # MODAL OPTIONS
        # ----------------------------
        modal_data = form_data.get("modalOption", {})
        for idx, opt in enumerate(modal_data.get("form", []), start=1):
            modal_option = ModalOption.objects.create(
                each_item=modal_data.get("eachItem", False),
                label=opt.get("label"),
                field_name=opt.get("name"),
                field_type=opt.get("type", "text"),
                required=opt.get("required", False),
                sort_order=idx,
            )
            form.modal_options.add(modal_option)

        form.save()
        return form

    def create_form_item(self, item_data, sort_order=0):
        """Creates FormItem and its OptionGroup."""
        option_group = None

        options = item_data.get("options")
        if options:
            option_group = self.create_option_group(options)

        form_item = FormItem.objects.create(
            identifier=item_data.get("id"),
            title=item_data.get("title"),
            subtitle=item_data.get("subtitle"),
            price=item_data.get("price"),
            base_price=item_data.get("basePrice"),
            protection_invalid=item_data.get("protectionInvalid", False),
            option_group=option_group,
            sort_order=sort_order,
        )

        # ----------------------------
        # SUBMENU PRICE CHANGES
        # ----------------------------
        submenu_changes = item_data.get("submenuPriceChange", {})
        for key, change in submenu_changes.items():
            spc, _ = SubmenuPriceChange.objects.get_or_create(
                key=key,
                defaults={
                    "change_type": change.get("type", "add"),
                    "value": change.get("value"),
                },
            )
            # Attach via related submenu items if needed
            # (depending on your schema – currently kept independent)

        return form_item

    def create_option_group(self, options_data):
        """Creates OptionGroup and OptionItems."""
        group = OptionGroup.objects.create(
            type=options_data.get("type", "checkbox"),
            minimum_required=options_data.get("minimumRequired", 0),
        )

        for idx, opt in enumerate(options_data.get("items", []), start=1):
            option_item, _ = OptionItem.objects.get_or_create(
                identifier=opt.get("id"),
                defaults={
                    "label": opt.get("label"),
                    "value": opt.get("value", False),
                    "disabled": opt.get("disabled", False),
                    "price_change": opt.get("priceChange") or opt.get("priceAdd"),
                    "sort_order": idx,
                },
            )
            group.items.add(option_item)

        return group

    def create_submenu(self, submenu_data):
        """Creates Submenu and its SubmenuItems."""
        submenu = Submenu.objects.create(
            type=submenu_data.get("type", "mixed"),
            label=submenu_data.get("label", "Unnamed"),
        )

        for idx, item in enumerate(submenu_data.get("items", []), start=1):
            submenu_item = SubmenuItem.objects.create(
                identifier=item.get("id"),
                label=item.get("label"),
                type=item.get("type"),
                value=item.get("value"),
                min_value=item.get("min"),
                max_value=item.get("max"),
                sort_order=idx,
            )
            submenu.items.add(submenu_item)

        return submenu
