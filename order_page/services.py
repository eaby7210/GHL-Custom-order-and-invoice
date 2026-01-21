import os
import requests
import time
from django.conf import settings


class GoogleService:
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY

    def get_autocomplete(self, input_text, session_token=None, **kwargs):
        """
        Get place predictions from Google Places Autocomplete (New) API.
        Accepts optional parameters like locationBias, includedPrimaryTypes via **kwargs.
        """
        url = "https://places.googleapis.com/v1/places:autocomplete"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
        }
        
        payload = {
            "input": input_text,
        }
        
        if session_token:
            payload["sessionToken"] = session_token

        # Filter and update payload with only valid optional parameters
        valid_params = {
            "includedPrimaryTypes",
            "includePureServiceAreaBusinesses",
            "includeQueryPredictions",
            "includedRegionCodes",
            "inputOffset",
            "languageCode",
            "locationBias",
            "locationRestriction",
            "origin",
            "regionCode",
        }

        for key, value in kwargs.items():
            if key in valid_params:
                payload[key] = value
            
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_timezone(self, latitude, longitude, timestamp=None):
        """
        Get timezone information from Google Maps Timezone API.
        """
        url = "https://maps.googleapis.com/maps/api/timezone/json"
        
        if timestamp is None:
            timestamp = int(time.time())
            
        params = {
            "location": f"{latitude},{longitude}",
            "timestamp": timestamp,
            "key": self.api_key,
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_place_details(self, place_id, fields=None):
        """
        Get place details from Google Places Details (New) API.
        """
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        
        # Default fields if none provided
        if not fields:
            fields = "id,displayName,addressComponents,formattedAddress"
            
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": fields
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}


class TypeformService:
    def __init__(self):
        self.access_token = getattr(settings, 'TYPEFORM_ACCESS_TOKEN', None)

    def get_form(self, form_id):
        """
        Retrieves a form by the given form_id. Includes any theme and images attached to the form as references.
        https://api.typeform.com/forms/{form_id}
        """
        if not self.access_token:
             return {"error": "Typeform access token not configured in settings."}

        url = f"https://api.typeform.com/forms/{form_id}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def sync_form(self, form_id):
        """
        Fetches the form definition from Typeform API and updates the local database.
        Returns the TypeformForm object.
        """
        data = self.get_form(form_id)
        if "error" in data:
            raise Exception(data["error"])

        from order_page.models import TypeformForm

        # Use the static method on the model
        return TypeformForm.create_or_update_from_api(data)

    def update_form(self, form_id: str, data: dict):
        """
        Updates an existing form.
        https://api.typeform.com/forms/{form_id}
        """
        if not self.access_token:
             return {"error": "Typeform access token not configured in settings."}

        url = f"https://api.typeform.com/forms/{form_id}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                try:
                    return {"error": e.response.json()}
                except ValueError:
                    return {"error": e.response.text}
            return {"error": str(e)}


