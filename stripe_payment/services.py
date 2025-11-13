from core.services import OAuthServices
import requests
import json, time
from django.conf import settings

def request_with_retry(url, headers, params=None, max_retries=3, delay=3):
    """
    Performs GET request with automatic retry on status 429.
    
    Args:
        url (str): Request URL
        headers (dict): Request headers
        params (dict): Query params
        max_retries (int): Max retry attempts
        delay (int/float): Delay between retries (seconds)
    """
    attempt = 0

    while attempt < max_retries:
        response = requests.get(url, headers=headers, params=params)

        # success
        if 200 <= response.status_code < 300:
            return response

        # rate limited → retry
        if response.status_code == 429:
            attempt += 1
            print(f"⚠️ Rate limit hit (429). Retrying in {delay} seconds... [{attempt}/{max_retries}]")
            time.sleep(delay)
            continue

        # other error → stop retrying
        return response

    print("❌ Max retries exceeded for:", url)
    return None

class InvoiceServices:
    
   
    @staticmethod
    def save_contact(contact):
        pass
    @staticmethod
    def post_invoice(location_id, data):
        headers = OAuthServices.get_valid_headers(location_id)
        url = "https://services.leadconnectorhq.com/invoices/"
        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 201:
            # print(json.dumps(response.json(),indent=4))
            # InvoiceServices.save_contact(response.json().get("contact"))
            return response.json()
        else:
            print(f"❌ Failed to create Invoice: {response.status_code} - {response.text}")
            return None
    
    @staticmethod
    def get_invoice(location_id, invoice_id):
        headers = OAuthServices.get_valid_headers(location_id)
        querystring = {"altId":location_id,"altType":"location"}
        url = f"https://services.leadconnectorhq.com/invoices/{invoice_id}"
        response = requests.get(url, headers=headers, params=querystring)

        if 200 <= response.status_code < 300:
            print(f"✅ Invoice {invoice_id} retrieved successfully.")
            # print(json.dumps(response.json(), indent=4))
            return response.json()
        else:
            print(f"❌ Failed to retrieve Invoice {invoice_id}: {response.status_code} - {response.text}")
            return None
    
    @staticmethod
    def send_invoice(location_id, invoice_id, data):
        headers = OAuthServices.get_valid_headers(location_id)
        url = f"https://services.leadconnectorhq.com/invoices/{invoice_id}/send"
        response = requests.post(url, headers=headers, json=data)

        if 200 <= response.status_code < 300:
            print(f"✅ Invoice {invoice_id} sent successfully.")
            return response.json().get("invoice", {})
        else:
            print(f"❌ Failed to send Invoice {invoice_id}: {response.status_code} - {response.text}")
            return None

    @staticmethod
    def record_payment(location_id, invoice_id, data):
        headers = OAuthServices.get_valid_headers(location_id)
        url = f"https://services.leadconnectorhq.com/invoices/{invoice_id}/record-payment"
        response = requests.post(url, headers=headers, json=data)

        if 200 <= response.status_code < 300:
            print(f"✅ Manual payment for Invoice {invoice_id} processed successfully.")
            return response.json().get("invoice", {})
        else:
            print(f"❌ Failed to process manual payment for Invoice {invoice_id}: {response.status_code} - {response.text}")
            return None

TEST_BASE_URL = "https://dev.notarydash.com"
PRODUCTION_BASE_URL = "https://app.notarydash.com"
BASE_URL=""
if settings.NOTARY_TEST:
    BASE_URL = TEST_BASE_URL
else:
    BASE_URL = PRODUCTION_BASE_URL
Notary_header={
    "Authorization": f"Bearer {settings.NOTARY_API_KEY}"
}
class NotaryDashServices:
    
    @staticmethod
    def get_clients(url=None):
        if not url:
            url = f"{BASE_URL}/api/v2/clients"

        response = request_with_retry(url, headers=Notary_header)

        if response and 200 <= response.status_code < 300:
            print("✅ Clients retrieved successfully.")
            return response.json()

        print(f"❌ Failed to retrieve clients: {response.status_code if response else 'No Response'}")
        return None

    @staticmethod
    def get_client(id: str):
        url = f"{BASE_URL}/api/v2/clients/{id}"
        
        response = request_with_retry(url, headers=Notary_header)

        if response and 200 <= response.status_code < 300:
            print("✅ Client retrieved successfully.")
            return response.json()

        print(f"❌ Failed to retrieve client: {response.status_code if response else 'No Response'}")
        return None

    
    @staticmethod
    def get_client_one_user(client_id, user_id):
        url = f"{BASE_URL}/api/v2/clients/{client_id}/users/{user_id}"

        response = request_with_retry(url, headers=Notary_header)

        if response and 200 <= response.status_code < 300:
            print(f"✅ Single client user retrieved successfully.")
            return response.json()

        print(f"❌ Failed: {response.status_code if response else 'No Response'}")
        return None


    
    @staticmethod
    def get_client_user(client_id, url=None):
        if not url:
            url = f"{BASE_URL}/api/v2/clients/{client_id}/users"

        response = request_with_retry(url, headers=Notary_header)

        if response and 200 <= response.status_code < 300:
            print(f"✅ Client user for client {client_id} retrieved successfully.")
            return response.json()

        print(f"❌ Failed client user {client_id}: {response.status_code if response else 'No Response'}")
        return None

      
    @staticmethod
    def get_products(company_id, is_global: bool):
        url = f"{BASE_URL}/api/v2/companies/{company_id}/products"
        params = {"global": is_global}

        response = request_with_retry(url, headers=Notary_header, params=params)

        if response and 200 <= response.status_code < 300:
            print(f"✅ Products for company {company_id} retrieved successfully.")
            return response.json()

        print(f"❌ Failed products for company {company_id}: {response.status_code if response else 'No Response'}")
        return None

    
    @staticmethod
    def create_order(data):
        url = f"{BASE_URL}/api/v2/orders"
        print("Creating order with data:", json.dumps(data, indent=4))
        response = requests.post(url, headers=Notary_header, json=data)
        if response.status_code >= 200 and response.status_code < 300:
            print("✅ Order created successfully.")
            return response.json()
        else:
            print(f"❌ Failed to create order: {response.status_code} - {response.text}")
            return None
        
    @staticmethod
    def create_products(data):
        url = f"{BASE_URL}/api/v2/companies/{data.get("client_id")}/products"
        response = requests.post(url, headers=Notary_header, json=data)
        if response.status_code >= 200 and response.status_code < 300:
            print("✅ Products created successfully.")
            return response.json()
        else:
            print(f"❌ Failed to create products: {response.status_code} - {response.text}")
            return None
    
    @staticmethod
    def create_client(data):
        url = f"{BASE_URL}/api/v2/clients"
        response = requests.post(url, headers=Notary_header, json=data)
        if response.status_code >= 200 and response.status_code < 300:
            print("✅ Client created successfully.")
            return response.json()
        else:
            print(f"❌ Failed to create client: {response.status_code} - {response.text}")
            return None

    @staticmethod
    def create_client_user(client_id: str, user_data: dict):
        """
        Create a new user under a specific client.
        
        Args:
            client_id (str): The NotaryDash client ID.
            user_data (dict): Example:
                {
                    "user": {
                        "password": "voluptas",
                        "password_confirmation": "ipsum",
                        "first_name": "minus",
                        "last_name": "et",
                        "email": "provident",
                        "attr": {
                            "phone": "est",
                            "mobile_phone": "ex"
                        }
                    },
                    "email_credentials": False,
                    "teams": [{"id": 11}]
                }

        Returns:
            dict | None
        """
        url = f"{BASE_URL}/api/v2/clients/{client_id}/users"
        headers = {
            **Notary_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = requests.post(url, headers=headers, json=user_data)

        if 200 <= response.status_code < 300:
            print("✅ Client user created successfully.")
            return response.json()
        else:
            print(f"❌ Failed to create client user: {response.status_code} - {response.text}")
            return None