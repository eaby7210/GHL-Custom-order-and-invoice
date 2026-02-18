from django.contrib import admin, messages
from django.db.models import Sum
from django.utils.html import format_html
from .models import (
    NotaryUser, NotaryClientCompany, NotaryCompanyGroup,
    Order, Bundle, BundleOption, BundleModalOption,
    ALaCarteService, ALaCarteItem, ALaCarteOption, ALaCarteSubMenuItem,
    ALaCarteItemModalOption, ALaCarteItemDisclosure,
    StripeWebhookEventLog
)
from rangefilter.filters import DateTimeRangeFilter


@admin.register(NotaryClientCompany)
class NotaryClientCompanyAdmin(admin.ModelAdmin):
    """Admin config for NotaryClientCompany with search and filtering."""

    class NotaryUserInline(admin.TabularInline):
        model = NotaryUser
        fields = ['email', 'full_name', 'is_admin', 'type']
        readonly_fields = ['email', 'full_name', 'type']
        extra = 0
        show_change_link = True
        can_delete = False
        fk_name = 'last_company'

        def full_name(self, obj):
            if obj.first_name or obj.last_name:
                return f"{obj.first_name} {obj.last_name}".strip()
            return obj.name or '-'
        full_name.short_description = 'Name'

    inlines = [NotaryUserInline]

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
        'stripe_customer_id',
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
        ('Payment Information', {
            'fields': ('stripe_customer_id', 'stripe_default_payment_method'),
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
        'last_company_display',
        'is_admin',
        'created_at',
    ]

    list_editable = ['is_admin']

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
        'is_admin',
    ]

    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'last_login_at',
        'deleted_at',
    ]

    raw_id_fields = ['last_company']
    filter_horizontal = ['signed_terms']

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
            'fields': ('disabled', 'type', 'is_admin')
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
        ('Terms & Legal', {
            'fields': ('signed_terms', 'last_signed_at'),
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

    def last_company_display(self, obj):
        """Display company name with ID."""
        if obj.last_company:
            return f"{obj.last_company} ({obj.last_company.id})"
        return '-'
    last_company_display.short_description = 'Last Company'
    last_company_display.admin_order_field = 'last_company'

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


@admin.register(NotaryCompanyGroup)
class NotaryCompanyGroupAdmin(admin.ModelAdmin):
    """Admin config for NotaryCompanyGroup."""
    
    list_display = ['id', 'name', 'company_count']
    search_fields = ['name', 'companies__company_name']
    filter_horizontal = ['companies']
    
    def company_count(self, obj):
        return obj.companies.count()
    company_count.short_description = 'Number of Companies'


@admin.register(StripeWebhookEventLog)
class StripeWebhookEventLogAdmin(admin.ModelAdmin):
    list_display = ['event_id', 'event_type', 'processed', 'created_at']
    list_filter = ['processed', 'event_type', 'created_at']
    search_fields = ['event_id', 'event_type', 'error_message']
    readonly_fields = [field.name for field in StripeWebhookEventLog._meta.fields]
    
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class BundleOptionInline(admin.TabularInline):
    model = BundleOption
    extra = 0
    readonly_fields = [field.name for field in BundleOption._meta.fields]
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class BundleModalOptionInline(admin.TabularInline):
    model = BundleModalOption
    extra = 0
    readonly_fields = [field.name for field in BundleModalOption._meta.fields]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'price']
    search_fields = ['name', 'order__id']
    inlines = [BundleOptionInline, BundleModalOptionInline]
    
    def has_add_permission(self, request):
        return False
        
    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class BundleInline(admin.TabularInline):
    model = Bundle
    extra = 0
    fields = ['name', 'description', 'base_price', 'price']
    readonly_fields = ['name', 'description', 'base_price', 'price']
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ALaCarteOptionInline(admin.TabularInline):
    model = ALaCarteOption
    extra = 0
    readonly_fields = [field.name for field in ALaCarteOption._meta.fields]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ALaCarteSubMenuItemInline(admin.TabularInline):
    model = ALaCarteSubMenuItem
    extra = 0
    readonly_fields = [field.name for field in ALaCarteSubMenuItem._meta.fields]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


class ALaCarteItemModalOptionInline(admin.TabularInline):
    model = ALaCarteItemModalOption
    extra = 0
    readonly_fields = [field.name for field in ALaCarteItemModalOption._meta.fields]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ALaCarteItemDisclosureInline(admin.TabularInline):
    model = ALaCarteItemDisclosure
    extra = 0
    readonly_fields = [field.name for field in ALaCarteItemDisclosure._meta.fields]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ALaCarteItem)
class ALaCarteItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'service', 'item_id', 'price']
    list_filter = ['service__service_id']
    search_fields = ['title', 'item_id', 'service__title']
    inlines = [
        ALaCarteOptionInline, 
        ALaCarteSubMenuItemInline, 
        ALaCarteItemModalOptionInline,
        ALaCarteItemDisclosureInline
    ]
    
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ALaCarteItemInline(admin.TabularInline):
    model = ALaCarteItem
    extra = 0
    fields = ['title', 'price', 'item_id']
    readonly_fields = ['title', 'price', 'item_id']
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ALaCarteService)
class ALaCarteServiceAdmin(admin.ModelAdmin):
    list_display = ['title', 'service_id', 'order']
    list_filter = ['service_id']
    search_fields = ['title', 'form_title', 'service_id']
    inlines = [ALaCarteItemInline]
    
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ALaCarteServiceInline(admin.TabularInline):
    model = ALaCarteService
    extra = 0
    fields = ['title', 'service_id']
    readonly_fields = ['title', 'service_id']
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'company_name', 'service_type', 'total_price','order_protection_price', 
        'created_at', 'processing_status', 'user_id'
    ]
    list_filter = [
        'service_type', 
        'unit_type', 
        'processing_status', 
        'occupancy_status',
        'order_protection',
        ('created_at', DateTimeRangeFilter),
        ('accepted_at', DateTimeRangeFilter),
        ('preferred_datetime', DateTimeRangeFilter),
    ]
    search_fields = [
        'id', 'user_id', 'company_id', 'stripe_session_id', 
        'stripe_intent_id', 'address', 'city', 'contact_email'
    ]
    readonly_fields = [field.name for field in Order._meta.fields]
    inlines = [BundleInline, ALaCarteServiceInline]
    
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
            
        metrics = qs.aggregate(
            total_sum=Sum('total_price'),
            protection_sum=Sum('order_protection_price')
        )
        
        total = metrics['total_sum'] or 0
        protection = metrics['protection_sum'] or 0
        
        msg = format_html(
            '<strong>Analysis of Filtered Orders:</strong> '
            'Total Price: ${} | '
            'Order Protection: ${}',
            total, protection
        )
        self.message_user(request, msg, messages.INFO)
        
        return response

