import requests, json,time
import requests
from django.utils.timezone import now
from datetime import timedelta
from django.utils.timezone import is_naive, make_aware


from django.conf import settings
from django.db import transaction
import requests 
from datetime import datetime
from typing import Any
import json, os
from django.utils.dateparse import parse_datetime
from django.contrib.contenttypes.models import ContentType
from django.apps import apps


class ToltService:
    BASE_URL = "https://api.tolt.com"
    API_KEY = settings.TOLT_KEY
    PROGRAM_ID = 'prg_NhKk8aX3SgT8FQzdzrdNbexg'

    @staticmethod
    def get_headers() -> dict:
        return {
            "Authorization": f"Bearer {ToltService.API_KEY}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def fetch_partners(start_after, end_before, per_page: int = 100) -> Any:
        url = f"{ToltService.BASE_URL}/v1/partners/"
        params = { 
                  "limit": per_page,
                'program_id': ToltService.PROGRAM_ID,
                  }
        if start_after :
            params["start_after"] = start_after
        if end_before :
            params["end_before"] = end_before

        response = requests.get(url, headers=ToltService.get_headers(), params=params)
        # print(response.text)
        # response.raise_for_status()
        return response.json()


    @staticmethod
    def fetch_partner(partner_id: int) -> Any:
        url = f"{ToltService.BASE_URL}/v1/partners/{partner_id}"
        response = requests.get(url, headers=ToltService.get_headers())
        if response.status_code != 200:
            print(f"Error fetching partner {partner_id} from Tolt: {response.status_code} - {response.text}")
            
        return response.json()

    @staticmethod
    def fetch_customers(starting_after: str|None = None, per_page: int = 100) -> Any:
        url = f"{ToltService.BASE_URL}/v1/customers"
        params = {
            "limit": per_page,
            "program_id": ToltService.PROGRAM_ID,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = requests.get(url, headers=ToltService.get_headers(), params=params)

        if response.status_code != 200:
            print(
                f"Error fetching customers from Tolt: "
                f"{response.status_code} - {response.text}"
            )

        return response.json()

    
    @staticmethod
    def fetch_links(start_after=None, end_before=None, per_page: int = 100) -> Any:
        url = f"{ToltService.BASE_URL}/v1/links"
        params = { "limit": per_page,
                  "program_id": ToltService.PROGRAM_ID
                  }
        if start_after:
            params["start_after"] = start_after
        if end_before:
            params["end_before"] = end_before
            
        response = requests.get(url, headers=ToltService.get_headers(), params=params)
        response.raise_for_status()
        return response.json()



    

        """
        Create a Tolt transaction
        Docs: POST /v1/transactions
        Example payload:
        {
            "amount": 9999,
            "customer_id": "...",
            "billing_type": "subscription",
            "charge_id": "...",
            "product_id": "...",
            "product_name": "...",
            "interval": "month",
            "created_at": "2025-01-15T14:30:00.000Z"
        }
        """

        url = f"{ToltService.BASE_URL}/v1/transactions"

        try:
            response = requests.post(
                url,
                headers=ToltService.get_headers(),
                data=json.dumps(payload),
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"Request failed: {e}"
            }

        if response.status_code not in (200, 201):
            return {
                "success": False,
                "status_code": response.status_code,
                "error": response.text,
            }

        return response.json()