from django.urls import path
from .views import LatestTermsOfConditionsView, TypeFormWebhook, NotaryCreationView

urlpatterns = [
    path('tos/latest/', LatestTermsOfConditionsView.as_view(), name='latest-tos'),
    path('entry-response/', TypeFormWebhook.as_view(), name='typeform-webhook'),
    path('redirection/', NotaryCreationView.as_view(), name='notary-creation-view')
]
