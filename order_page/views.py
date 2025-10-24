# views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import TermsOfConditions, TypeformResponse, TypeformParser
from .serializers import TermsOfConditionsSerializer
from rest_framework import status
import json

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

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




@method_decorator(csrf_exempt, name='dispatch')
class TypeFormWebhook(APIView):

        def post(self, request):
 

            try:
                print(f'Raw payload {request.body}')
                try:
                    payload = request.data
                    # print(f'Recieved Payload {json.dumps(payload, indent=4)}')
                except json.JSONDecodeError:
                    return HttpResponseBadRequest("Invalid JSON payload")
                
                resp_obj = TypeformParser.save_webhook(payload)
                return Response({"status": "ok", "response_id": resp_obj.id}, status=status.HTTP_201_CREATED)



            except Exception as e:
                print("Typeform Webhook Error:", e)
                return JsonResponse({"error": str(e)}, status=400)


class NotaryCreationView(APIView):
    pass
