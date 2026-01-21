# admin.py
from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from adminsortable2.admin import SortableAdminMixin, SortableInlineAdminMixin
from .models import (
    TermsOfConditions,ServiceVariance, BundleGroup, Bundle, ServiceCategory,
    IndividualService, ServiceForm, FormItem, OptionGroup,
    OptionItem, Submenu, SubmenuItem, SubmenuPriceChange,
    ModalOption, Disclosure,    BundleOptionGroup,
    BundleOptionItem,
        BundleGroup,
        Bundle,
        BundleOptionGroup,
        BundleOptionItem,
        BundleModalForm,
        BundleModalField,
        DiscountLevel, CheckDiscloure
)
from .forms import SubmenuItemForm
from django.utils.html import format_html
from .models import TypeformForm, TypeformField, TypeformPartnerMapping
from .services import TypeformService
from django.contrib import messages



@admin.register(TermsOfConditions)
class TermsOfConditionsAdmin(SummernoteModelAdmin):
    summernote_fields = ('body',)
    
# -------------------------------------------------------------------
#  Inline for Option Items (only inline allowed)
# -------------------------------------------------------------------

class BundleOptionItemInline(admin.TabularInline):
    model = BundleOptionGroup.items.through  # Through table for M2M
    extra = 1
    verbose_name = "Option Item Link"
    verbose_name_plural = "Linked Option Items"
    autocomplete_fields = ["bundleoptionitem"] if hasattr(BundleOptionGroup.items, "field") else []


# -------------------------------------------------------------------
#  Bundle Option Item Admin
# -------------------------------------------------------------------
@admin.register(BundleOptionItem)
class BundleOptionItemAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("label", "price_change", "disabled", "sort_order", "view_groups")
    search_fields = ("label", "identifier")
    list_editable = ("sort_order", "disabled")
    ordering = ("sort_order",)

    def view_groups(self, obj):
        groups = obj.option_groups.all()
        if not groups:
            return "-"
        links = [
            f'<a href="/admin/order_page/bundleoptiongroup/{g.id}/change/">{g}</a>'
            for g in groups
        ]
        return format_html("<br>".join(links))
    view_groups.short_description = "Used In Groups"


# -------------------------------------------------------------------
#  Bundle Option Group Admin
# -------------------------------------------------------------------
@admin.register(BundleOptionGroup)
class BundleOptionGroupAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ( "minimum_required", "sort_order", "view_bundles", "manage_items")
    search_fields = ("type",)
    list_editable = ("sort_order",)
    ordering = ("sort_order",)
    inlines = [BundleOptionItemInline]

    def view_bundles(self, obj):
        bundles = obj.bundles.all()
        if not bundles:
            return "-"
        links = [
            f'<a href="/admin/order_page/bundle/{b.id}/change/">{b.name}</a>'
            for b in bundles
        ]
        return format_html("<br>".join(links))
    view_bundles.short_description = "Used In Bundles"

    def manage_items(self, obj):
        return format_html(
            '<a class="button" href="/admin/order_page/bundleoptionitem/">🔗 Manage Items</a>'
        )
    manage_items.short_description = "Actions"
    manage_items.allow_tags = True


# -------------------------------------------------------------------
#  Bundle Admin
# -------------------------------------------------------------------
# @admin.register(Bundle)
# class BundleAdmin(SortableAdminMixin, admin.ModelAdmin):
#     list_display = (
#         "name",
#         "group",
#         "base_price",
#         "discounted_price",
#         "is_active",
#         "sort_order",
#         "manage_option_groups",

#     )
#     list_filter = ("is_active", "group")
#     search_fields = ("name", "description")
#     ordering = ("group", "sort_order")
#     filter_horizontal = ("option_groups",)

#     def manage_option_groups(self, obj):
#         """
#         Adds quick 'edit' and 'add' buttons for option groups.
#         """
#         edit_links = ""
#         if obj.option_groups.exists():
#             edit_links = "<br>".join(
#                 [
#                     f'<a href="/admin/order_page/bundleoptiongroup/{g.id}/change/">✏️ {g}</a>'
#                     for g in obj.option_groups.all()
#                 ]
#             )
#         add_link = '<a class="button" href="/admin/order_page/bundleoptiongroup/add/">➕ Add Group</a>'
#         return format_html(f"{edit_links}<br>{add_link}")
#     manage_option_groups.short_description = "Option Groups"


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "discounted_price", "is_active", "sort_order")
    list_filter = ("group", "is_active")
    search_fields = ("name", "description")
    ordering = ("group", "sort_order")

    filter_horizontal = ("option_groups",)

    fieldsets = (
        ("Bundle Info", {
            "fields": ("group", "name", "description", "is_active", "sort_order")
        }),
        ("Pricing", {
            "fields": ("base_price", "discounted_price")
        }),
        ("Option Groups", {
            "fields": ("option_groups",)
        }),
        ("Modal Form", {
            "fields": ("modal_form",)   # ✔ allowed because OneToOneField
        }),
    )


@admin.register(BundleModalForm)
class BundleModalFormAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active")
    search_fields = ("title",)
    list_filter = ("is_active",)

    filter_horizontal = ("field",)   # ✔ multi-select for modal fields

    fieldsets = (
        ("Modal Details", {
            "fields": ("title", "description", "is_active")
        }),
        ("Fields", {
            "fields": ("field",)     # ✔ this is allowed (M2M)
        }),
         ("Check Disclosures", {
            "fields": ("check_disclosure",)     # ✔ this is allowed (M2M)
        }),
    )

@admin.register(BundleModalField)
class BundleModalFieldAdmin(admin.ModelAdmin):
    list_display = ("label", "type", "required", "sort_order")
    search_fields = ("label", "name")
    list_filter = ("type", "required")
    ordering = ("sort_order",)

    fieldsets = (
        ("Field Info", {
            "fields": (
                "label",
                "name",
                "type",
                "required",
                "value",
                "placeholder",
                "help_text",
                "sort_order",
            )
        }),
    )

# -------------------------------------------------------------------
#  Bundle Group Admin
# -------------------------------------------------------------------
class BundleInline(admin.TabularInline):
    model = Bundle
    extra = 0
    fields = ("name","description", "base_price", "discounted_price", "is_active")
    show_change_link = True


@admin.register(BundleGroup)
class BundleGroupAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "header", "is_active", "sort_order", "manage_bundles")
    list_filter = ("is_active",)
    search_fields = ("name", "header", "subheader")
    ordering = ("sort_order",)
    inlines = [BundleInline]

    def manage_bundles(self, obj):
        """
        Add quick edit / add buttons for bundles in group list page.
        """
        edit_links = ""
        if obj.bundles.exists():
            edit_links = "<br>".join(
                [
                    f'<a href="/admin/order_page/bundle/{b.id}/change/">✏️ {b.name}</a>'
                    for b in obj.bundles.all()
                ]
            )
        add_link = f'<a class="button" href="/admin/order_page/bundle/add/?group={obj.id}">➕ Add Bundle</a>'
        return format_html(f"{edit_links}<br>{add_link}")
    manage_bundles.short_description = "Manage Bundles"



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
                "service_category","bundle_order_protection_type","bundle_order_protection_value", "bundle_group",
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
    list_display = ("label", "identifier", "value", "disabled",  "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("label", "identifier")
    list_filter = ("disabled",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {"fields": ("identifier", "label", "value", "disabled","price_type","price_value")}),
        ("Ordering", {"fields": ("sort_order",)}),
    )


@admin.register(SubmenuPriceChange)
class SubmenuPriceChangeAdmin(admin.ModelAdmin):
    list_display = ("submenu_item", "form_item", "change_type", "value")
    search_fields = (
        "submenu_item__identifier",
        "form_item__identifier",
        "change_type",
    )
    list_editable = ("value",)
    ordering = ("submenu_item__identifier",)
    list_filter = ("change_type",)
    autocomplete_fields = ("form_item", "submenu_item")


class SubmenuPriceChangeInline(admin.TabularInline):
    model = SubmenuPriceChange
    extra = 1
    autocomplete_fields = ("form_item",)
    fields = ("form_item", "change_type", "value")
    ordering = ("form_item__sort_order",)
    verbose_name = "Form Item Price Modifier"
    verbose_name_plural = "Linked Form Item Price Modifiers"



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


@admin.register(OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    list_display = ("__str__", "type", "minimum_required")
   
    filter_horizontal = ("items",)
    # ordering = ("sort_order",)
    search_fields = ("form_item__title","__str__")
    fieldsets = (
        (None, {
            "fields": ("type", "minimum_required", "items")
        }),
        # ("Meta", {"fields": ("sort_order",)})
    )


@admin.register(SubmenuItem)
class SubmenuItemAdmin(admin.ModelAdmin):
    form = SubmenuItemForm
    list_display = (
        "label", "identifier", "type", "display_value",
        "min_value", "max_value", "sort_order"
    )
    list_editable = ("sort_order",)
    search_fields = ("label", "identifier")
    list_filter = ("type",)
    ordering = ("sort_order",)
    inlines = [SubmenuPriceChangeInline]

    # Base fieldsets (used for editing)
    fieldsets = (
        (None, {
            "fields": (
                "identifier",
                "label",
                "type",
                "value",     
                "form_name",
                "min_value",
                "max_value",
            )
        }),
        ("Ordering", {"fields": ("sort_order",)}),
    )

    # def get_fieldsets(self, request, obj=None):
    #     """
    #     Hide 'value' field on create form,
    #     show it only on edit.
    #     """
    #     fieldsets = super().get_fieldsets(request, obj)

    #     # If obj is None → creating new item → hide 'value'
    #     if obj is None:
    #         new_fieldsets = []
    #         for name, data in fieldsets:
    #             fields = tuple(f for f in data["fields"] if f != "value")
    #             new_fieldsets.append((name, {**data, "fields": fields}))
    #         return new_fieldsets
    #     return fieldsets

    def display_value(self, obj):
        """Show a readable preview in the list view."""
        if obj.type == "radio":
            return "✅ True" if obj.value else "False"
        if obj.type == "counter":
            return f"{obj.value or 0}"
        return obj.value
    display_value.short_description = "Default Value"
    
    class Media:
        js = ("order_page/js/submenuitem_admin.js",)


@admin.register(Submenu)
class SubmenuAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "sort_order")
    list_editable = ("sort_order",)
    filter_horizontal = ("items",)
    search_fields = ("name",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {"fields": ("name", "type", "items")}),
        ("Meta", {"fields": ("sort_order",)}),
    )



@admin.register(FormItem)
class FormItemAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("title", "identifier", "price", "protection_invalid", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("title", "identifier")
    autocomplete_fields = ("option_group",)
    ordering = ("sort_order",)
    fieldsets = (
        (None, {
            "fields": (
                "identifier",
                "title",
                "subtitle",
                "price",
                # "base_price",
                "protection_invalid",
                "option_group",
            )
        }),
        ("Ordering", {"fields": ("sort_order",)}),
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



class DisclosureInline(admin.TabularInline):
    model = Disclosure
    extra = 1
    fields = ("type", "message", "sort_order")
    show_change_link = True


@admin.register(IndividualService)
class IndividualServiceAdmin(SummernoteModelAdmin):
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
    summernote_fields = ('subheader_html',)

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


@admin.register(DiscountLevel)
class DiscountLevelAdmin(admin.ModelAdmin):

    # Fields shown in list page
    list_display = (
        "items",
        "percent",
        "active_flag",
        "created_at",
        "updated_at",
    )

    # Make admin clean & usable
    list_filter = ("active_flag", "created_at")
    search_fields = ("items", "percent")
    ordering = ("items",)

    # Allow inline edit for active_flag & percent
    list_editable = ("percent", "active_flag")

    # Prevent accidental edits to system timestamps
    readonly_fields = ("created_at", "updated_at")

    # Add collapsible grouping
    fieldsets = (
        ("Discount Details", {
            "fields": ("items", "percent", "active_flag"),
        }),
        ("System Information (Read-only)", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    # Optional: allow bulk deactivate / activate
    actions = ["activate_levels", "deactivate_levels"]

    def activate_levels(self, request, queryset):
        count = queryset.update(active_flag=True)
        self.message_user(request, f"{count} discount levels activated.")

    def deactivate_levels(self, request, queryset):
        count = queryset.update(active_flag=False)
        self.message_user(request, f"{count} discount levels deactivated.")

    activate_levels.short_description = "Mark selected discount levels as active"
    deactivate_levels.short_description = "Mark selected discount levels as inactive"

@admin.register(CheckDiscloure)
class CheckDiscloureAdmin(admin.ModelAdmin):
    list_display = ("name", "required", "sort_order", "active_flag")
    list_editable = ("sort_order", "active_flag", "required")
    search_fields = ("name", "message")
    list_filter = ("active_flag", "required")
    ordering = ("sort_order",)
    fieldsets = (
        (None, {
            "fields": ("name", "message", "required", "active_flag", "sort_order")
        }),
    )

# -------------------------------------------------------------------
#  Typeform Admin
# -------------------------------------------------------------------
from .models import (
    TypeformForm, TypeformField, TypeformPartnerMapping,
    TypeformWelcomeScreen, TypeformThankYouScreen, TypeformLogic
)
from .services import TypeformService
from django.contrib import messages

class TypeformFieldInline(admin.TabularInline):
    model = TypeformField
    extra = 0
    fields = ("title", "field_type", "field_id", "ref")
    readonly_fields = ("title", "field_type", "field_id", "ref")
    show_change_link = True

class TypeformWelcomeScreenInline(admin.TabularInline):
    model = TypeformWelcomeScreen
    extra = 0
    fields = ("title", "ref")
    readonly_fields = ("title", "ref")
    show_change_link = True

class TypeformThankYouScreenInline(admin.TabularInline):
    model = TypeformThankYouScreen
    extra = 0
    fields = ("title", "type", "ref")
    readonly_fields = ("title", "type", "ref")
    show_change_link = True

class TypeformLogicInline(admin.TabularInline):
    model = TypeformLogic
    extra = 0
    fields = ("ref", "type")
    readonly_fields = ("ref", "type")
    show_change_link = True

@admin.register(TypeformForm)
class TypeformFormAdmin(admin.ModelAdmin):
    list_display = ("title", "form_id", "created_at")
    search_fields = ("title", "form_id")
    actions = ["sync_form_definition"]
    inlines = [
        TypeformFieldInline, 
        TypeformWelcomeScreenInline, 
        TypeformThankYouScreenInline, 
        TypeformLogicInline
    ]

    def sync_form_definition(self, request, queryset):
        service = TypeformService()
        success_count = 0
        
        for form in queryset:
            try:
                # Use the service sync_form which delegates to model static method
                service.sync_form(form.form_id)
                success_count += 1
            except Exception as e:
                self.message_user(request, f"Error syncing form {form.form_id}: {str(e)}", level=messages.ERROR)
        
        if success_count > 0:
            self.message_user(request, f"Successfully synced {success_count} form(s).", level=messages.SUCCESS)
    sync_form_definition.short_description = "Sync Definition from Typeform API"


class TypeformPartnerMappingInline(admin.TabularInline):
    model = TypeformPartnerMapping
    extra = 1
    autocomplete_fields = ("partner",)
    fields = ("choice_ref", "choice_label", "partner")
    show_change_link = True

@admin.register(TypeformField)
class TypeformFieldAdmin(admin.ModelAdmin):
    list_display = ("title", "field_type", "field_id", "form")
    list_filter = ("form", "field_type")
    search_fields = ("title", "field_id", "ref")
    inlines = [TypeformPartnerMappingInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        
        # Handle deletions
        for obj in formset.deleted_objects:
            obj.delete()

        for instance in instances:
            if isinstance(instance, TypeformPartnerMapping):
                # Ensure form is set from the parent field
                # The inline is on TypeformField, so instance.field is naturally set by Django admin internals usually,
                # but let's be safe. 'instance.field' might already be set.
                # Actually, in an inline on TypeformField, the foreign key to TypeformField is handled automatically.
                # But 'instance.form' needs to be set.
                if hasattr(instance, 'field') and instance.field:
                    instance.form = instance.field.form
            instance.save()
        formset.save_m2m()

@admin.register(TypeformWelcomeScreen)
class TypeformWelcomeScreenAdmin(admin.ModelAdmin):
    list_display = ("title", "ref", "form")
    list_filter = ("form",)
    search_fields = ("title", "ref")

@admin.register(TypeformThankYouScreen)
class TypeformThankYouScreenAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "ref", "form")
    list_filter = ("form", "type")
    search_fields = ("title", "ref")

@admin.register(TypeformLogic)
class TypeformLogicAdmin(admin.ModelAdmin):
    list_display = ("ref", "type", "form")
    list_filter = ("form", "type")
    search_fields = ("ref",)

@admin.register(TypeformPartnerMapping)
class TypeformPartnerMappingAdmin(admin.ModelAdmin):
    list_display = ("choice_label", "partner", "field", "form")
    list_filter = ("form", "field")
    search_fields = ("choice_label", "choice_ref", "partner__company_name", "partner__email")
    autocomplete_fields = ("field", "partner", "form")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Optional customization e.g. filtering fields based on selected form
        return form


