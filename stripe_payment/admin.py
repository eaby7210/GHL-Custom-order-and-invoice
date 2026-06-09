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
    readonly_fields = [field.name for field in Bundle._meta.fields]
    
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
    readonly_fields = [field.name for field in ALaCarteItem._meta.fields]
    
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
    readonly_fields = [field.name for field in ALaCarteService._meta.fields]
    
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
        'id', 'user_id', 'company_id', 'owner_id', 'client_team_id',
        'notary_order_id', 'stripe_session_id', 'stripe_intent_id',
        'invoice_id', 'location_id', 'contact_email'
    ]
    readonly_fields = [field.name for field in Order._meta.fields]
    inlines = [BundleInline, ALaCarteServiceInline]
    actions = ['process_order_action']
    
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def process_order_action(self, request, queryset):
        from stripe_payment.views import process_order, PROCESS_ORDER_RETRYABLE
        import stripe
        from django.conf import settings
        stripe.api_key = settings.STRIPE_SECRET_KEY

        processed_count = 0
        skipped_count = 0
        error_count = 0

        for order in queryset:
            # Check if order has Stripe IDs but no NotaryDash order ID
            has_stripe_ids = bool(order.stripe_session_id or order.stripe_intent_id or order.invoice_id)
            if order.notary_order_id:
                self.message_user(
                    request,
                    f"Order {order.id} already has a NotaryDash Order ID ({order.notary_order_id}). Skipped.",
                    messages.WARNING
                )
                skipped_count += 1
                continue

            if not has_stripe_ids:
                self.message_user(
                    request,
                    f"Order {order.id} does not have any associated Stripe IDs (Session ID, Intent ID, or Invoice ID). Skipped.",
                    messages.WARNING
                )
                skipped_count += 1
                continue

            # Attempt to find/fetch event object
            event = None
            
            # 1. Look up locally in event logs
            if order.stripe_session_id:
                log = StripeWebhookEventLog.objects.filter(
                    event_type="checkout.session.completed",
                    event_data__data__object__id=order.stripe_session_id
                ).first()
                if log:
                    event = log.event_data

            if not event and order.stripe_intent_id:
                log = StripeWebhookEventLog.objects.filter(
                    event_type="payment_intent.succeeded",
                    event_data__data__object__id=order.stripe_intent_id
                ).first()
                if log:
                    event = log.event_data

            # 2. Retrieve from Stripe API directly
            if not event:
                if order.stripe_session_id:
                    try:
                        session = stripe.checkout.Session.retrieve(order.stripe_session_id)
                        event = {
                            "id": f"evt_manual_session_{order.id}",
                            "type": "checkout.session.completed",
                            "data": {"object": session}
                        }
                    except Exception as e:
                        print(f"Error retrieving Stripe Session for Order {order.id}: {e}")

                if not event and order.stripe_intent_id:
                    try:
                        intent = stripe.PaymentIntent.retrieve(order.stripe_intent_id)
                        event = {
                            "id": f"evt_manual_pi_{order.id}",
                            "type": "payment_intent.succeeded",
                            "data": {"object": intent}
                        }
                    except Exception as e:
                        print(f"Error retrieving Stripe PaymentIntent for Order {order.id}: {e}")

                if not event and order.invoice_id:
                    try:
                        invoice = stripe.Invoice.retrieve(order.invoice_id)
                        pi_id = getattr(invoice, "payment_intent", None)
                        if pi_id:
                            intent = stripe.PaymentIntent.retrieve(pi_id)
                            event = {
                                "id": f"evt_manual_pi_{order.id}",
                                "type": "payment_intent.succeeded",
                                "data": {"object": intent}
                            }
                    except Exception as e:
                        print(f"Error retrieving Stripe Invoice for Order {order.id}: {e}")

            if not event:
                self.message_user(
                    request,
                    f"Could not build or retrieve Stripe event object for Order {order.id}. Details: "
                    f"Session ID: {order.stripe_session_id or 'None'}, "
                    f"Intent ID: {order.stripe_intent_id or 'None'}, "
                    f"Invoice ID: {order.invoice_id or 'None'}",
                    messages.ERROR
                )
                error_count += 1
                continue

            # Process order
            try:
                # We need to temporarily set the status to 'pending' or 'failed' to pass the idempotency check
                original_status = order.processing_status
                if original_status not in ["pending", "failed"]:
                    order.processing_status = "pending"
                    order.save(update_fields=["processing_status"])

                res = process_order(event, order)

                if res is True:
                    order.refresh_from_db()
                    order.processing_status = "completed"
                    order.save(update_fields=["processing_status"])
                    
                    # Revoke any scheduled/active/reserved Celery tasks for this order
                    from stripe_payment.tasks import revoke_order_fulfillment_tasks
                    revoked_ids = revoke_order_fulfillment_tasks(order.id)
                    
                    msg = f"✅ Order {order.id} processed successfully! NotaryDash Order ID: {order.notary_order_id}"
                    if revoked_ids:
                        msg += f" (Revoked {len(revoked_ids)} pending Celery task(s): {', '.join(revoked_ids)})"
                    self.message_user(
                        request,
                        msg,
                        messages.SUCCESS
                    )
                    processed_count += 1
                else:
                    # Restore original status if failed
                    order.processing_status = original_status
                    order.save(update_fields=["processing_status"])
                    self.message_user(
                        request,
                        f"❌ Order {order.id} fulfillment failed. NotaryDash returned failure/retryable response.",
                        messages.ERROR
                    )
                    error_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"❌ Unexpected exception during process_order for Order {order.id}: {e}",
                    messages.ERROR
                )
                error_count += 1

        self.message_user(
            request,
            f"Bulk processing summary: {processed_count} succeeded, {skipped_count} skipped, {error_count} failed.",
            messages.INFO
        )

    process_order_action.short_description = "Process Order (Create NotaryDash Order)"

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

