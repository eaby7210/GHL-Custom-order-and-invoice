
from django.db import models
from django.utils import timezone
from django.conf import settings
from oauth2_provider.models import Application
from django.utils.crypto import get_random_string

class WebhookEvent(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Event name, e.g. 'order.created'")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class WebhookEndpoint(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='webhook_endpoints')
    target_url = models.URLField(help_text="URL where the webhook will be delivered.")
    events = models.ManyToManyField(WebhookEvent, related_name='endpoints')
    secret = models.CharField(max_length=64, blank=True, help_text="Signing secret for verifying the payload")
    headers = models.JSONField(default=dict, blank=True, help_text="Custom JSON headers to include in the webhook request.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = get_random_string(50)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.application.name} - {self.target_url}"


class WebhookLog(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    )
    
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='logs')
    event = models.ForeignKey(WebhookEvent, on_delete=models.CASCADE, related_name='logs')
    payload = models.JSONField()
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.event} -> {self.endpoint} ({self.status})"

