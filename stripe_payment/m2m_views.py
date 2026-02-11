from rest_framework import generics, filters
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from .models import NotaryClientCompany, NotaryUser
from .serializer import NotaryClientCompanySerializer, NotaryUserSerializer
from core.permissions import IsM2MClient

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

from rest_framework import viewsets

class NotaryClientCompanyM2MViewSet(viewsets.ReadOnlyModelViewSet):
    """
    M2M ViewSet for NotaryClientCompany.
    Provides `list` and `retrieve` actions.
    """
    queryset = NotaryClientCompany.objects.all().order_by('-created_at')
    serializer_class = NotaryClientCompanySerializer
    permission_classes = [IsM2MClient]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['type', 'active', 'owner_id', 'parent_company_id']
    search_fields = ['company_name', 'stripe_customer_id', 'address']
    ordering_fields = ['created_at', 'updated_at', 'company_name']


class NotaryUserM2MViewSet(viewsets.ReadOnlyModelViewSet):
    """
    M2M ViewSet for NotaryUser.
    Provides `list` and `retrieve` actions.
    """
    queryset = NotaryUser.objects.all().order_by('-created_at')
    serializer_class = NotaryUserSerializer
    permission_classes = [IsM2MClient]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['type', 'disabled', 'is_admin', 'last_company']
    search_fields = ['email', 'first_name', 'last_name', 'name']
    ordering_fields = ['created_at', 'last_login_at', 'email']

