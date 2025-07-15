from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FormSubmissionAPIView, stripe_webhook,
    OrderRetrieveView, notary_view, stripe_coupon
)

router = DefaultRouter()
router.register(r'orders', OrderRetrieveView, basename='order')

urlpatterns = [
    path("submit-order/", FormSubmissionAPIView.as_view(), name="submit-order"),
    path("submit-order/<str:stripe_session_id>/", FormSubmissionAPIView.as_view(), name="submit-order-with-session"),
    path("stripe-webhook/", stripe_webhook, name="stripe-webhook"),
    path("notary-view/", notary_view, name="notary-view"),
    path("stripe-coupon/<str:coupon_code>", stripe_coupon, name="stripe-coupon"),
    path('', include(router.urls)),
]

