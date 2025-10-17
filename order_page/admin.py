# admin.py
from django.contrib import admin
from .models import TermsOfConditions
from django_summernote.admin import SummernoteModelAdmin

@admin.register(TermsOfConditions)
class TermsOfConditionsAdmin(SummernoteModelAdmin):
    summernote_fields = ('body',)
