# views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import TermsOfConditions
from .serializers import TermsOfConditionsSerializer

class LatestTermsOfConditionsView(APIView):
    """
    Returns the latest Terms of Conditions (by updated_at).
    """

    def get(self, request, *args, **kwargs):
        latest_tos = TermsOfConditions.objects.order_by('-updated_at').first()
        if not latest_tos:
            return Response({"detail": "No Terms of Conditions found."}, status=404)
        
        serializer = TermsOfConditionsSerializer(latest_tos)
        return Response(serializer.data)
