from django.urls import path
from .views import (LatestTermsOfConditionsView, TypeFormWebhook,
                    NotaryCreationView, ServiceLookupView, GooglePlacesAutocompleteView,
                    GooglePlaceDetailsView)

urlpatterns = [
    path('tos/latest/', LatestTermsOfConditionsView.as_view(), name='latest-tos'),
    path('entry-response/', TypeFormWebhook.as_view(), name='typeform-webhook'),
    path('redirection/', NotaryCreationView.as_view(), name='notary-creation-view'),
     path("services/<str:company_id>/", ServiceLookupView.as_view(), name="service-lookup"),
    path("places/autocomplete/", GooglePlacesAutocompleteView.as_view(), name="places-autocomplete"),
    path("places/details/", GooglePlaceDetailsView.as_view(), name="places-details"),
]
