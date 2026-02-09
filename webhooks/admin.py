
from django.contrib import admin
from .models import WebhookEvent, WebhookEndpoint, WebhookLog

@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('name', 'description', 'updated_at')
    def has_add_permission(self, request):
        return False

@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ('application', 'target_url', 'is_active', 'updated_at')
    list_filter = ('is_active', 'events')
    search_fields = ('application__name', 'target_url')
    readonly_fields = ('secret',)

@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ('event', 'endpoint', 'status', 'response_status', 'created_at')
    list_filter = ('status', 'event', 'created_at')
    search_fields = ('endpoint__target_url', 'response_body', 'error_message')
    readonly_fields = ('event', 'endpoint', 'payload', 'response_status', 'response_body', 'status', 'error_message', 'created_at')
    
    def has_add_permission(self, request):
        return False

