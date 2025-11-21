import json
from decimal import Decimal, InvalidOperation
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
    help = "Load service configuration JSON and create database objects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Path to JSON file",
        )
        parser.add_argument(
            "--dry",
            action="store_true",
            help="Dry run — only print what would happen, no DB changes.",
        )

    def dry_print(self, msg):
        """Helper print that highlights dry-run output."""
        self.stdout.write(self.style.WARNING(f"[DRY] {msg}"))

    def info(self, msg):
        self.stdout.write(self.style.SUCCESS(msg))

    # ----------------------
    # Main handler
    # ----------------------
    def handle(self, *args, **options):
        path = options["path"]
        dry = options["dry"]

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if dry:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE ENABLED ==="))
            self.stdout.write(self.style.WARNING("NO changes will be committed.\n"))

        self.info(f"Loading services from {path} ...")

        # Wrap in a single atomic block; use set_rollback(True) for dry runs
        with transaction.atomic():
            for service_data in data:
                self.import_service(service_data, dry=dry)

            if dry:
                # mark transaction to rollback and exit
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("\n(DRY RUN) Rolling back changes..."))
                return

        self.info("✔ All services imported successfully!")

    # ----------------------
    # Import a service
    # ----------------------
    def import_service(self, s, dry=False):
        sid = s.get("id")
        title = s.get("title", sid or "untitled")
        if dry:
            self.dry_print(f"Service: {sid} → {title}")

        service, _ = IndividualService.objects.update_or_create(
            service_id=sid,
            defaults=dict(
                title=title,
                subtitle=s.get("subtitle"),
                header=s.get("header"),
                subheader_html=s.get("subheader"),
                order_protection=s.get("order_protection", False),
                order_protection_disabled=s.get("order_protection_disabled", False),
                order_protection_type=s.get("order_protection_type"),
                order_protection_value=s.get("order_protection_value"),
            ),
        )

        form_data = s.get("form")
        if form_data:
            if dry:
                self.dry_print(f"  Form: {form_data.get('title')}")

            form, _ = ServiceForm.objects.update_or_create(
                title=form_data.get("title"),
                defaults={"description": form_data.get("description")},
            )
            service.form_ref = form
            service.save()

            # pass service id for submenu unique naming
            self.import_form_items(form, form_data.get("items", []), service, dry=dry)
            self.import_form_options(form, form_data.get("options", {}), service, dry=dry)
            self.import_form_submenu(form, form_data.get("submenu"), service, dry=dry)
            self.import_form_modal_options(form, form_data.get("modalOption"), dry=dry)

        # disclosures (if any)
        for d in s.get("disclosure", []):
            if dry:
                self.dry_print(f"  Disclosure: {d.get('message','')[:60]}...")
            Disclosure.objects.update_or_create(
                service=service,
                message=d["message"],
                defaults={"type": d.get("type", "info"), "sort_order": d.get("sort_order", 0)},
            )

    # ----------------------
    # Import form items
    # ----------------------
    def import_form_items(self, form, items, service, dry=False):
        for idx, item in enumerate(items or []):
            if dry:
                self.dry_print(f"    FormItem: {item.get('id')}")

            fitem, _ = FormItem.objects.update_or_create(
                identifier=item.get("id"),
                defaults=dict(
                    title=item.get("title"),
                    subtitle=item.get("subtitle"),
                    price=item.get("price"),
                    base_price=item.get("basePrice"),
                    protection_invalid=item.get("protectionInvalid", False),
                    sort_order=idx,
                ),
            )

            form.items.add(fitem)

            # options attached to this form item
            if item.get("options"):
                self.import_option_group(fitem, item["options"], dry=dry)

            # submenu price changes (map keys to submenu items later)
            if item.get("submenuPriceChange"):
                self.import_price_changes(fitem, item["submenuPriceChange"], dry=dry)

    # ----------------------
    # Import option group for a FormItem (OneToOne)
    # ----------------------
    def import_option_group(self, form_item, group_data, dry=False):
        """
        Creates or updates an OptionGroup and assigns it to form_item.option_group.
        """
        if dry:
            self.dry_print(f"      OptionGroup for FormItem: {form_item.identifier}")

        # If FormItem already has an OptionGroup, update it; otherwise create new
        group = getattr(form_item, "option_group", None)
        if group:
            # update fields on existing group
            group.type = group_data.get("type", group.type)
            group.minimum_required = group_data.get("minimumRequired", group.minimum_required)
            if not dry:
                group.save()
        else:
            group = OptionGroup.objects.create(
                type=group_data.get("type", "checkbox"),
                minimum_required=group_data.get("minimumRequired", 0),
            )
            # bind to the FormItem one-to-one
            form_item.option_group = group
            if not dry:
                form_item.save()

        # reset items for this group
        if not dry:
            group.items.clear()

        for idx, opt in enumerate(group_data.get("items", []) or []):
            if dry:
                self.dry_print(f"        OptionItem: {opt.get('id')}")

            # determine price_type and price_value safely
            if "priceAdd" in opt and opt["priceAdd"] is not None:
                price_type = "priceAdd"
                price_value = opt["priceAdd"]
            elif "priceChange" in opt and opt["priceChange"] is not None:
                price_type = "priceChange"
                price_value = opt["priceChange"]
            else:
                price_type = "priceAdd"
                price_value = None

            # convert numeric price_value to Decimal when present
            price_value_dec = None
            if price_value is not None:
                try:
                    price_value_dec = Decimal(str(price_value))
                except (InvalidOperation, TypeError, ValueError):
                    price_value_dec = None

            obj, _ = OptionItem.objects.update_or_create(
                identifier=opt.get("id"),
                defaults=dict(
                    label=opt.get("label"),
                    value=opt.get("value", False),
                    disabled=opt.get("disabled", False),
                    price_type=price_type,
                    price_value=price_value_dec,
                    sort_order=idx,
                ),
            )

            if not dry:
                group.items.add(obj)

        return group

    # ----------------------
    # Service-level options — create group but DO NOT try to attach to form.items
    # (your models do not have a place to attach an OptionGroup to ServiceForm directly).
    # We create the OptionGroup and log it. You can adapt if you want it linked somewhere.
    # ----------------------
    def import_form_options(self, form, options, service, dry=False):
        if not options or options.get("type") == "none":
            return

        if dry:
            self.dry_print("    Service-level OptionGroup (created but not attached to form.items)")

        # create a named OptionGroup so it is unique per service
        group_name = f"{service.service_id}-form-options"
        group = OptionGroup.objects.create(
            type=options.get("type", "checkbox"),
            minimum_required=options.get("minimumRequired", 0),
        )

        for idx, opt in enumerate(options.get("items", []) or []):
            if dry:
                self.dry_print(f"      OptionItem: {opt.get('id')}")
            price_type = "priceAdd"
            price_value = opt.get("priceAdd")
            price_value_dec = None
            if price_value is not None:
                try:
                    price_value_dec = Decimal(str(price_value))
                except (InvalidOperation, TypeError, ValueError):
                    price_value_dec = None

            obj, _ = OptionItem.objects.update_or_create(
                identifier=opt.get("id"),
                defaults=dict(
                    label=opt.get("label"),
                    value=opt.get("value", False),
                    disabled=opt.get("disabled", False),
                    price_type=price_type,
                    price_value=price_value_dec,
                    sort_order=idx,
                ),
            )
            if not dry:
                group.items.add(obj)

        # NOTE: we intentionally do NOT add `group` into `form.items` (invalid)
        # If you want to persist a link to the form, add a new field on ServiceForm or store the group id elsewhere.

    # ----------------------
    # Submenu import
    # ----------------------
    def import_form_submenu(self, form, submenu_data, service, dry=False):
        """
        Create a unique Submenu per service+type to avoid collisions between services.
        """
        if not submenu_data:
            return

        if dry:
            self.dry_print(f"    Submenu: {submenu_data.get('type')}")

        # create unique name combining service_id and submenu type
        submenu_name = f"{service.service_id}::{submenu_data.get('type')}"
        submenu, created = Submenu.objects.get_or_create(
            name=submenu_name,
            defaults={"type": submenu_data.get("type"), "sort_order": 0},
        )

        if not dry:
            # ensure it's fresh for this import: clear existing items then re-add
            submenu.items.clear()

        for idx, item in enumerate(submenu_data.get("items", []) or []):
            if dry:
                self.dry_print(f"      SubmenuItem: {item.get('id')}")
            sub, _ = SubmenuItem.objects.update_or_create(
                identifier=item.get("id"),
                defaults=dict(
                    label=item.get("label"),
                    type=item.get("type"),
                    value=item.get("value"),
                    form_name=item.get("name"),
                    min_value=item.get("min"),
                    max_value=item.get("max"),
                    sort_order=idx,
                ),
            )
            if not dry:
                submenu.items.add(sub)

        if not dry:
            form.submenus.add(submenu)

    # ----------------------
    # Submenu price changes
    # ----------------------
    def import_price_changes(self, form_item, changes, dry=False):
        for key, cfg in (changes or {}).items():
            if dry:
                self.dry_print(f"      PriceChange: {key}")

            submenu_item = SubmenuItem.objects.filter(identifier=key).first()
            if submenu_item:
                SubmenuPriceChange.objects.update_or_create(
                    form_item=form_item,
                    submenu_item=submenu_item,
                    defaults=dict(
                        change_type=cfg.get("type"),
                        value=cfg.get("value"),
                    ),
                )

    # ----------------------
    # Modal Options
    # ----------------------
    def import_form_modal_options(self, form, modal_data, dry=False):
        if not modal_data:
            return

        for idx, field in enumerate(modal_data.get("form", []) or []):
            if dry:
                self.dry_print(f"    ModalOption: {field.get('label')}")

            modal, _ = ModalOption.objects.update_or_create(
                label=field.get("label"),
                defaults=dict(
                    field_name=field.get("name"),
                    field_type=field.get("type", "text"),
                    required=field.get("required", False),
                    sort_order=idx,
                    each_item=modal_data.get("eachItem", False),
                ),
            )

            if not dry:
                form.modal_options.add(modal)

            # link valid_for_items if provided in JSON (valid_item_index)
            for valid_id in field.get("valid_item_index", []) or []:
                fitem = FormItem.objects.filter(identifier=valid_id).first()
                if fitem and not dry:
                    modal.valid_for_items.add(fitem)
          
            