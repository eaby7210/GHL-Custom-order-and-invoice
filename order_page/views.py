# views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import TermsOfConditions, TypeformResponse, TypeformParser, TypeformAnswer
from .serializers import TermsOfConditionsSerializer
from rest_framework import status
import json
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from stripe_payment.services import NotaryDashServices
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
    
    def post(self, request):
        
        data = request.data
        print(f'Recieved payload {json.dumps(data, indent=4)}')
        email = data.get("email")
        time_threshold = timezone.now() - timedelta(seconds=30  )
        print(f"time treshold : {timezone.now() } - {timedelta(seconds=30  )} - {time_threshold}")
        if email:
            print(f"Got email {email}")
            email_answers = (
                TypeformAnswer.objects
                .select_related('response')  # optimize DB join
                .filter(
                    answer_type='email',
                    value_text=email,  
                    response__landed_at__gte=time_threshold
                )
                .order_by('-response__landed_at')
            )
            print(f"emailanswers {email_answers}")
            recent_responses = TypeformResponse.objects.filter(
                id__in=email_answers.values_list('response_id', flat=True)
            ).select_related('form').prefetch_related('answers__field')
            print(f" recennt responses {recent_responses}")
            recent_response = recent_responses.first()
            if recent_response:
                print(f"Recent res {recent_response}")
                client_payload = {
                    "company_name": recent_response.get_answer_by_title("Company"),
                      
                     
                    #   "address": {
                    #    "address_1": recent_response.get_answer_by_title("Address"),
                    #    "address_2": recent_response.get_answer_by_title("Address line 2"),
                    #     "state": recent_response.get_answer_by_title("State/Region/Province"),
                    #     "city": "city",
                    #    "zip": "123456"
                    #   }
                    }
                client_user_payload ={
                        "user": {
                            "password": "test1234",
                            "password_confirmation": "test1234",
                            "first_name": recent_response.get_answer_by_title("First name"),
                            "last_name": recent_response.get_answer_by_title("Last name"),
                            "email": recent_response.get_answer_by_title("Email"),
                            "attr":{
                                "phone":recent_response.get_answer_by_title("Phone number")
                            }
                        },
                        "email_credentials": True
                    }
                client_response = NotaryDashServices.create_client(client_payload)
                if client_response:
                    client_id = client_response.get("data",{}).get("id")
                    if client_id:
                        client_response = NotaryDashServices.create_client_user(client_id=client_id, user_data=client_user_payload)
                        if client_response:   
                            client_user_id = client_response.get("data").get("id")
                            lastcompany_id = client_response.get("data").get("last_company_id")
                            client_id = lastcompany_id if lastcompany_id else client_id
                            if client_user_id:
                                return Response(data={
                                    "message": "Account Created", "url" : f"https://go.investorbootz.com/?company_id={client_id}&client_id={client_user_id}"},status=status.HTTP_201_CREATED)
                return Response(data={"message":"Recieved paylaod"},status=status.HTTP_201_CREATED)
            else:
                 return Response(data={"message":"No Content"},status=status.HTTP_204_NO_CONTENT)
            
        return Response(data={"message":"Error"},status=status.HTTP_400_BAD_REQUEST)
        # return Response(data={"message":"Recieved paylaod"},status=status.HTTP_204_NO_CONTENT)
