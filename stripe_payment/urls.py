from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FormSubmissionAPIView, stripe_webhook,
    OrderRetrieveView, notary_view, stripe_coupon, test_email_template,
    OrderRetrieveView, notary_view, stripe_coupon, test_email_template,
    create_setup_intent, save_payment_method, set_default_card,
    retrieve_invoice_by_payment_intent
)

router = DefaultRouter()
router.register(r'orders', OrderRetrieveView, basename='order')

urlpatterns = [
    path("submit-order/", FormSubmissionAPIView.as_view(), name="submit-order"),
    path("submit-order/<str:stripe_session_id>/", FormSubmissionAPIView.as_view(), name="submit-order-with-session"),
    path("invoice/payment-intent/<str:payment_intent_id>/", retrieve_invoice_by_payment_intent, name="retrieve-invoice-by-pi"),
    path("stripe-webhook/", stripe_webhook, name="stripe-webhook"),
    path("notary-view/", notary_view, name="notary-view"),
    path("stripe-coupon/<str:coupon_code>", stripe_coupon, name="stripe-coupon"),
    path("test-email-template/<int:order_id>/", test_email_template, name="test-email-template"),
    path("create-setup-intent/", create_setup_intent, name="create-setup-intent"),
    path("save-payment-method/", save_payment_method, name="save-payment-method"),
    path("set-default-card/", set_default_card, name="set-default-card"),
    path('', include(router.urls)),
]

