from django.contrib import admin
from .models import Partner, Customer, Link


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = (
        "id", "first_name", "last_name", "email", "company_name",
        "program_id", "organization_id", "payout_method", "country_code", "created_at"
    )
    list_filter = ("program_id", "organization_id", "country_code", "payout_method")
    search_fields = ("id", "first_name", "last_name", "email", "company_name")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "email", "partner", "status",
        "program_id", "organization_id", "created_at", "updated_at"
    )
    list_filter = ("status", "program_id", "organization_id")
    search_fields = ("id", "name", "email", "customer_id")
    ordering = ("-created_at",)
    autocomplete_fields = ("partner",)
    date_hierarchy = "created_at"


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = (
        "id", "param", "value", "partner", "program_id",
        "organization_id", "created_at", "updated_at"
    )
    list_filter = ("program_id", "organization_id", "param")
    search_fields = ("id", "param", "value")
    ordering = ("-created_at",)
    autocomplete_fields = ("partner",)
    date_hierarchy = "created_at"
