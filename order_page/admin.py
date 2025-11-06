# admin.py
from django.contrib import admin
from .models import TermsOfConditions
from django_summernote.admin import SummernoteModelAdmin
from django import forms


@admin.register(TermsOfConditions)
class TermsOfConditionsAdmin(SummernoteModelAdmin):
    summernote_fields = ('body',)

from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from adminsortable2.admin import SortableAdminMixin, SortableInlineAdminMixin

from .models import (
    ServiceVariance, BundleGroup, Bundle, ServiceCategory,
    IndividualService, ServiceForm, FormItem, OptionGroup,
    OptionItem, Submenu, SubmenuItem, SubmenuPriceChange,
    ModalOption, Disclosure
)




# ==============================================================
# 🔹 BUNDLE ADMIN
# ==============================================================

class BundleInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Bundle
    extra = 0
    fields = ("name", "description", "base_price", "discounted_price", "is_active", "sort_order")
    ordering = ("sort_order",)


@admin.register(BundleGroup)
class BundleGroupAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "header", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "header", "subheader")
    ordering = ("sort_order",)
    inlines = [BundleInline]


@admin.register(Bundle)
class BundleAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "group", "base_price", "discounted_price", "is_active", "sort_order")
    list_filter = ("is_active", "group")
    search_fields = ("name", "description")
    ordering = ("group", "sort_order")




@admin.register(ServiceVariance)
class ServiceVarianceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "version_number",
        "is_default", "is_active", "created_at"
    )
    list_filter = ("is_active", "is_default", "service_category", "bundle_group")
    search_fields = ("name", "notes", "service_category__title", "bundle_group__name")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("clients",)
    fieldsets = (
        ("Variance Details", {
            "fields": (
                "name", "notes", "version_number",
                "service_category", "bundle_group",
            )
        }),
        ("Status & Control", {
            "fields": (
                "is_default", "is_active", "clients"
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    ordering = ("-created_at",)

    def get_readonly_fields(self, request, obj=None):
        """Prevent edits on default variances."""
        if obj and obj.is_default:
            return tuple(self.readonly_fields) + ("is_default", "clients",)
        return self.readonly_fields




@admin.register(OptionItem)
class OptionItemAdmin(admin.ModelAdmin):
    list_display = ("label", "identifier", "value", "disabled", "price_change", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("label", "identifier")
    list_filter = ("disabled",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {"fields": ("identifier", "label", "value", "disabled", "price_change")}),
        ("Ordering", {"fields": ("sort_order",)}),
    )


@admin.register(SubmenuPriceChange)
class SubmenuPriceChangeAdmin(admin.ModelAdmin):
    list_display = ("key", "change_type", "value")
    search_fields = ("key",)
    list_editable = ("value",)
    ordering = ("key",)
    list_filter = ("change_type",)


@admin.register(ModalOption)
class ModalOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "field_name", "field_type", "required", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("label", "field_name")
    list_filter = ("field_type", "required")
    ordering = ("sort_order",)


@admin.register(Disclosure)
class DisclosureAdmin(admin.ModelAdmin):
    list_display = ("service", "type", "message", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("message", "service__title")
    list_filter = ("type",)
    ordering = ("sort_order",)
    autocomplete_fields = ("service",)

# ----------------------------------------------------------
# 🔹 Mid-Level Models (OptionGroup, Submenu, SubmenuItem)
# ----------------------------------------------------------

@admin.register(OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    list_display = ("__str__", "type", "minimum_required", "sort_order")
    list_editable = ("sort_order",)
    filter_horizontal = ("items",)
    ordering = ("sort_order",)
    search_fields = ("form_item__title",)
    fieldsets = (
        (None, {
            "fields": ("type", "minimum_required", "items")
        }),
        ("Meta", {"fields": ("sort_order",)})
    )


@admin.register(SubmenuItem)
class SubmenuItemAdmin(admin.ModelAdmin):
    list_display = ("label", "identifier", "type", "min_value", "max_value", "sort_order")
    list_editable = ("sort_order",)
    filter_horizontal = ("price_changes",)
    search_fields = ("label", "identifier")
    list_filter = ("type",)
    ordering = ("sort_order",)


@admin.register(Submenu)
class SubmenuAdmin(admin.ModelAdmin):
    list_display = ("label", "type", "sort_order")
    list_editable = ("sort_order",)
    filter_horizontal = ("items",)
    search_fields = ("label",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {"fields": ("label", "type", "items")}),
        ("Meta", {"fields": ("sort_order",)}),
    )

# ----------------------------------------------------------
# 🔹 FormItem & ServiceForm Admins (Core of configuration)
# ----------------------------------------------------------

@admin.register(FormItem)
class FormItemAdmin(admin.ModelAdmin):
    list_display = ("title", "identifier", "price", "base_price", "protection_invalid", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("title", "identifier")
    autocomplete_fields = ("option_group",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {
            "fields": ("identifier", "title", "subtitle", "price", "base_price", "protection_invalid", "option_group")
        }),
        ("Ordering", {"fields": ("sort_order",)})
    )


@admin.register(ServiceForm)
class ServiceFormAdmin(admin.ModelAdmin):
    list_display = ("title", "description")
    search_fields = ("title",)
    filter_horizontal = ("items", "submenus", "modal_options")
    ordering = ("title",)
    fieldsets = (
        (None, {
            "fields": ("title", "description")
        }),
        ("Relations", {
            "fields": ("items", "submenus", "modal_options")
        }),
    )

# ----------------------------------------------------------
# 🔹 IndividualService & ServiceCategory
# ----------------------------------------------------------

class DisclosureInline(admin.TabularInline):
    model = Disclosure
    extra = 1
    fields = ("type", "message", "sort_order")
    show_change_link = True


@admin.register(IndividualService)
class IndividualServiceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "service_id",
        "order_protection",
        "order_protection_type",
        "order_protection_value",
        "sort_order",
    )
    list_editable = ("sort_order",)
    search_fields = ("title", "service_id")
    list_filter = ("order_protection_type", "order_protection_disabled")
    ordering = ("sort_order",)
    autocomplete_fields = ("form_ref",)
    inlines = [DisclosureInline]

    fieldsets = (
        ("Basic Info", {
            "fields": (
                "service_id",
                "title",
                "subtitle",
                "header",
                "subheader_html",
            )
        }),
        ("Order Protection", {
            "fields": (
                "order_protection",
                "order_protection_disabled",
                "order_protection_type",
                "order_protection_value",
            )
        }),
        ("Form Reference", {"fields": ("form_ref",)}),
        ("Meta", {"fields": ("sort_order",)}),
    )


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "description", "sort_order")
    list_editable = ("sort_order",)
    filter_horizontal = ("services",)
    search_fields = ("title",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {
            "fields": ("title", "description", "services")
        }),
        ("Meta", {"fields": ("sort_order",)}),
    )