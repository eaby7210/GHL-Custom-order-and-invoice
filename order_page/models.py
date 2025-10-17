from django.db import models
from django.utils.html import strip_tags
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError




class TermsOfConditions(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Enter basic HTML content for terms of conditions (no JS).")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
            db_table = 'terms_of_conditions'



    def clean(self):
        # optional: basic sanitization or validation
        disallowed_tags = ["script", "iframe", "object", "embed"]
        for tag in disallowed_tags:
            if f"<{tag}" in self.body.lower():
                raise ValidationError(f"Tag <{tag}> is not allowed.")
        super().clean()

    def __str__(self):
        return self.title