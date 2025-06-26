import requests
from django.utils.timezone import now
from datetime import timedelta
from django.utils.timezone import is_naive, make_aware
from .models import OAuthToken, Contact
from django.conf import settings
from django.db import transaction
import requests 
from datetime import datetime
from typing import Any
import json, os
from django.utils.dateparse import parse_datetime
from django.contrib.contenttypes.models import ContentType
from django.apps import apps

import time




TOKEN_URL = 'https://services.leadconnectorhq.com/oauth/token'
LIMIT_PER_PAGE = 100
BASE_URL = 'https://services.leadconnectorhq.com'
API_VERSION = "2021-07-28"
MIGRATED_TASKS_FILE = "migrated_tasks.json"
FAILED_TASKS_FILE = "failed_tasks.json"

class OAuthTokenError(Exception):
    '''Custom exeption for Oauth token-related errors'''

class OAuthServices:
    
    
    @staticmethod
    def get_valid_headers(location_id):
        token_obj = OAuthServices.get_valid_access_token_obj(location_id)
        return {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Version": "2021-07-28",
            "Content-Type": "application/json"
        }
    
    @staticmethod
    def get_valid_access_token_obj(location_id=None):
       
        from django.conf import settings
        if location_id:
            token_obj = OAuthToken.objects.get(LocationId=location_id)  # Assuming one OAuth record, change if one per user
        else:
            token_obj = OAuthToken.objects.first()
            location_id = token_obj.LocationId if token_obj else None
        if not token_obj:
            raise OAuthTokenError("OAuth token not found. Please authenticate first")
        
        if token_obj.is_expired():
            token_obj = OAuthServices.refresh_access_token(location_id)
            
        return token_obj
    
    @staticmethod
    def get_fresh_token(auth_code):
        '''Exchange authorization code for a fresh access token'''
        print("reached hereee")
        from django.conf import settings
        
        headers = {
        "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            'client_id': settings.CLIENT_ID,
            'client_secret' : settings.CLIENT_SECRET,
            'grant_type' : 'authorization_code',
            'code' : auth_code,
        }
        # print(payload)
        response =requests.post(TOKEN_URL,headers=headers,data=payload)
        token_data = response.json()

        
        if response.status_code == 200:
            # company_data = fetch_company_data(token_data['access_token'], token_data['locationId'])
            # print("company data:",company_data)
            print("success response")
            token_obj, created = OAuthToken.objects.update_or_create(
                LocationId=token_data["locationId"],
                defaults={
                    "access_token": token_data["access_token"],
                    "token_type": token_data["token_type"],
                    "expires_at": (now() + timedelta(seconds=token_data["expires_in"])).date(),
                    "refresh_token": token_data["refresh_token"],
                    "scope": token_data["scope"],
                    "userType": token_data["userType"],
                    "companyId": token_data["companyId"],
                    "userId": token_data["userId"],
                    
                }
            )
            return token_obj
        else:
            print("errror response")
            print(f"Payload: \n {payload}")
            raise ValueError(f"Failed to get fresh access token: {token_data}")
    
    
    @staticmethod
    def refresh_access_token(location_id):
        """
        Refresh the access token using the refresh token.
        """
        
        token_obj = OAuthToken.objects.get(LocationId=location_id)
        payload = {
            'grant_type': 'refresh_token',
            'client_id': settings.CLIENT_ID,
            'client_secret': settings.CLIENT_SECRET,
            'refresh_token': token_obj.refresh_token
        }
        print(f"payload: {payload}")
        response = requests.post(TOKEN_URL, data=payload)

        if response.status_code != 200:
            raise OAuthTokenError(f"Failed to refresh access token: {response.json()}")

        new_tokens = response.json()
        print("New Tokens:", new_tokens)

        token_obj.access_token = new_tokens.get("access_token")
        token_obj.refresh_token = new_tokens.get("refresh_token")
        token_obj.expires_at = now() + timedelta(seconds=new_tokens.get("expires_in"))

        token_obj.scope = new_tokens.get("scope")
        token_obj.userType = new_tokens.get("userType")
        token_obj.companyId = new_tokens.get("companyId")
        # token_obj.LocationId = new_tokens.get("locationId")
        token_obj.userId = new_tokens.get("userId")

        token_obj.save()
        return token_obj


class ContactServiceError(Exception):
    "Exeption for Contact api's"
    pass

class ContactServices:
    
    @staticmethod
    def get_contact(location_id,contact_id):
        """
        Fetch contacts from GoHighLevel API with given parameters.
        """
        token_obj = OAuthServices.get_valid_access_token_obj(location_id)
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
            "Version": API_VERSION,
        }

      
        url = f"{BASE_URL}/contacts/{contact_id}"

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            raise ContactServiceError(f"API request failed: {response.status_code}")
    
    
    @staticmethod
    def save_contact(contact):
        contact = contact.get("contact") if contact.get("contact") else contact  # Allow both full response or just contact dict

        if not contact or not contact.get("id"):
            print("❌ No valid contact data to save.")
            return None

        contact_obj, created = Contact.objects.update_or_create(
            id=contact["id"],
            defaults={
                "first_name": contact.get("firstName", ""),
                "last_name": contact.get("lastName", ""),
                "email": contact.get("email", ""),
                "phone": contact.get("phone", ""),
                "country": contact.get("country", ""),
                "location_id": contact.get("locationId", ""),
                "type": contact.get("type", "lead"),
                "date_added": datetime.fromisoformat(contact["dateAdded"].replace("Z", "+00:00")) if contact.get("dateAdded") else None,
                "date_updated": datetime.fromisoformat(contact["dateUpdated"].replace("Z", "+00:00")) if contact.get("dateUpdated") else None,
                "dnd": contact.get("dnd", False),
            }
        )

        print(f"{'✅ Created' if created else '🔄 Updated'} contact {contact_obj.id}")
        return contact_obj
    
    @staticmethod
    def post_contact(location_id, contact_data):
        headers = OAuthServices.get_valid_headers(location_id)
        url = "https://services.leadconnectorhq.com/contacts/"
        response = requests.post(url, headers=headers, json=contact_data)

        if response.status_code == 201:
            # print(json.dumps(response.json(),indent=4))
            ContactServices.save_contact(response.json().get("contact"))
            return response.json().get("contact", {}) , response.status_code
        else:
            print(f"\033[91m❌ Failed to create contact: {response.status_code} - {response.text}\033[0m")
            return response.json(), response.status_code

    
    @staticmethod
    def get_contacts(location_id,query=None, url=None, limit=LIMIT_PER_PAGE):
        """
        Fetch contacts from GoHighLevel API with given parameters.
        """
        token_obj = OAuthServices.get_valid_access_token_obj(location_id)
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
            "Version": API_VERSION,
        }

        if url:
            response = requests.get(url, headers=headers)
        else:
            url = f"{BASE_URL}/contacts/"
            params = {
                "locationId": token_obj.LocationId,
                "limit": limit,
            }
            if query:
                params["query"] = query
            response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()
        else:
            raise ContactServiceError(f"API request failed: {response.status_code}")
    
    @staticmethod
    def pull_contacts(query=None):
        """
        Fetch all contacts using nextPageURL-based pagination and save them to the database.
        """
        imported_contacts_summary = []
        # location_ids = list(OAuthToken.objects.values_list('LocationId', flat=True))
        location_ids = ['HBMH06bPfTaKkZx49Y4x']
        for location_id in location_ids:
            tokenobj: OAuthToken = OAuthServices.get_valid_access_token_obj(location_id)
            all_contacts = []
            url = None
            start_after_id = None
            start_after = None
            i = 0

            while True:
                # If there is a startAfter or startAfterId, include them in the parameters
                params = {
                    "locationId": tokenobj.LocationId,
                    "limit": LIMIT_PER_PAGE,
                }
                if query:
                    params["query"] = query
                if start_after:
                    params["startAfter"] = start_after
                if start_after_id:
                    params["startAfterId"] = start_after_id

                # Fetch contacts from the API
                response_data = ContactServices.get_contacts(location_id=tokenobj.LocationId, query=query, url=url)

                contacts = response_data.get("contacts", [])
                all_contacts.extend(contacts)

                # Check if we should continue to the next page
                meta = response_data.get("meta", {})
                next_page_url = meta.get("nextPageUrl")
                start_after_id = meta.get("startAfterId")
                start_after = meta.get("startAfter")
                print(f"next page {i+2}: {json.dumps(meta,indent=4)}")
                if not next_page_url:
                    break  # No next page

                # Prepare for the next request
                url = next_page_url
                i += 1
            print(f"completed fetching, Saving {len(all_contacts)} Contacts")
            ContactServices._save_contacts(all_contacts)
            imported_contacts_summary.append(f"{location_id}: Imported {len(all_contacts)} contacts")
        
        return imported_contacts_summary

    @staticmethod
    def _save_contacts(contacts):
        """
        Bulk save contacts to the database along with their custom fields.
        """
        unique_contacts = {contact["id"]: contact for contact in contacts}.values()  # Remove duplicates

        contact_objects = []
        custom_field_values = []

        # Step 1: Prepare Contact objects
        for contact in unique_contacts:
            contact_obj = Contact(
                id=contact["id"],
                first_name=contact.get("firstName", ""),
                last_name=contact.get("lastName", ""),
                email=contact.get("email", ""),
                phone=contact.get("phone", ""),
                country=contact.get("country", ""),
                location_id=contact.get("locationId", ""),
                type=contact.get("type", "lead"),
                date_added=datetime.fromisoformat(contact["dateAdded"].replace("Z", "+00:00")) if contact.get("dateAdded") else None,
                date_updated=datetime.fromisoformat(contact["dateUpdated"].replace("Z", "+00:00")) if contact.get("dateUpdated") else None,
                dnd=contact.get("dnd", False),
            )
            contact_objects.append(contact_obj)

        # Step 2: Bulk insert or update contacts
        Contact.objects.bulk_create(
            contact_objects,
            update_conflicts=True,
            unique_fields=["id"],
            update_fields=[
                "first_name", "last_name", "email", "phone", "country", "location_id", "type",
                "date_added", "date_updated", "dnd"
            ],
        )

    
    @staticmethod
    def search_contacts(location_id, query ):
        """
        Search contacts by name or email.
        """
        token_obj = OAuthServices.get_valid_access_token_obj(location_id)
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
            "Version": API_VERSION,
        }

        url = f"{BASE_URL}/contacts/search"
        payload = {**query}  # Assuming query is a dict with search parameters
        # print(f"search payload: {json.dumps(payload, indent=4)}")
        response = requests.post(url, headers=headers, json=payload)
        # print(f"search result: {json.dumps(response.json(), indent=4)}")
        if response.status_code == 200:
        
            return response.json()
        else:
            raise ContactServiceError(f"API request failed: {response.status_code}")

                    
    @staticmethod
    def push_contact(contact_obj :Contact, data):
        token_obj = OAuthServices.get_valid_access_token_obj(contact_obj.location_id)
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
            "Version": API_VERSION,
        }

        url = f"{BASE_URL}/contacts/{contact_obj.id}"
      

        response = requests.put(url, headers=headers, json=data)

        if response.status_code == 200:
            return response.json()
        else:
            raise ContactServiceError(f"API request failed: {response.status_code}")


    

