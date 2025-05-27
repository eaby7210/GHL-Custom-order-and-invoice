from django.urls import path
from .views import FormSubmissionAPIView, stripe_webhook

urlpatterns = [
    path("submit-order/", FormSubmissionAPIView.as_view(), name="submit-order"),
    path("stripe-webhook/", stripe_webhook, name="stripe-webhook"),
]