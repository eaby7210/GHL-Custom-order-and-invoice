from django.urls import path
from .views import LatestTermsOfConditionsView

urlpatterns = [
    path('tos/latest/', LatestTermsOfConditionsView.as_view(), name='latest-tos'),
]
