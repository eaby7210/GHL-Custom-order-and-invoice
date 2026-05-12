import os
import django
from unittest.mock import MagicMock, patch

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from stripe_payment.m2m_views import NotaryUserM2MViewSet
from stripe_payment.models import NotaryUser, NotaryClientCompany

# Define mock data based on user payload
payload = {
    "id": "bab9751a-705a-4e2d-b3d4-2f2cc9d9e25d",
    "email": "test_m2m_create_user@example.com",
    "role": "customer",
    "first_name": "TestM2M",
    "last_name": "UserM2M",
    "name": "TestM2M UserM2M",
    "company": "TestM2MCompany",
    "phone": "555-0199",
    "address": "123 M2M St",
    "city": "M2M City",
    "state": "ST",
    "zip_code": "90210",
    "country": "US",
    "onboarding_completed": False,
    "team_id": None,
}

@patch('stripe_payment.services.NotaryDashServices')
@patch('stripe_payment.utils.create_stripe_customer')
def test_create_user(mock_create_stripe, mock_services):
    print("Running test_create_user...")
    
    # Mock create_client response (Company)
    mock_services.create_client.return_value = {
        "data": {
            "id": 99101, # Integer ID for company
            "company_name": "TestM2MCompany",
            "owner_id": 1,
            "parent_company_id": 1,
            "type": "client",
            "active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    }
    
    # Mock create_client_user response (User)
    mock_services.create_client_user.return_value = {
        "data": {
            "id": 99202, # Integer user ID
            "first_name": "TestM2M",
            "last_name": "UserM2M",
            "email": "test_m2m_create_user@example.com",
            "last_company_id": 99101,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "type": "customer"
        }
    }
    
    mock_create_stripe.return_value = MagicMock(id="cus_m2mtest")

    factory = APIRequestFactory()
    view = NotaryUserM2MViewSet.as_view({'post': 'create'})
    
    request = factory.post('/users/', payload, format='json')
    
    # Force authentication if IsM2MClient permission requires it.
    # For this test, we might bypass permission or mock it, but IsM2MClient likely checks headers or user.
    # Let's try to mock the permission check or provide necessary headers if known.
    # Assuming IsM2MClient checks for a specific header or token. 
    # For now, let's proceed and see if it fails on permission.
    
    # Actually, we can override permission_classes in the view instance for testing if needed,
    # or just assume the factory request doesn't run permission checks by default? 
    # ViewSets DO run permission checks.
    # Let's try to bypass permission by mocking.
    
    view.cls.permission_classes = [] 

    response = view(request)
    
    print(f"Response status: {response.status_code}")
    print(f"Response data: {response.data}")
    
    if response.status_code == 201:
        # Check DB
        user = NotaryUser.objects.filter(id=99202).first()
        if user:
            print(f"SUCCESS: User created in DB: {user} (ID: {user.id})")
            print(f"User email: {user.email}")
            print(f"User last_company_id: {user.last_company_id}")
        else:
            print("FAILURE: User not found in DB")
            
        company = NotaryClientCompany.objects.filter(id=99101).first()
        if company:
             print(f"SUCCESS: Company created in DB: {company} (ID: {company.id})")
        else:
             print("FAILURE: Company not found in DB")
    else:
        print("FAILURE: Response status was not 201")

if __name__ == "__main__":
    try:
        test_create_user()
    except Exception as e:
        print(f"Error: {e}")
