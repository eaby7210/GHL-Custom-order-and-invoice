# admin.py
from django import forms
from .models import SubmenuItem

class SubmenuItemForm(forms.ModelForm):
    class Meta:
        model = SubmenuItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        field_type = instance.type if instance else None
        print(f"field_type {field_type}")
        if field_type == "radio":
            self.fields["value"] = forms.BooleanField(
                required=False,
                label="Default Value",
                help_text="Default selected (True/False)"
            )
        elif field_type == "counter":
            self.fields["value"] = forms.IntegerField(
                required=False,
                label="Default Value",
                help_text="Default counter starting value (integer)"
            )
        else:
            self.fields["value"] = forms.JSONField(
                required=False,
                label="Value",
                help_text="Raw JSON (use for other future field types)"
            )
