# views.py
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    TermsOfConditions, TypeformResponse, TypeformParser, TypeformAnswer,
    ServiceVariance, NotaryClientCompany
    )

from .serializers import TermsOfConditionsSerializer, ServiceVarianceSerializer
from rest_framework import status
import json
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from stripe_payment.services import NotaryDashServices
from stripe_payment.models import NotaryClientCompany, NotaryUser
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
                print(f'Raw payload {json.dumps(request.data, indent=4)}')
                try:
                    payload = request.data
                    # print(f'Recieved Payload {json.dumps(payload, indent=4)}')
                except json.JSONDecodeError:
                    return HttpResponseBadRequest("Invalid JSON payload")
                
                resp_obj = TypeformParser.save_webhook(payload)
                return Response({"status": "ok", "response_id": resp_obj.id}, status=status.HTTP_201_CREATED) #type:ignore



            except Exception as e:
                print("Typeform Webhook Error:", e)
                return JsonResponse({"error": str(e)}, status=400)



class NotaryCreationView(APIView):
    """
    Creates a client + client user on NotaryDash and stores them locally.
    """

    def post(self, request):
        data = request.data
        print(f"Received payload: {json.dumps(data, indent=4)}")
        email = data.get("email")

        # Validate email & time threshold
        time_threshold = timezone.now() - timedelta(minutes=1)
        if not email:
            return Response({"message": "Missing email"}, status=status.HTTP_400_BAD_REQUEST)

        # 1️⃣ Get recent Typeform response for this email
        email_answers = (
            TypeformAnswer.objects
            .select_related('response')
            .filter(
                answer_type='email',
                value_text=email,
                response__submitted_at__gte=time_threshold
            )
            .order_by('-response__submitted_at')
        )

        recent_responses = TypeformResponse.objects.filter(
            id__in=email_answers.values_list('response_id', flat=True)
        ).select_related('form').prefetch_related('answers__field')

        recent_response = recent_responses.first()
        if not recent_response:
            return Response({"message": "No recent Typeform response found"}, status=status.HTTP_204_NO_CONTENT)

        print(f"Using recent response: {recent_response.id}") #type:ignore

        # 2️⃣ Build payloads
        client_payload = {
            "company_name": recent_response.get_answer_by_title("Company"),
        }

        client_user_payload = {
            "user": {
                "password": "test1234",
                "password_confirmation": "test1234",
                "first_name": recent_response.get_answer_by_title("First name"),
                "last_name": recent_response.get_answer_by_title("Last name"),
                "email": recent_response.get_answer_by_title("Email"),
                "attr": {
                    "phone": recent_response.get_answer_by_title("Phone number")
                },
            },
            "email_credentials": True,
        }

        # 3️⃣ Create client in NotaryDash
        client_response = NotaryDashServices.create_client(client_payload)
        if not client_response:
            return Response({"message": "Failed to create client"}, status=status.HTTP_400_BAD_REQUEST)

        client_data = client_response.get("data", {})
        client_id = client_data.get("id")

        if not client_id:
            return Response({"message": "No client ID returned"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Save NotaryClientCompany locally
        client_obj, _ = NotaryClientCompany.objects.update_or_create(
            id=client_id,
            defaults={
                "owner_id": client_data.get("owner_id"),
                "parent_company_id": client_data.get("parent_company_id"),
                "type": client_data.get("type"),
                "company_name": client_data.get("company_name"),
                "parent_company_name": client_data.get("parent_company_name"),
                "attr": client_data.get("attr", {}),
                "address": client_data.get("address", {}),
                "deleted_at": client_data.get("deleted_at"),
                "created_at": client_data.get("created_at"),
                "updated_at": client_data.get("updated_at"),
                "active": client_data.get("active", True),
            }
        )

        print(f"✅ Saved NotaryClientCompany: {client_obj}")

        # 4️⃣ Create client user
        user_response = NotaryDashServices.create_client_user(
            client_id=client_id, user_data=client_user_payload
        )

        if not user_response:
            return Response({"message": "Failed to create client user"}, status=status.HTTP_400_BAD_REQUEST)

        user_data = user_response.get("data", {})
        user_id = user_data.get("id")
        last_company_id = user_data.get("last_company_id")
        company_id = last_company_id if last_company_id else client_id

        if user_id:
            # ✅ Save NotaryUser locally
            user_obj, _ = NotaryUser.objects.update_or_create(
                id=user_id,
                defaults={
                    "first_name": user_data.get("first_name"),
                    "last_name": user_data.get("last_name"),
                    "email": user_data.get("email"),
                    "photo_url": user_data.get("photo_url"),
                    "country_code": user_data.get("country_code"),
                    "tz": user_data.get("tz"),
                    "attr": user_data.get("attr", {}),
                    "last_login_at": user_data.get("last_login_at"),
                    "last_ip": user_data.get("last_ip"),
                    "last_company_id": user_data.get("last_company_id"),
                    "email_unverified": user_data.get("email_unverified"),
                    "disabled": user_data.get("disabled"),
                    "deleted_at": user_data.get("deleted_at"),
                    "created_at": user_data.get("created_at"),
                    "updated_at": user_data.get("updated_at"),
                    "type": user_data.get("type"),
                }
            )

            print(f"✅ Saved NotaryUser: {user_obj}")

            # 5️⃣ Return success response
            return Response(
                {
                    "message": "Account Created",
                    "url": f"https://go.investorbootz.com/?company_id={company_id}&client_id={user_id}",
                },
                status=status.HTTP_201_CREATED,
            )

        return Response({"message": "User creation failed"}, status=status.HTTP_400_BAD_REQUEST)




class ServiceLookupView(APIView):
    """
    Returns the detailed service + bundle structure for a given company.
    If company_id = 'default', returns the active default variance.
    Otherwise:
      - Attempts to find a variance assigned to the company.
      - Falls back to default if none exists.
    """

    def get(self, request, company_id: str):
        try:
            # Case 1: If explicitly requesting the default
            if company_id.lower() == "default":
                variance = ServiceVariance.get_default()
                if not variance:
                    return Response(
                        {"detail": "No default active service variance found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            else:
                # Case 2: Try to find company-specific variance
                client = get_object_or_404(NotaryClientCompany, id=company_id)

                variance = (
                    ServiceVariance.objects.filter(clients=client, is_active=True)
                    .prefetch_related("bundle_group__bundles", "service_category__services")
                    .first()
                )

                # Fallback to default
                if not variance:
                    variance = ServiceVariance.get_default()
                    if not variance:
                        return Response(
                            {"detail": "No active variance found for client or default."},
                            status=status.HTTP_404_NOT_FOUND,
                        )

            # Serialize result
            serializer = ServiceVarianceSerializer(variance)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
