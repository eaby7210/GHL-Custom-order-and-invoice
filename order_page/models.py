from django.db import models
from django.utils.html import strip_tags
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import JSONField  
from django.utils import timezone
from django.db import transaction
import uuid, json
from stripe_payment.models import NotaryClientCompany 



class TermsOfConditions(models.Model):
    version_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Enter basic HTML content for terms of conditions (no JS).")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
            db_table = 'terms_of_conditions'



    def clean(self):
  
        disallowed_tags = ["script", "iframe", "object", "embed"]
        for tag in disallowed_tags:
            if f"<{tag}" in self.body.lower():
                raise ValidationError(f"Tag <{tag}> is not allowed.")
        super().clean()

    def save(self, *args, **kwargs):
        # Check if this is an update (pk exists)
        if self.pk:
            # Clear all users who have signed this term
            self.users.clear()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
    

class TypeformForm(models.Model):
    """Unique Typeform form definition"""
    form_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    settings = models.JSONField(default=dict, blank=True)
    endings = models.JSONField(default=list, blank=True)
    
    # Enhanced fields
    workspace = models.JSONField(default=dict, blank=True)
    theme = models.JSONField(default=dict, blank=True)
    cui_settings = models.JSONField(default=dict, blank=True)
    variables = models.JSONField(default=dict, blank=True)
    hidden = models.JSONField(default=list, blank=True)
    

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title or self.form_id

    @staticmethod
    @transaction.atomic
    def create_or_update_from_api(data: dict):
        """
        Creates or updates a TypeformForm and its related models from the API response data.
        """
        # Update or create Form
        form_obj, _ = TypeformForm.objects.update_or_create(
            form_id=data.get("id"),
            defaults={
                "title": data.get("title", ""),
                "settings": data.get("settings", {}),
                "endings": data.get("endings", []),
                "workspace": data.get("workspace", {}),
                "theme": data.get("theme", {}),
                "cui_settings": data.get("cui_settings", {}),
                "variables": data.get("variables", {}),
                "hidden": data.get("hidden", []),
            },
        )
        
        # --- Sync Welcome Screens ---
        current_welcome_ids = []
        for ws in data.get("welcome_screens", []):
            w_obj, _ = TypeformWelcomeScreen.objects.update_or_create(
                form=form_obj,
                ref=ws.get("ref"),
                defaults={
                    "title": ws.get("title"),
                    "properties": ws.get("properties", {}),
                    "attachment": ws.get("attachment", {}),
                    "layout": ws.get("layout", {}),
                }
            )
            current_welcome_ids.append(w_obj.id)
        # Verify: Remove old ones? For now, let's keep it simple and additive/update-only to avoid data loss if API response is partial? 
        # API response usually full, so deletion of orphans is correct for strict sync.
        # form_obj.welcome_screens.exclude(id__in=current_welcome_ids).delete()

        # --- Sync Thank You Screens ---
        current_thankyou_ids = []
        for ty in data.get("thankyou_screens", []):
            ty_obj, _ = TypeformThankYouScreen.objects.update_or_create(
                form=form_obj,
                ref=ty.get("ref"),
                defaults={
                    "title": ty.get("title"),
                    "type": ty.get("type"),
                    "properties": ty.get("properties", {}),
                    "attachment": ty.get("attachment", {}),
                    "layout": ty.get("layout", {}),
                }
            )
            current_thankyou_ids.append(ty_obj.id)

        # --- Sync Logic ---
        current_logic_ids = []
        for l in data.get("logic", []):
            l_obj, _ = TypeformLogic.objects.update_or_create(
                form=form_obj,
                ref=l.get("ref"),
                defaults={
                    "type": l.get("type"),
                    "actions": l.get("actions", []),
                }
            )
            current_logic_ids.append(l_obj.id)

        # --- Sync Fields ---
        fields_data = data.get("fields", [])
        current_field_ids = []
        for f in fields_data:
            field_obj, _ = TypeformField.objects.update_or_create(
                form=form_obj,
                field_id=f.get("id"),
                defaults={
                    "ref": f.get("ref"),
                    "field_type": f.get("type"),
                    "title": f.get("title"),
                    "properties": f.get("properties", {}),
                    "choices": f.get("properties", {}).get("choices", []), 
                },
            )
            current_field_ids.append(field_obj.id)

            # --- Sync Partner Mappings (Choices) ---
            # Automatically populate TypeformPartnerMapping for dropdown choices
            if f.get("type") == "dropdown":
                choices = f.get("properties", {}).get("choices", [])
                print(f"[DEBUG sync_mappings] Choices: {json.dumps(choices, indent=2)}")
                current_choice_refs = []
                for choice in choices:
                    choice_ref = choice.get("ref")
                    choice_label = choice.get("label")
                    
                    if choice_ref:
                        current_choice_refs.append(choice_ref) # Add to list of active refs
                        
                        # Use manual lookup/create to avoid immediate save() trigger from get_or_create
                        # and to allow setting the recursion guard flag.
                        mapping_obj = TypeformPartnerMapping.objects.filter(
                            form=form_obj,
                            field=field_obj,
                            choice_ref=choice_ref
                        ).first()

                        if not mapping_obj:
                            # Try to find by label if ref lookup failed (for locally created choices without ref)
                            from django.db.models import Q
                            mapping_obj = TypeformPartnerMapping.objects.filter(
                                form=form_obj,
                                field=field_obj,
                                choice_label=choice_label
                            ).filter(Q(choice_ref__isnull=True) | Q(choice_ref='')).first()

                            if mapping_obj:
                                # Found match by label! Update the ref.
                                print(f"[DEBUG] Found existing mapping by label '{choice_label}', updating ref to {choice_ref}")
                                mapping_obj.choice_ref = choice_ref
                                mapping_obj._skip_typeform_sync = True
                                mapping_obj.save()
                            else:
                                mapping_obj = TypeformPartnerMapping(
                                    form=form_obj,
                                    field=field_obj,
                                    choice_ref=choice_ref,
                                    choice_label=choice_label
                                )
                                mapping_obj._skip_typeform_sync = True
                                mapping_obj.save()
                        
                        else:
                            # Update label if changed
                            if mapping_obj.choice_label != choice_label:
                                mapping_obj.choice_label = choice_label
                                mapping_obj._skip_typeform_sync = True
                                mapping_obj.save()
                        

                
                # Delete mappings that are NOT in the current choice refs list
                # This ensures local DB stays in sync with Typeform definition
                if current_choice_refs:
                    stale_mappings = TypeformPartnerMapping.objects.filter(
                        form=form_obj, 
                        field=field_obj
                    ).exclude(choice_ref__in=current_choice_refs)
                    
                    if stale_mappings.exists():
                         print(f"[DEBUG] Deleting {stale_mappings.count()} stale partner mappings for field {field_obj.field_id}")
                         # Set flag on potential delete? delete() signal might trigger sync?
                         # The delete() method on model is overridden to sync to Typeform.
                         # But here we are syncing FROM Typeform.
                         # If we delete locally because it's gone from Typeform, we DON'T want to trigger a sync back to Typeform (it's already gone).
                         # We should use queryset delete or set flag? Queryset delete doesn't call model.delete() method, so it bypasses our override!
                         # Perfect.
                         stale_mappings.delete()
            
        return form_obj


class TypeformWelcomeScreen(models.Model):
    form = models.ForeignKey(TypeformForm, related_name="welcome_screens", on_delete=models.CASCADE)
    ref = models.CharField(max_length=100, null=True, blank=True)
    title = models.TextField(null=True, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    attachment = models.JSONField(default=dict, blank=True)
    layout = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Welcome: {self.title[:30] if self.title else self.ref}"


class TypeformThankYouScreen(models.Model):
    form = models.ForeignKey(TypeformForm, related_name="thankyou_screens_models", on_delete=models.CASCADE)
    ref = models.CharField(max_length=100, null=True, blank=True)
    title = models.TextField(null=True, blank=True)
    type = models.CharField(max_length=50, null=True, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    attachment = models.JSONField(default=dict, blank=True)
    layout = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"ThankYou: {self.title[:30] if self.title else self.ref}"


class TypeformLogic(models.Model):
    form = models.ForeignKey(TypeformForm, related_name="logics", on_delete=models.CASCADE)
    ref = models.CharField(max_length=100, null=True, blank=True)
    type = models.CharField(max_length=50, null=True, blank=True)
    actions = models.JSONField(default=list, blank=True)
    
    def __str__(self):
        return f"Logic: {self.ref} ({self.type})"


class TypeformField(models.Model):
    """Field/question definition (static per form)"""
    form = models.ForeignKey(TypeformForm, related_name="fields", on_delete=models.CASCADE)
    field_id = models.CharField(max_length=50)
    ref = models.CharField(max_length=100, null=True, blank=True)
    field_type = models.CharField(max_length=50)
    title = models.TextField()
    properties = models.JSONField(default=dict, blank=True)
    choices = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ("form", "field_id")
        indexes = [
            models.Index(fields=["field_id"]),
            models.Index(fields=["ref"]),
        ]

    def __str__(self):
        return f"{self.title[:40]} ({self.field_type})"


class TypeformResponse(models.Model):
    """Each webhook submission"""
    event_id = models.CharField(max_length=100, unique=True)
    form = models.ForeignKey(TypeformForm, related_name="responses", on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    landed_at = models.DateTimeField()
    submitted_at = models.DateTimeField()
    hidden = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["form"]),
            models.Index(fields=["submitted_at"]),
        ]

    def get_answer_by_title(self, title: str):
        """
        Given a field title (case-insensitive), return its answer value.
        Returns None if no matching field or answer exists.
        """
        try:
            # Case-insensitive lookup on field title
            answer = (
                self.answers.select_related("field").filter(field__title__iexact=title).first())#type:ignore
            if not answer:
                return None

            # Return the best available scalar value
            if answer.value_text:
                return answer.value_text
            if answer.value_number is not None:
                return answer.value_number
            if answer.value_bool is not None:
                return answer.value_bool
            if answer.value_json:
                return answer.value_json
            return None
        except Exception as e:
            # Optional: handle edge cases safely
            print(f" get_answer_by_title({title}) failed:", e)
            return None

    def resolve_typeform_partner_mapping(self):
        """
        First TypeformPartnerMapping matching a dropdown choice answer in this
        response (same ref/label + field lookup as ghl_update_contact).
        """
        qs = self.answers.select_related("field").filter(
            answer_type="choice",
            field__field_type="dropdown",
        )
        for answer in qs:
            if not answer.value_json or not isinstance(answer.value_json, dict):
                continue
            choice_data = answer.value_json
            choice_ref = choice_data.get("ref")
            choice_label = choice_data.get("label")
            if not choice_ref and not choice_label:
                continue
            mapping = None
            if choice_ref:
                mapping = TypeformPartnerMapping.objects.filter(
                    field=answer.field,
                    choice_ref=choice_ref,
                ).first()
            if not mapping and choice_label:
                mapping = TypeformPartnerMapping.objects.filter(
                    field=answer.field,
                    choice_label=choice_label,
                ).first()
            if mapping:
                return mapping
        return None

    def resolve_partner_from_hidden_tolt_link(self):
        """
        When Typeform ``hidden`` includes e.g. ``{"ref": "ispeedtolead"}``, match
        that string against ``tolt.Link.value`` (exact, case-insensitive, then
        substring) and return the related ``Partner`` if one exists.
        """
        from tolt.models import Link

        hidden = self.hidden
        if not hidden or not isinstance(hidden, dict):
            return None
        token = hidden.get("ref")
        if token is None:
            return None
        token = str(token).strip()
        if not token:
            return None

        qs = (
            Link.objects.filter(partner__isnull=False)
            .exclude(value__isnull=True)
            .exclude(value="")
            .select_related("partner")
            .order_by("-created_at")
        )
        link = (
            qs.filter(value=token).first()
            or qs.filter(value__iexact=token).first()
            or qs.filter(value__icontains=token).first()
        )
        return link.partner if link else None

    def __str__(self):
        return f"Response {self.token} ({self.form.form_id})"


class TypeformAnswer(models.Model):
    """Link each response to each field with scalar value"""
    response = models.ForeignKey(TypeformResponse, related_name="answers", on_delete=models.CASCADE)
    field = models.ForeignKey(TypeformField, related_name="answers", on_delete=models.CASCADE)
    answer_type = models.CharField(max_length=50)
    value_text = models.TextField(null=True, blank=True)
    value_number = models.FloatField(null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    value_json = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("response", "field")
        indexes = [
            models.Index(fields=["field"]),
            models.Index(fields=["response"]),
        ]

    def __str__(self):
        return f"{self.field.title[:30]} → {self.get_value_display()}"

    def get_value_display(self):
        if self.value_text:
            return self.value_text
        if self.value_number is not None:
            return str(self.value_number)
        if self.value_bool is not None:
            return str(self.value_bool)
        return str(self.value_json)



class TypeformPartnerMapping(models.Model):
    """Maps a specific choice in a Typeform dropdown field to a Tolt Partner"""
    form = models.ForeignKey(TypeformForm, on_delete=models.CASCADE, related_name="partner_mappings")
    field = models.ForeignKey(TypeformField, on_delete=models.CASCADE, related_name="partner_mappings")
    
    # Store the choice reference from Typeform (stable ID)
    choice_ref = models.CharField(max_length=100, help_text="The 'ref' of the choice in Typeform definition", null=True, blank=True)
    choice_label = models.CharField(max_length=255, help_text="The readable label of the choice")
    
    partner = models.ForeignKey("tolt.Partner", on_delete=models.CASCADE, related_name="typeform_mappings", null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("form", "field", "choice_ref")
        verbose_name = "Typeform Partner Mapping"
        verbose_name_plural = "Typeform Partner Mappings"

    def __str__(self):
        return f"{self.choice_label} -> {self.partner}"

    def save(self, *args, **kwargs):
        # Prevent infinite recursion during sync
        if getattr(self, "_skip_typeform_sync", False):
            super().save(*args, **kwargs)
            return

        # Save to DB first so that the sync process sees the updated values!
        super().save(*args, **kwargs)

        print(f"[DEBUG] TypeformPartnerMapping.save() called for {self.choice_label}")
        # Perform API update if specific conditions met
        if self.field and self.field.field_type == 'dropdown':
            print(f"[DEBUG] Saving TypeformPartnerMapping for dropdown field {self.field.field_id}")
            from .services import TypeformService
            service = TypeformService()
            
            try:
                # 1. Fetch current form definition
                print(f"[DEBUG] Fetching form {self.form.form_id} from Typeform...")
                form_data = service.get_form(self.form.form_id)
                
                # Check for errors in fetch
                if "error" in form_data:
                    raise Exception(f"Failed to fetch form: {form_data['error']}")
                
                # 2. Find and modify the field choices
                found_field = False
                if "fields" in form_data:
                    for field_item in form_data["fields"]:
                        if field_item["id"] == self.field.field_id:
                            found_field = True
                            props = field_item.get("properties", {})
                            choices = props.get("choices", [])
                            
                            # Check if choice exists by ref or label
                            existing_choice = None
                            if self.choice_ref:
                                existing_choice = next(
                                    (c for c in choices if str(c.get("ref")) == str(self.choice_ref)), 
                                    None
                                )
                            else:
                                existing_choice = next(
                                    (c for c in choices if c.get("label") == self.choice_label), 
                                    None
                                )
                            
                            if existing_choice:
                                print(f"[DEBUG] Updating existing choice with label '{self.choice_label}'")
                                # Update label
                                existing_choice["label"] = self.choice_label
                                if self.choice_ref:
                                    existing_choice["ref"] = self.choice_ref
                            else:
                                print(f"[DEBUG] Adding new choice -> '{self.choice_label}'")
                                # Add new choice
                                import uuid
                                new_choice = {"label": self.choice_label}
                                new_choice["ref"] = self.choice_ref if self.choice_ref else str(uuid.uuid4())
                                choices.append(new_choice)
                            
                            # Ensure choices that aren't mapped to a partner are moved to the end
                            mapped_refs = set(TypeformPartnerMapping.objects.filter(
                                form=self.form,
                                field=self.field,
                                partner__isnull=False
                            ).values_list('choice_ref', flat=True))
                            
                            # Stable sort: mapped (0) comes before unmapped (1)
                            choices.sort(key=lambda c: 0 if str(c.get("ref")) in mapped_refs else 1)
                            
                            props["choices"] = choices
                            field_item["properties"] = props
                            break
                
                if found_field:
                    # 3. PUT the updated form
                    print(f"[DEBUG] Sending PUT request to update form {self.form.form_id}...")
                    print(f"Form data: {json.dumps(form_data["fields"], indent=2)}")
                    updated_form = service.update_form(self.form.form_id, form_data)
                    
                    if "error" in updated_form:
                         raise Exception(f"Failed to update form: {updated_form['error']}")
                    
                    print(f"[DEBUG] Form updated successfully. Syncing local DB...")
                    # 4. Sync local DB from response to ensure consistency
                    # This updates TypeformField choices locally as well
                    TypeformForm.create_or_update_from_api(updated_form)
                else:
                    print(f"[DEBUG] Field {self.field.field_id} not found in form definition.")

            except Exception as e:
                # Log error or re-raise? 
                # User said "so that is updated to typefrom as well". 
                # Failing here is safer than silently ignoring and having inconsistency.
                print(f"[DEBUG] Error syncing to Typeform: {str(e)}")
                raise Exception(f"Error syncing to Typeform: {str(e)}")

    def delete(self, *args, **kwargs):
        print(f"[DEBUG] TypeformPartnerMapping.delete() called for {self.choice_label}")
        if self.field and self.field.field_type == 'dropdown':
            try:
                from .services import TypeformService
                service = TypeformService()
                
                # 1. Fetch form
                print(f"[DEBUG] Fetching form {self.form.form_id} for deletion...")
                form_data = service.get_form(self.form.form_id)
                if "error" in form_data:
                    raise Exception(f"Failed to fetch form: {form_data['error']}")
                
                # 2. Find field and remove choice
                found_field = False
                choice_removed = False
                
                if "fields" in form_data:
                    for field_item in form_data["fields"]:
                        if field_item["id"] == self.field.field_id:
                            found_field = True
                            props = field_item.get("properties", {})
                            choices = props.get("choices", [])
                            
                            # Filter out the choice to be deleted
                            original_count = len(choices)
                            new_choices = [
                                c for c in choices 
                                if str(c.get("ref")) != str(self.choice_ref)
                            ]
                            
                            if len(new_choices) < original_count:
                                print(f"[DEBUG] Removed choice {self.choice_ref} from payload")
                                props["choices"] = new_choices
                                field_item["properties"] = props
                                choice_removed = True
                            else:
                                print(f"[DEBUG] Choice {self.choice_ref} not found in Typeform definition, skipping removal.")
                            break
                            
                if found_field and choice_removed:
                    # 3. Update form
                    print(f"[DEBUG] Sending PUT request to update form...")
                    updated_form = service.update_form(self.form.form_id, form_data)
                    
                    if "error" in updated_form:
                        raise Exception(f"Failed to update form: {updated_form['error']}")
                    
                    print(f"[DEBUG] Form updated successfully after deletion.")
                    # 4. Sync local DB
                    TypeformForm.create_or_update_from_api(updated_form)
                    
            except Exception as e:
                # Decide if we want to block deletion or just log
                print(f"[ERROR] Failed to sync deletion to Typeform: {e}")
                raise Exception(f"Error syncing deletion to Typeform: {str(e)}")

        super().delete(*args, **kwargs)


class TypeformParser:
    """Helper class to parse and save Typeform webhook payloads"""

    @staticmethod
    @transaction.atomic
    def save_webhook(payload: dict):
        form_resp = payload.get("form_response", {})
        if not form_resp:
            raise ValueError("Invalid webhook: missing form_response")

        # -- Form
        form_def = form_resp.get("definition", {})
        form_obj, _ = TypeformForm.objects.update_or_create(
            form_id=form_def.get("id"),
            defaults={
                "title": form_def.get("title", ""),
                "settings": form_def.get("settings", {}),
                "endings": form_def.get("endings", []),
            },
        )

        # -- Fields (ensure all exist)
        for f in form_def.get("fields", []):
            TypeformField.objects.update_or_create(
                form=form_obj,
                field_id=f.get("id"),
                defaults={
                    "ref": f.get("ref"),
                    "field_type": f.get("type"),
                    "title": f.get("title"),
                    "properties": f.get("properties", {}),
                    "choices": f.get("choices", []),
                },
            )

        # -- Response
        resp_obj, _ = TypeformResponse.objects.update_or_create(
            token=form_resp.get("token"),
            defaults={
                "event_id": payload.get("event_id"),
                "form": form_obj,
                "landed_at": form_resp.get("landed_at"),
                "submitted_at": form_resp.get("submitted_at"),
                "hidden": form_resp.get("hidden", {}),
                "raw_payload": payload,
            },
        )

        # -- Answers
        for ans in form_resp.get("answers", []):
            field_id = ans["field"]["id"]
            field_obj = TypeformField.objects.filter(form=form_obj, field_id=field_id).first()
            if not field_obj:
                continue

            answer_type = ans.get("type")
            kwargs = {"answer_type": answer_type, "value_json": {}}

            # Map to scalar efficiently
            if "text" in ans:
                kwargs["value_text"] = ans["text"]
            elif "email" in ans:
                kwargs["value_text"] = ans["email"]
            elif "phone_number" in ans:
                kwargs["value_text"] = ans["phone_number"]
            elif "number" in ans:
                kwargs["value_number"] = ans["number"]
            elif "boolean" in ans:
                kwargs["value_bool"] = ans["boolean"]
            elif "choice" in ans:
                kwargs["value_json"] = ans["choice"]
            elif "choices" in ans:
                kwargs["value_json"] = ans["choices"]

            TypeformAnswer.objects.update_or_create(
                response=resp_obj,
                field=field_obj,
                defaults=kwargs,
            )

        return resp_obj




class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ServiceVariance(TimeStampedModel):
    """
    Represents a versioned configuration of services + bundles.
    Each variance may be:
    - The default (applies to all clients)
    - Or assigned to one or more NotaryClientCompany instances
    """
    class OrderProtectionType(models.TextChoices):
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"
    name = models.CharField(
        max_length=255,
        help_text="Version or variance name, e.g. 'Fall 2025 Edition', 'Company One Special'."
    )

    service_category = models.ForeignKey(
        "ServiceCategory",
        related_name="variances",
        on_delete=models.CASCADE,
        help_text="Associated service category this version applies to.",
        verbose_name="Individual service variance"
    )
    bundle_group = models.ManyToManyField(
        "BundleGroup",
        related_name="variances",
        help_text="Associated bundle group this version applies to."
    )
    bundle_order_protection_type = models.CharField(
        max_length=50,
        choices=OrderProtectionType.choices,
        blank=True,
        null=True,
        help_text="Type of order protection applied (percent or fixed)."
    )
    bundle_order_protection_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="The numeric value for order protection."
    )

    version_number = models.PositiveIntegerField(
        default=1,
        help_text="Numeric version number."
    )

    # 🔹 Determines if this is the system-wide default configuration
    is_default = models.BooleanField(
        default=False,
        help_text="If True, this variance is the default fallback for all clients."
    )

    # 🔹 Clients that this variance applies to (many-to-many, like permissions)
    clients = models.ManyToManyField(
        NotaryClientCompany,  # or the actual app/model where this lives
        related_name="service_variances",
        blank=True,
        help_text="Clients that use this custom variance instead of the default."
    )

    is_active = models.BooleanField(
        default=False,
        help_text="Mark this variance as currently active."
    )

    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("name", "version_number")

    def __str__(self):
        label = " (default)" if self.is_default else ""
        return f"{self.name} v{self.version_number}{label}"

    # ----------------------------------------------------------------
    # 🧠 Utility methods for easy access and querying
    # ----------------------------------------------------------------
    @classmethod
    def get_for_client(cls, client: "NotaryClientCompany"):
        """
        Retrieve the active variance for a given client.
        If no client-specific variance is assigned, return the default.
        """
        # Try client-specific first
        variance = (
            cls.objects.filter(clients=client, is_active=True)
            .select_related("service_category", "bundle_group")
            .first()
        )
        if variance:
            return variance

        # Fallback to default active variance
        return (
            cls.objects.filter(is_default=True, is_active=True)
            .select_related("service_category", "bundle_group")
            .first()
        )

    @classmethod
    def get_default(cls):
        """Return the active default variance."""
        return cls.objects.filter(is_default=True, is_active=True).first()

class BundleGroup(TimeStampedModel):
    """
    Represents a collection of bundles (e.g., 'Pre-built packages with built-in savings')
    """
    name = models.CharField(max_length=255)
    header = models.CharField(max_length=255)
    subheader = models.CharField(max_length=512, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name


class BundleOptionItem(TimeStampedModel):
    """
    Represents a selectable option available under bundle option groups.
    Example: add-ons like 'Expedited Delivery' or 'Premium Support'.
    """
    FIELD_TYPES = [
        ("text", "Text"),
        # ("textarea", "Textarea"),
        ("number", "Number"),
        # ("email", "Email"),
        ("radio", "Radio"),
        # ("select", "Select"),
        ("checkbox", "Checkbox"),

    ]
    identifier = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=50, choices=FIELD_TYPES,blank=True,
        null=True,)

    name = models.CharField(max_length=255,blank=True,
        null=True,)
    value = models.BooleanField(default=False)
    text_val = models.CharField(max_length=255, null=True, blank=True)
    num_val = models.PositiveIntegerField(null=True, blank=True)
    disabled = models.BooleanField(default=False)
    price_change = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Additional price to add when this option is selected."
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} (+${self.price_change or 0})"

class BundleOptionGroup(TimeStampedModel):
    """
    Defines a reusable set of selectable options (checkbox, radio, etc.)
    linked to one or more Bundles.
    """
    name = models.CharField(max_length=255,blank=True,
        null=True,)

    minimum_required = models.PositiveIntegerField(default=0)


    items = models.ManyToManyField(
        "BundleOptionItem",
        related_name="option_groups",
        blank=True,
        help_text="Select one or more items that belong to this option group."
    )

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        """
        Display the type and number of options for easy identification.
        """
        item_count = self.items.count()
        return f"{self.name} Group ({item_count} option{'s' if item_count != 1 else ''})"


class Bundle(TimeStampedModel):
    group = models.ForeignKey(
        "BundleGroup",
        related_name="bundles",
        on_delete=models.CASCADE
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    min_lead_time = models.SmallIntegerField(default=0,verbose_name="Minimum Lead Time (in hours)")
    sort_order = models.PositiveIntegerField(default=0)

    option_groups = models.ManyToManyField(
        "BundleOptionGroup",
        related_name="bundles",
        blank=True
    )

    # ONE Bundle → ONE ModalForm
    modal_form = models.OneToOneField(
        "BundleModalForm",
        related_name="bundle",
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    class Meta:
        ordering = ["sort_order", "created_at"]
        unique_together = ("group", "name")

    def __str__(self):
        return f"{self.name} (${self.discounted_price})"
    
class BundleModalForm(TimeStampedModel):
    """
    Modal form for a specific Bundle.
    Each bundle can have at most one modal form.
    """
    field = models.ManyToManyField(
        "BundleModalField",
        related_name="form",
       null=True, blank=True
    )
    check_disclosure = models.ManyToManyField(
        'CheckDiscloure',
        related_name='modal_forms',
        blank=True,
        help_text="Select the disclosures to show in this "
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Modal Form - {self.title}"


class BundleModalField(TimeStampedModel):
    FIELD_TYPES = [
        ("text", "Text"),
        ("textarea", "Textarea"),
        ("number", "Number"),
        ("email", "Email"),
        ("radio", "Radio"),
        ("select", "Select"),
        ("checkbox", "Checkbox"),
        ("date", "Date"),
    ]



    label = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=50, choices=FIELD_TYPES, default="text")

    required = models.BooleanField(default=False)
    value = models.CharField(max_length=255, blank=True, null=True, verbose_name="Default value")

    placeholder = models.CharField(max_length=255, blank=True, null=True)
    help_text = models.CharField(max_length=255, blank=True, null=True)

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]


    def __str__(self):
        return f"{self.label} ({self.type})"

# -------------------------------------------------------------------
# Top-level Category
# -------------------------------------------------------------------
class ServiceCategory(TimeStampedModel):
    """Container for one or more Individual Services."""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    services = models.ManyToManyField(
        "IndividualService",
        related_name="categories",
        blank=True,
        help_text="Select the individual services that belong to this category."
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title



# -------------------------------------------------------------------
# Individual Service
# -------------------------------------------------------------------
class IndividualService(TimeStampedModel):
    class OrderProtectionType(models.TextChoices):
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    service_id = models.CharField(max_length=100, unique=False, help_text="Make this short as possible, This will be used in combined product name in NotaryDash.")
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=512, blank=True, null=True)
    header = models.CharField(max_length=255, blank=True, null=True)
    subheader_html = models.TextField(blank=True, null=True, verbose_name="Sub-Header")

    order_protection = models.BooleanField(default=False)
    order_protection_disabled = models.BooleanField(default=False)
    order_protection_type = models.CharField(
        max_length=50,
        choices=OrderProtectionType.choices,
        blank=True,
        null=True,
        help_text="Type of order protection applied (percent or fixed)."
    )
    order_protection_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="The numeric value for order protection."
    )

    form_ref = models.OneToOneField(
        "ServiceForm",
        related_name="linked_service",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Choose or create Service Items set",
        verbose_name="Service Item set"
    )

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title


# -------------------------------------------------------------------
# Service Form
# -------------------------------------------------------------------
class ServiceForm(TimeStampedModel):
 
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    items = models.ManyToManyField(
        "FormItem",
        related_name="forms",
        blank=True,
        help_text="Select one or more form items for this form."
    )
    submenus = models.ManyToManyField(
        "Submenu",
        related_name="forms",
        blank=True,
        help_text="Attach one or more submenus to this form."
    )
    modal_options = models.ManyToManyField(
        "ModalOption",
        related_name="forms",
        blank=True,
        help_text="Attach one or more modal options (e.g., 'Lockbox Code', 'Signer Name')."
    )

    def __str__(self):
        return f"{self.title} "


# -------------------------------------------------------------------
#  Form Item
# -------------------------------------------------------------------
class FormItem(TimeStampedModel):
    """
    Represents an individual configurable item that can appear
    in one or more ServiceForms.
    """
    identifier = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    subtitle = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    protection_invalid = models.BooleanField(default=False)
    min_lead_time = models.SmallIntegerField(default=0,verbose_name="Minimum Lead Time (in hours)")
    sort_order = models.PositiveIntegerField(default=0)
    option_group = models.OneToOneField(
        "OptionGroup",
        related_name="form_item",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="The group of selectable options linked to this form item."
    )

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.title}"


# -------------------------------------------------------------------
#  Option Group
# -------------------------------------------------------------------
class OptionGroup(TimeStampedModel):
    """
    Defines a set of selectable options (checkbox, radio, etc.)
    linked to a single FormItem.
    Now supports many-to-many relationship with OptionItems.
    """
    type = models.CharField(
        max_length=50,
        choices=[
            ("checkbox", "Checkbox"),
            # ("radio", "Radio"),
            # ("dropdown", "Dropdown"),
        ],
        default="checkbox",
        help_text="Type of option selection control."
    )
    minimum_required = models.PositiveIntegerField(default=0)
   
    # 🔹 Many-to-many relationship to OptionItem
    items = models.ManyToManyField(
        "OptionItem",
        related_name="groups",
        blank=True,
        help_text="Select one or more options that belong to this group."
    )

    class Meta:
        ordering = [ "created_at"]

    def __str__(self):
        """
        Display type and related FormItem identifier or title if linked,
        otherwi
        se indicate unlinked status.
        """
        if hasattr(self, "form_item") and self.form_item:  # type: ignore
            identifier = getattr(self.form_item, "identifier", None) or self.form_item.title  # type: ignore
            return f"{identifier} → {self.type.title()} Group"
        return f"Unlinked {self.type.title()} Group"



# -------------------------------------------------------------------
# Option Item
# -------------------------------------------------------------------
class OptionItem(TimeStampedModel):
    """
    Represents a selectable option that can appear in one or more OptionGroups.
    Example: Interior, Exterior, Ship Docs, etc.
    """
    identifier = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    value = models.BooleanField(default=False, verbose_name="Default Check")
    disabled = models.BooleanField(default=False)
    price_type = models.CharField(max_length=15, choices=[
            ("priceAdd", "Addition"),
            ("priceChange", "Change Into"),
        ], help_text="Price altering behavior")
    price_value= models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        """
        Show the label and a list of group types it's linked to, if any.
        """
        linked_groups = list(self.groups.values_list("type", flat=True)) if hasattr(self, "groups") else [] #type:ignore
        if linked_groups:
            return f"{self.label} {self.identifier}"
        return f"{self.label} {self.identifier} (Unlinked)"


# -------------------------------------------------------------------
# Submenu (e.g., page range, witness counter)
# -------------------------------------------------------------------
class Submenu(TimeStampedModel):
    
    type = models.CharField(max_length=50, default="mixed")
    name = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    items = models.ManyToManyField(
        "SubmenuItem",
        related_name="submenus",
        blank=True,
        help_text="Select one or more items to include in this submenu."
    )

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        label_display = self.name or "Untitled"
        return f"{label_display} ({self.type.title()}) Submenu" #type:ignore
    



class SubmenuItem(TimeStampedModel):
    identifier = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    type = models.CharField(
        max_length=50,
        choices=[
            ("radio", "Radio"),
            ("counter", "Counter"),
        ],
        blank=True,
        null=True,
        help_text="You cannot have Submenu type as Radio and Price modifier type as Multiple which breacks the order page"
    )
    value = models.JSONField(blank=True, null=True)
    form_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Used in HTML form",
        verbose_name="Form Name",
    )
    min_value = models.IntegerField(blank=True, null=True)
    max_value = models.IntegerField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def save(self, *args, **kwargs):
        """Automatically assign default value based on type."""
        if self.value is None:
            if self.type == "radio":
                self.value = False
            elif self.type == "counter":
                self.value = 0
        super().save(*args, **kwargs)


    def __str__(self):
        return self.label
# -------------------------------------------------------------------
#SubmenuPriceChange
# -------------------------------------------------------------------
class SubmenuPriceChange(TimeStampedModel):
    """
    Represents pricing modifiers for specific submenu items (like 'pages11_39', 'witness', etc.)
    Applied to a specific FormItem.
    """

    form_item = models.ForeignKey(
        "FormItem",
        related_name="submenu_price_changes",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The form item (e.g. 'NTinperson') this price change applies to."
    )

    submenu_item = models.ForeignKey(
        "SubmenuItem",
        related_name="price_modifiers",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The submenu item (e.g. 'pages11_39', 'witness') this modifier applies to."
    )

    change_type = models.CharField(
        max_length=20,
        choices=[
            ("add", "Add"),
            ("multiple", "Multiple"),
        ],
        help_text="How this price modifies the base (additive or multiplier)."
    )

    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="The numeric amount or multiplier value."
    )

    class Meta:
        unique_together = ("form_item", "submenu_item")
        ordering = ["form_item", "submenu_item"]

    def __str__(self):
        return f"{self.form_item.identifier if self.form_item else "form item unliked"} → {self.submenu_item.identifier if self.submenu_item else "Submenu item unlinked"} ({self.change_type}: {self.value})" #type: ignore

# -------------------------------------------------------------------
# Modal Option (custom inline forms like “Lockbox code”)
# -------------------------------------------------------------------
class ModalOption(TimeStampedModel):

    each_item = models.BooleanField(default=False)
    label = models.CharField(max_length=255)
    field_name = models.CharField(max_length=100)
    footer_head= models.CharField(max_length=100, blank=True, null=True,)
    footer_body = models.TextField( blank=True, null=True)
    hidden = models.BooleanField(default=False)
    check_disclosure = models.ManyToManyField(
        'CheckDiscloure',
        related_name='modal_options',
        blank=True,
        help_text="Select the disclosures this modal option only applies to (Leave it blank to applied in all disclosures)."
    )
    field_type = models.CharField(
        max_length=50,
        choices=[
            ("text", "Text"),
            ("email", "Email"),
            ("number", "Number"),
            ("date", "Date"),
        ],
        default="text",
        help_text="Type of input field rendered in frontend."
    ) # text, email, number, etc.
    required = models.BooleanField(default=False)
    value = models.CharField(max_length=255, blank=True, null=True, verbose_name="Default value")
    sort_order = models.PositiveIntegerField(default=0)
    valid_for_items = models.ManyToManyField(
        "FormItem",
        related_name="modal_valid_options",
        blank=True,
        help_text="Select the FormItems this modal option only applies to (Leave it blank to applied in all items)."
    )

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} ({self.field_type})"


class ModalOptionToggle(TimeStampedModel):
    modal_option = models.ForeignKey(
        "ModalOption",
        related_name="toggles",
        on_delete=models.CASCADE,
        help_text="The parent modal option this toggle controls."
    )
    label = models.CharField(max_length=255)
    toggle_type = models.CharField(
        max_length=50,
        choices=[
            ("checkbox", "Checkbox"),
            ("radio", "Radio"),
        ],
        default="checkbox"
    )
    options = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text='List of options for radio toggles (e.g. ["Yes", "No"]).'
    )
    trigger_value = models.CharField(
        max_length=255,
        help_text="Value that triggers the visibility of the field (e.g. 'true' or 'Yes')."
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} ({self.toggle_type})"


# -------------------------------------------------------------------
# Disclosure (Array-based)
# -------------------------------------------------------------------
class Disclosure(TimeStampedModel):
    """
    Stores multiple disclosure/info messages per service.
    """
    service = models.ForeignKey(
        IndividualService, related_name="disclosures", on_delete=models.CASCADE
    )
    type = models.CharField(max_length=50, default="info",        choices=[
            ("info", "Info"),
            ("warning", "Warning"),
            ("success", "Success"),
            ("danger", "Danger"),
        ], help_text="Text color variations")
    message = models.TextField(help_text="Disclosure or information message to show")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.type.title()} disclosure for {self.service.title}"

class CheckDiscloure(TimeStampedModel):
    """
    Stores Checkbox input of disclousures
    """
    name = models.CharField(max_length=255)
    required = models.BooleanField(default=False, help_text="Is this disclosure required?")
    message = models.TextField(help_text="Disclosure or information message to show")
    sort_order = models.PositiveIntegerField(default=0)
    active_flag = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name

class DiscountLevel(TimeStampedModel):
    """
    Represents discount slabs like:
    2 items → 20%
    3 items → 30%
    ...
    """

    items = models.PositiveIntegerField(help_text="Minimum items required")
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage discount"
    )
    active_flag = models.BooleanField(default=True)

    class Meta:
        ordering = ["items"]
        unique_together = ("items", "percent")

    def __str__(self):
        return f"{self.items} items → {self.percent} {"Enabled" if self.active_flag else "Disabled"}%"

        