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
    def fetch_customers(
        starting_after: str | None = None,
        per_page: int = 100,
        *,
        program_id: str | None = None,
        partner_id: str | None = None,
        search: str | None = None,
        order: str | None = None,
        status: str | None = None,
        expand: list[str] | None = None,
        created_gte: str | None = None,
        created_lte: str | None = None,
        limit: int | None = None,
        ending_before: str | None = None,
    ) -> Any:
        """
        GET /v1/customers — list or search customers.

        Query parameters (passed to the API):

        - program_id (str, required by API): Program to list from; defaults to
          ``ToltService.PROGRAM_ID`` when omitted.
        - partner_id (str, optional): Only customers referred by this partner.
        - search (str, optional): Filter by email (partial matches supported).
        - order (str, optional): ``asc`` or ``desc`` by ``created_at`` (default API: desc).
        - status (str, optional): ``lead``, ``trialing``, ``active``, or ``canceled``.
        - expand (list[str], optional): Related objects to include; each entry
          should be ``partner`` or ``program`` (sent as ``expand[]=...``).
        - created_gte (str, optional): ISO date — customers created on/after this time.
        - created_lte (str, optional): ISO date — customers created on/before this time.
        - limit (int, optional): Page size (default API 10, max 100). Overrides
          ``per_page`` when set.
        - starting_after (str, optional): Pagination cursor (customer id).
        - ending_before (str, optional): Pagination cursor for previous page.

        Positional args for backward compatibility:

        - ``starting_after`` / ``per_page`` behave as before; ``per_page`` sets
          ``limit`` unless ``limit`` is passed explicitly.
        """
        url = f"{ToltService.BASE_URL}/v1/customers"
        limit_val = limit if limit is not None else per_page

        params: dict[str, Any] = {
            "program_id": program_id or ToltService.PROGRAM_ID,
            "limit": limit_val,
        }
        if starting_after:
            params["starting_after"] = starting_after
        if ending_before:
            params["ending_before"] = ending_before
        if partner_id:
            params["partner_id"] = partner_id
        if search is not None and search != "":
            params["search"] = search
        if order:
            params["order"] = order
        if status:
            params["status"] = status
        if created_gte:
            params["created_gte"] = created_gte
        if created_lte:
            params["created_lte"] = created_lte

        request_params: Any
        if expand:
            request_params = [(k, v) for k, v in params.items()]
            for item in expand:
                request_params.append(("expand[]", item))
        else:
            request_params = params

        response = requests.get(
            url,
            headers=ToltService.get_headers(),
            params=request_params,
        )

        if response.status_code != 200:
            print(
                f"Error fetching customers from Tolt: "
                f"{response.status_code} - {response.text}"
            )

        return response.json()

    @staticmethod
    def customers_from_list_response(payload: dict) -> list[Any]:
        """
        Extract the customer objects array from GET /v1/customers JSON, e.g.::

            {"success": true, "data": {"data": [ {...}, ... ]}}
        """
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, list):
                return inner
        if isinstance(data, list):
            return data
        return []

    @staticmethod
    def find_customer_by_email(
        email: str,
        *,
        partner_id: str | None = None,
        limit: int = 100,
    ) -> dict | None:
        """
        Search Tolt customers by ``search`` (email, partial API match) and return
        the first record whose ``email`` matches exactly (case-insensitive).
        If ``partner_id`` is set, the record must also have the same ``partner_id``.
        Returns ``None`` if the request fails, is unsuccessful, or no row matches.
        """
        raw = ToltService.fetch_customers(
            search=email,
            limit=min(limit, 100),
            partner_id=partner_id,
        )
        if not raw.get("success"):
            return None
        rows = ToltService.customers_from_list_response(raw)
        target = (email or "").strip().lower()
        if not target:
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (row.get("email") or "").strip().lower() != target:
                continue
            if partner_id is not None and row.get("partner_id") != partner_id:
                continue
            return row
        return None

    @staticmethod
    def create_customer(
        email: str,
        partner_id: str,
        *,
        name: str | None = None,
        subscription_id: str | None = None,
        customer_id: str | None = None,
        click_id: str | None = None,
        created_at: str | None = None,
        lead_at: str | None = None,
        active_at: str | None = None,
        status: str | None = None,
    ) -> Any:
        """
        POST /v1/customers — create a Tolt customer.

        Request body (JSON):

        - email (str, required): Customer's email address.
        - partner_id (str, required): The partner ID who referred this customer.
        - name (str, optional): Customer's full name.
        - subscription_id (str, optional): Associated subscription identifier.
        - customer_id (str, optional): Your internal customer identifier.
        - click_id (str, optional): Tracking click identifier.
        - created_at (str, optional): ISO 8601 timestamp when the customer was created.
        - lead_at (str, optional): ISO 8601 timestamp when the customer became a lead.
        - active_at (str, optional): ISO 8601 timestamp when the customer became active.
        - status (str, optional): One of: ``lead``, ``trialing``, ``active``, ``canceled``.

        Returns the parsed JSON response body (success or error payload).
        """
        url = f"{ToltService.BASE_URL}/v1/customers"
        payload: dict[str, Any] = {
            "email": email,
            "partner_id": partner_id,
        }
        optional = {
            "name": name,
            "subscription_id": subscription_id,
            "customer_id": customer_id,
            "click_id": click_id,
            "created_at": created_at,
            "lead_at": lead_at,
            "active_at": active_at,
            "status": status,
        }
        for key, val in optional.items():
            if val is not None and val != "":
                payload[key] = val

        response = requests.post(
            url,
            headers=ToltService.get_headers(),
            json=payload,
        )
        if response.status_code not in (200, 201):
            print(
                f"Error creating Tolt customer: "
                f"{response.status_code} - {response.text}"
            )
        try:
            return response.json()
        except ValueError:
            return {"error": "invalid_json", "text": response.text}

    
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

