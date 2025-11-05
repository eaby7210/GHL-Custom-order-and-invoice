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
# 🔹 INLINE CONFIGS (nested editing)
# ==============================================================

# --- Option Items Inline ---
class OptionItemInline(SortableInlineAdminMixin, admin.TabularInline):
    model = OptionItem
    extra = 0
    fields = ("label", "value", "disabled", "price_change", "sort_order")
    ordering = ("sort_order",)


# --- Option Groups Inline ---
class OptionGroupInline(SortableInlineAdminMixin, admin.TabularInline):
    model = OptionGroup
    extra = 0
    fields = ("type", "minimum_required", "sort_order")
    ordering = ("sort_order",)
    show_change_link = True


# --- Submenu Item Inline ---
class SubmenuItemInline(SortableInlineAdminMixin, admin.TabularInline):
    model = SubmenuItem
    extra = 0
    fields = ("identifier", "label", "type", "value", "min_value", "max_value", "sort_order")
    ordering = ("sort_order",)


# --- Submenu Inline ---
class SubmenuInline(SortableInlineAdminMixin, admin.StackedInline):
    model = Submenu
    extra = 0
    fields = ("type", "label", "sort_order")
    ordering = ("sort_order",)
    show_change_link = True


# --- Submenu Price Change Inline ---
class SubmenuPriceChangeInline(admin.TabularInline):
    model = SubmenuPriceChange
    extra = 0
    fields = ("key", "change_type", "value")
    ordering = ("key",)


# --- Modal Option Inline ---
class ModalOptionInline(admin.TabularInline):
    model = ModalOption
    extra = 0
    fields = ("each_item", "label", "field_name", "field_type", "required", "sort_order")
    ordering = ("sort_order",)


# --- Disclosure Inline ---
class DisclosureInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Disclosure
    extra = 0
    fields = ("type", "message", "sort_order")
    ordering = ("sort_order",)


# ==============================================================
# 🔹 SERVICE FORM LEVEL
# ==============================================================

class FormItemInline(SortableInlineAdminMixin, admin.StackedInline):
    model = FormItem
    extra = 0
    show_change_link = True
    fieldsets = (
        (None, {
            "fields": (
                "identifier", "title", "subtitle", "price", "base_price", "protection_invalid", "sort_order"
            ),
            "classes": ("collapse",)
        }),
    )
    ordering = ("sort_order",)




@admin.register(ServiceForm)
class ServiceFormAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("title", "service")
    search_fields = ("title", "description", "service__title")
    inlines = [FormItemInline, SubmenuInline, ModalOptionInline]
    ordering = ("created_at",)
    fieldsets = (
        (None, {"fields": ("service", "title", "description")}),
    )


# ==============================================================
# 🔹 INDIVIDUAL SERVICE ADMIN
# ==============================================================

@admin.register(IndividualService)
class IndividualServiceAdmin(SummernoteModelAdmin, SortableAdminMixin):
    list_display = ("title", "order_protection", "order_protection_type", "sort_order")
    list_filter = ("order_protection", "order_protection_type")
    search_fields = ("title", "service_id", "subtitle", "header")
    summernote_fields = ("subheader_html",)
    ordering = ("sort_order",)
    inlines = [DisclosureInline]
    fieldsets = (
        ("Service Info", {
            "fields": (
                "service_id", "title", "subtitle", "header", "subheader_html"
            )
        }),
        ("Order Protection", {
            "fields": (
                "order_protection", "order_protection_disabled", "order_protection_type", "order_protection_value"
            ),
            "classes": ("collapse",)
        }),
        ("Sorting", {"fields": ("sort_order",)}),
    )


# ==============================================================
# 🔹 SERVICE CATEGORY ADMIN
# ==============================================================

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("title", "description", "sort_order")
    search_fields = ("title", "description")
    ordering = ("sort_order",)


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


# ==============================================================
# 🔹 SERVICE VARIANCE ADMIN
# ==============================================================

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


# ==============================================================
# 🔹 SUBMENU, PRICE CHANGE, AND OPTIONS
# ==============================================================

@admin.register(OptionGroup)
class OptionGroupAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("form_item", "type", "minimum_required", "sort_order")
    ordering = ("form_item", "sort_order")
    inlines = [OptionItemInline]
    search_fields = ("form_item__title",)


@admin.register(Submenu)
class SubmenuAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("form", "type", "label", "sort_order")
    inlines = [SubmenuItemInline]
    search_fields = ("form__title", "label")


@admin.register(SubmenuPriceChange)
class SubmenuPriceChangeAdmin(admin.ModelAdmin):
    list_display = ("form_item", "key", "change_type", "value")
    list_filter = ("change_type",)
    search_fields = ("key", "form_item__title")


@admin.register(ModalOption)
class ModalOptionAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("form", "label", "field_name", "field_type", "required", "sort_order")
    search_fields = ("label", "field_name")
    ordering = ("form", "sort_order")


@admin.register(Disclosure)
class DisclosureAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("service", "type", "sort_order")
    search_fields = ("service__title", "message")
    ordering = ("service", "sort_order")
