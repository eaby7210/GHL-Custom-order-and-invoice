from django.shortcuts import render
from django.urls import path, include
from .views import ToltWebhookView

# Create your views here.


urlpatterns = [
    path('twebhook', ToltWebhookView.as_view(), name='tolt-webhook'),
    path('twebhook/', ToltWebhookView.as_view(), name='tolt-webhook'),

]
