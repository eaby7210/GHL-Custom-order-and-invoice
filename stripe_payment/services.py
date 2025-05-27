from core.services import OAuthServices
import requests
import json


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
            print(json.dumps(response.json(),indent=4))
            # InvoiceServices.save_contact(response.json().get("contact"))
            return response.json()
        else:
            print(f"❌ Failed to create Invoice: {response.status_code} - {response.text}")
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
    