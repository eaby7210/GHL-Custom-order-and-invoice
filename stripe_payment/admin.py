from django.contrib import admin
from django.utils.html import format_html
from .models import NotaryUser, NotaryClientCompany


@admin.register(NotaryClientCompany)
class NotaryClientCompanyAdmin(admin.ModelAdmin):
    """Admin config for NotaryClientCompany with search and filtering."""

    list_display = [
        'id',
        'company_name',
        'type',
        'parent_company_name',
        'owner_id',
        'parent_company_id',
        'active',
        'is_deleted',
        'created_at',
    ]

    list_display_links = ['id', 'company_name']

    search_fields = [
        'company_name',
        'parent_company_name',
        'id',
        'owner_id',
        'parent_company_id',
        'type',
    ]

    list_filter = [
        'active',
        'type',
        ('deleted_at', admin.EmptyFieldListFilter),
        ('created_at', admin.DateFieldListFilter),
        ('updated_at', admin.DateFieldListFilter),
    ]

    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'deleted_at',
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'company_name', 'type', 'active')
        }),
        ('Company Relationships', {
            'fields': (
                'owner_id',
                'parent_company_id',
                'parent_company_name'
            )
        }),
        ('Additional Data', {
            'fields': ('attr', 'address'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',)
        }),
    )

    date_hierarchy = 'created_at'

    list_per_page = 25
    list_max_show_all = 100

    ordering = ['-created_at']

    def is_deleted(self, obj):
        """Display whether the company is deleted."""
        if obj.deleted_at:
            return format_html(
                '<span style="color: red;">✓ Deleted</span>'
            )
        return format_html('<span style="color: green;">Active</span>')
    is_deleted.short_description = 'Status'


@admin.register(NotaryUser)
class NotaryUserAdmin(admin.ModelAdmin):
    """Admin config for NotaryUser with search and filtering."""

    list_display = [
        'id',
        'email',
        'full_name',
        'type',
        'last_company',
        'disabled',
        'email_unverified',
        'pivot_active',
        'last_login_at',
        'created_at',
    ]

    list_display_links = ['id', 'email']

    search_fields = [
        'email',
        'first_name',
        'last_name',
        'name',
        'id',
        'last_ip',
        'last_company__company_name',
        'pivot_company',
    ]

    list_filter = [
        'disabled',
        'email_unverified',
        'type',
        'pivot_active',
        'last_company',
        ('deleted_at', admin.EmptyFieldListFilter),
        ('last_login_at', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter),
        ('updated_at', admin.DateFieldListFilter),
        'country_code',
    ]

    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'last_login_at',
        'deleted_at',
    ]

    raw_id_fields = ['last_company']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'id',
                'email',
                'email_unverified',
                'name',
                'first_name',
                'last_name'
            )
        }),
        ('Account Status', {
            'fields': ('disabled', 'type', 'active_status')
        }),
        ('Company & Roles', {
            'fields': (
                'last_company',
                'has_roles',
                'pivot_active',
                'pivot_role_id',
                'pivot_company'
            )
        }),
        ('Profile', {
            'fields': ('photo_url', 'country_code', 'tz'),
            'classes': ('collapse',)
        }),
        ('Activity', {
            'fields': ('last_login_at', 'last_ip'),
            'classes': ('collapse',)
        }),
        ('Additional Data', {
            'fields': ('attr',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',)
        }),
    )

    date_hierarchy = 'created_at'

    list_per_page = 25
    list_max_show_all = 100

    ordering = ['-created_at']

    def full_name(self, obj):
        """Display full name with formatting."""
        if obj.first_name or obj.last_name:
            return f"{obj.first_name} {obj.last_name}".strip()
        return obj.name or '-'
    full_name.short_description = 'Full Name'
    full_name.admin_order_field = 'first_name'

    def active_status(self, obj):
        """Display active status based on deleted_at."""
        if obj.deleted_at:
            return format_html(
                '<span style="color: red;">Deleted</span>'
            )
        return format_html('<span style="color: green;">Active</span>')
    active_status.short_description = 'Account Status'

    def get_queryset(self, request):
        """Optimize queryset with select_related for foreign keys."""
        qs = super().get_queryset(request)
        return qs.select_related('last_company')
