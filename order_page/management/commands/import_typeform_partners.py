import csv
import os
from django.core.management.base import BaseCommand
from order_page.models import TypeformField, TypeformPartnerMapping
from tolt.models import Partner

class Command(BaseCommand):
    help = 'Import Typeform Partner Mappings from CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Path to the CSV file')
        parser.add_argument('field_id', type=str, help='The Typeform Field ID')

    def handle(self, *args, **kwargs):
        csv_path = kwargs['csv_path']
        field_id = kwargs['field_id']

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f'CSV file not found: {csv_path}'))
            return

        try:
            field = TypeformField.objects.get(field_id=field_id)
        except TypeformField.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'TypeformField with ID {field_id} not found.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Processing CSV: {csv_path} for Field: {field.title} ({field_id})'))

        # Prepare for Batch Processing
        from order_page.services import TypeformService
        from order_page.models import TypeformForm
        import uuid
        
        service = TypeformService()
        
        # 1. Fetch current form definition ONCE
        self.stdout.write(f"Fetching form {field.form.form_id} definition...")
        try:
            form_data = service.get_form(field.form.form_id)
            if "error" in form_data:
                 self.stdout.write(self.style.ERROR(f"Failed to fetch form: {form_data['error']}"))
                 return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception fetching form: {e}"))
            return

        # Locate the field in the form definition
        target_field_data = None
        if "fields" in form_data:
            for f in form_data["fields"]:
                if f["id"] == field_id:
                    target_field_data = f
                    break
        
        if not target_field_data:
            self.stdout.write(self.style.ERROR(f"Field {field_id} not found in form definition."))
            return
            
        # Ensure properties and choices exist
        if "properties" not in target_field_data:
             target_field_data["properties"] = {}
        if "choices" not in target_field_data["properties"]:
             target_field_data["properties"]["choices"] = []
             
        choices_list = target_field_data["properties"]["choices"]

        count = 0
        updated_count = 0
        
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                # Strip potential whitespace from keys
                clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
                
                choice_label = clean_row.get("Partner's Name")
                email = clean_row.get("Partner Email ID Tolt")
                
                if not choice_label or not email:
                    continue

                # Find Partner
                partner = Partner.objects.filter(email=email).first()
                if not partner:
                    self.stdout.write(self.style.WARNING(f'Partner not found for email: {email}'))
                    # Continue to create/update choice in Typeform/DB even if partner link fails?
                    # Original logic passed. We'll stick to that.
                
                # Check for existing mapping key (form, field, choice_label)
                # We need a ref.
                
                # 1. Check if mapping exists locally
                mapping = TypeformPartnerMapping.objects.filter(
                    form=field.form, field=field, choice_label=choice_label
                ).first()
                
                choice_ref = None
                if mapping and mapping.choice_ref:
                    choice_ref = mapping.choice_ref
                else:
                    # 2. Check if choice exists in API choices by label
                    existing_api_choice = next((c for c in choices_list if c.get("label") == choice_label), None)
                    if existing_api_choice:
                        choice_ref = existing_api_choice.get("ref")
                
                # 3. If still no ref, generate new one
                if not choice_ref:
                     choice_ref = str(uuid.uuid4())
                
                # --- Update Local DB (Skip Sync) ---
                mapping, created = TypeformPartnerMapping.objects.update_or_create(
                    form=field.form,
                    field=field,
                    choice_label=choice_label,
                    defaults={
                        'choice_ref': choice_ref,
                        'partner': partner
                    }
                )
                
                # Ensure we skip sync trigger on save (update_or_create calls save)
                # Wait, update_or_create triggers save immediately. We can't pass _skip_typeform_sync easily via defaults unless we override init?
                # Actually, iterate:
                # To be safe and efficient: 
                # Use get_or_create then manually save with flag if needed.
                
                # Let's redo the DB part properly to avoid sync:
                # But we just did update_or_create. That triggers save() -> triggers sync logic!
                # We MUST manually handle this to inject the flag.
                
                pass # Logic continues below to fix this section
                
        # ... (Re-implementing the loop body properly for replacement) ...
        # Since I'm replacing the whole handle method, I will write the clean loop.

    # Correct implementations
    def handle(self, *args, **kwargs):
        csv_path = kwargs['csv_path']
        field_id = kwargs['field_id']

        # Imports
        from order_page.services import TypeformService
        from order_page.models import TypeformForm
        import uuid

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f'CSV file not found: {csv_path}'))
            return

        try:
            field = TypeformField.objects.get(field_id=field_id)
        except TypeformField.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'TypeformField with ID {field_id} not found.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Processing CSV: {csv_path} for Field: {field.title} ({field_id})'))
        
        service = TypeformService()
        
        # 1. Fetch Form
        self.stdout.write(f"Fetching form {field.form.form_id} definition...")
        try:
            form_data = service.get_form(field.form.form_id)
            if "error" in form_data:
                 self.stdout.write(self.style.ERROR(f"Failed to fetch form: {form_data['error']}"))
                 return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception fetching form: {e}"))
            return

        target_field_data = None
        if "fields" in form_data:
            for f in form_data["fields"]:
                if f["id"] == field_id:
                    target_field_data = f
                    break
        
        if not target_field_data:
            self.stdout.write(self.style.ERROR(f"Field {field_id} not found in form definition."))
            return
            
        if "properties" not in target_field_data: target_field_data["properties"] = {}
        if "choices" not in target_field_data["properties"]: target_field_data["properties"]["choices"] = []
        choices_list = target_field_data["properties"]["choices"]

        count = 0
        updated_count = 0
        
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
                choice_label = clean_row.get("Partner's Name")
                email = clean_row.get("Partner Email ID Tolt")
                
                if not choice_label or not email:
                    continue

                partner = Partner.objects.filter(email=email).first()
                if not partner:
                    self.stdout.write(self.style.WARNING(f'Partner not found for email: {email}'))

                # Resolve Ref
                choice_ref = None
                
                # Check Local
                mapping = TypeformPartnerMapping.objects.filter(
                    form=field.form, field=field, choice_label=choice_label
                ).first()
                if mapping and mapping.choice_ref:
                    choice_ref = mapping.choice_ref
                
                # Check API List (if local didn't have ref)
                if not choice_ref:
                    existing_api_choice = next((c for c in choices_list if c.get("label") == choice_label), None)
                    if existing_api_choice:
                        choice_ref = existing_api_choice.get("ref")
                
                # Generate new if missing
                if not choice_ref:
                     choice_ref = str(uuid.uuid4())
                
                # Update DB (Skipping Sync)
                if mapping:
                    mapping.choice_ref = choice_ref
                    mapping.partner = partner
                    mapping._skip_typeform_sync = True
                    mapping.save()
                    updated_count += 1
                else:
                    mapping = TypeformPartnerMapping(
                        form=field.form,
                        field=field,
                        choice_label=choice_label,
                        choice_ref=choice_ref,
                        partner=partner
                    )
                    mapping._skip_typeform_sync = True
                    mapping.save()
                    count += 1
                
                # Update Payload Choice List
                # Check if exists in list to update, else append
                choice_in_payload = next((c for c in choices_list if c.get("ref") == choice_ref), None)
                if choice_in_payload:
                    choice_in_payload["label"] = choice_label # Update label just in case
                else:
                    choices_list.append({"ref": choice_ref, "label": choice_label})
        
        # 3. Update Form via API (Single Call)
        self.stdout.write(f"Sending Batch Update to Typeform ({len(choices_list)} choices)...")
        target_field_data["properties"]["choices"] = choices_list
        
        try:
            updated_form = service.update_form(field.form.form_id, form_data)
            if "error" in updated_form:
                 self.stdout.write(self.style.ERROR(f"Failed to update form: {updated_form['error']}"))
                 return
            
            # 4. Sync Local DB from Response
            self.stdout.write("Syncing local DB from response...")
            TypeformForm.create_or_update_from_api(updated_form)
            
            self.stdout.write(self.style.SUCCESS(f'Import Complete. Processed {count + updated_count} items. Total Choices: {len(choices_list)}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error updating Typeform: {e}"))
