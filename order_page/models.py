from django.db import models
from django.utils.html import strip_tags
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import JSONField  
from django.utils import timezone
from django.db import transaction




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