import json, time, base64, logging, typing
from typing import TYPE_CHECKING, Optional, cast, Type
from datetime import datetime
from django.apps import apps
from django.db import transaction
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, is_naive
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from datetime import datetime, timezone, timedelta
from tolt.management.commands.pull_partners import Command as PullPartnersCommand
from tolt.services import ToltService
from tolt.models import Link, Partner, Customer

# Create your views here.
@method_decorator(csrf_exempt, name='dispatch')
class ToltWebhookView(APIView):
    
    def post(self, request):
   
        data = request.data
        print("Received webhook data:", json.dumps(data, indent=2))
        w_type = data.get("type")
        if w_type in ["partner.created", "partner.updated"]:
            try:
                p_data = data.get("data", {})
                print(f"Processing partner webhook: {w_type}, ID: {p_data.get('id')}")
                obj, created = Partner.create_or_update_from_api(p_data)
                return Response(status=status.HTTP_200_OK)
            except Exception as e:
                print(f"Error processing partner webhook: {e}")
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if w_type in ("customer.created", "customer.updated"):
            try:
                obj, created = Customer.from_webhook(data)

                return Response(
                    {
                        "status": "success",
                        "customer_id": obj.id,
                        "created": created,
                    },
                    status=status.HTTP_200_OK
                )
            except Exception as exc:
                print("❌ Webhook customer sync failed:", exc)
                return Response(
                    {"error": str(exc)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        elif w_type in ["link.created", "link.updated"]:
           
            partner_id = data.get("data", {}).get("partner_id")
            partner= Partner.objects.filter(id=partner_id).first()
            if not partner:
                p_data = ToltService.fetch_partner(partner_id)
                if data:
                    print(f"Fetched partner data from Tolt: {p_data.get('data', {}).get('id')}")
                    partner, _ = Partner.create_or_update_from_api(p_data.get("data", {}))
            else:
                print(f"Found existing partner {partner.id} in DB")
            link, created, event_type = Link.create_or_update_from_webhook(data)
            print(f"Processed Link {link.id}, created: {created}, event_type: {event_type}")
     
        return Response(status=status.HTTP_200_OK)
    