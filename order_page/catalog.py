"""
Shared catalog accessor for order_page.ServiceVariance.

Single cache-or-DB choke point used by both ServiceLookupView (page load)
and order_page.pricing.reprice_order (form submission), so a submit doesn't
have to re-query the catalog if the page load already warmed the cache.
"""
from django.core.cache import cache
from django.shortcuts import get_object_or_404

from .models import ServiceVariance
from .serializers import ServiceVarianceSerializer

# Redis TTL evicts the key natively at this age — no separate cleanup task needed.
SERVICE_LOOKUP_CACHE_SECONDS = 60 * 60


def service_lookup_cache_key(company_id: str) -> str:
    return f"order_page:service_lookup:v1:{company_id.strip()}"


def get_service_variance_payload(company_id: str):
    """
    Resolve + serialize the active ServiceVariance for a company, falling
    back to the default variance the same way ServiceLookupView does.
    company_id == "default" (case-insensitive) resolves the default variance
    directly. Returns None if nothing resolves; raises Http404 if company_id
    doesn't match a NotaryClientCompany at all.
    """
    if not company_id:
        return None

    cache_key = service_lookup_cache_key(company_id)
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        return cached_payload

    if company_id.lower() == "default":
        variance = ServiceVariance.get_default()
    else:
        from stripe_payment.models import NotaryClientCompany

        client = get_object_or_404(NotaryClientCompany, id=company_id)
        variance = (
            ServiceVariance.objects.filter(clients=client, is_active=True)
            .prefetch_related("bundle_group__bundles", "service_category__services")
            .first()
        )
        if not variance:
            variance = ServiceVariance.get_default()

    if not variance:
        return None

    data = ServiceVarianceSerializer(variance).data
    cache.set(cache_key, data, SERVICE_LOOKUP_CACHE_SECONDS)
    return data
