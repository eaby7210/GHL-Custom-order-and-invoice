from django.db import models
from django.utils.html import strip_tags
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import JSONField  
from django.utils import timezone
from django.db import transaction
import uuid
from stripe_payment.models import NotaryClientCompany 



class TermsOfConditions(models.Model):
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

    def __str__(self):
        return self.title
    

class TypeformForm(models.Model):
    """Unique Typeform form definition"""
    form_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    settings = models.JSONField(default=dict, blank=True)
    endings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title or self.form_id


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

    name = models.CharField(
        max_length=255,
        help_text="Version or variance name, e.g. 'Fall 2025 Edition', 'Company One Special'."
    )

    service_category = models.ForeignKey(
        "ServiceCategory",
        related_name="variances",
        on_delete=models.CASCADE,
        help_text="Associated service category this version applies to."
    )
    bundle_group = models.ManyToManyField(
        "BundleGroup",
        related_name="variances",
        help_text="Associated bundle group this version applies to."
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
        return self.header


class Bundle(TimeStampedModel):
    """
    Represents an individual bundle (e.g., 'Deal Accelerator').
    """
    group = models.ForeignKey(
        BundleGroup,
        related_name="bundles",
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]
        unique_together = ("group", "name")

    def __str__(self):
        return f"{self.name} (${self.discounted_price})"

    # @property
    # def savings(self):
    #     """Calculate the savings amount"""
    #     return round(self.base_price - self.discounted_price, 2)

    # @property
    # def discount_percent(self):
    #     """Calculate discount percentage"""
    #     if self.base_price == 0:
    #         return 0
    #     return round((self.savings / self.base_price) * 100, 2)




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

    slug = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=512, blank=True, null=True)
    header = models.CharField(max_length=255, blank=True, null=True)
    subheader_html = models.TextField(blank=True, null=True)

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

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title

# -------------------------------------------------------------------
# Service Form
# -------------------------------------------------------------------
class ServiceForm(TimeStampedModel):
    service = models.OneToOneField(
        IndividualService, related_name="form", on_delete=models.CASCADE
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.title} ({self.service.title})"


# -------------------------------------------------------------------
#  Form Item
# -------------------------------------------------------------------
class FormItem(TimeStampedModel):
    form = models.ForeignKey(ServiceForm, related_name="items", on_delete=models.CASCADE)
    identifier = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    subtitle = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    protection_invalid = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.title} ({self.form.service.title})"


# -------------------------------------------------------------------
#  Option Group
# -------------------------------------------------------------------
class OptionGroup(TimeStampedModel):
    form_item = models.ForeignKey(FormItem, related_name="option_groups", on_delete=models.CASCADE)
    type = models.CharField(max_length=50, default="checkbox")  # e.g., checkbox, radio
    minimum_required = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.type.title()} options for {self.form_item.title}"


# -------------------------------------------------------------------
# Option Item
# -------------------------------------------------------------------
class OptionItem(TimeStampedModel):
    group = models.ForeignKey(OptionGroup, related_name="items", on_delete=models.CASCADE)
    identifier = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    value = models.BooleanField(default=False)
    disabled = models.BooleanField(default=False)
    price_change = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} ({self.group.form_item.title})"


# -------------------------------------------------------------------
# Submenu (e.g., page range, witness counter)
# -------------------------------------------------------------------
class Submenu(TimeStampedModel):
    form = models.ForeignKey(ServiceForm, related_name="submenus", on_delete=models.CASCADE)
    type = models.CharField(max_length=50, default="mixed")
    label = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"Submenu ({self.form.service.title})"


class SubmenuItem(TimeStampedModel):
    submenu = models.ForeignKey(Submenu, related_name="items", on_delete=models.CASCADE)
    identifier = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=50, blank=True, null=True)  # radio, counter, etc.
    value = models.CharField(max_length=255, blank=True, null=True)
    min_value = models.IntegerField(blank=True, null=True)
    max_value = models.IntegerField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.label


# -------------------------------------------------------------------
#SubmenuPriceChange (NEW)
# -------------------------------------------------------------------
class SubmenuPriceChange(TimeStampedModel):
    """
    Represents pricing modifiers for specific submenus (like 'pages11_39', 'witness', etc.)
    """
    form_item = models.ForeignKey(FormItem, related_name="submenu_price_changes", on_delete=models.CASCADE)
    key = models.CharField(max_length=100, help_text="Submenu key, e.g. 'pages11_39'")
    change_type = models.CharField(max_length=20, choices=[
        ("add", "Add"),
        ("multiple", "Multiple")
    ])
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.key} ({self.change_type}: {self.value})"


# -------------------------------------------------------------------
# Modal Option (custom inline forms like “Lockbox code”)
# -------------------------------------------------------------------
class ModalOption(TimeStampedModel):
    form = models.ForeignKey(ServiceForm, related_name="modal_options", on_delete=models.CASCADE)
    each_item = models.BooleanField(default=False)
    label = models.CharField(max_length=255)
    field_name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=50, default="text")  # text, email, number, etc.
    required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} ({self.form.service.title})"


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
    type = models.CharField(max_length=50, default="info", help_text="e.g., 'info', 'warning'")
    message = models.TextField(help_text="Disclosure or information message to show")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.type.title()} disclosure for {self.service.title}"
