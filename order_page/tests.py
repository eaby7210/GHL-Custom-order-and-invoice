from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework import status
from stripe_payment.models import NotaryClientCompany, NotaryUser
from order_page.models import FramerRegistrationSubmission

@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class FramerRegistrationTests(TestCase):
    def setUp(self):
        self.register_url = reverse('framer-register')
        self.webhook_url = reverse('framer_webhook')

    @patch('stripe_payment.utils.create_stripe_customer')
    @patch('stripe_payment.services.NotaryDashServices.create_client_user')
    @patch('stripe_payment.services.NotaryDashServices.create_client')
    def test_registration_with_company(self, mock_create_client, mock_create_user, mock_create_stripe):
        # Mock NotaryDash Client Creation
        mock_create_client.return_value = {
            "data": {
                "id": 12345,
                "owner_id": 11,
                "parent_company_id": None,
                "type": "regular",
                "company_name": "Acme Corp",
                "parent_company_name": None,
                "attr": {},
                "address": {},
                "deleted_at": None,
                "created_at": "2026-06-08T00:00:00Z",
                "updated_at": "2026-06-08T00:00:00Z"
            }
        }
        
        # Mock NotaryDash User Creation
        mock_create_user.return_value = ({
            "data": {
                "id": 67890,
                "first_name": "Jane",
                "last_name": "Doe",
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "photo_url": None,
                "country_code": "US",
                "tz": "America/New_York",
                "attr": {},
                "last_login_at": None,
                "last_ip": None,
                "last_company_id": 12345,
                "email_unverified": False,
                "disabled": False,
                "deleted_at": None,
                "created_at": "2026-06-08T00:00:00Z",
                "updated_at": "2026-06-08T00:00:00Z",
                "type": "regular"
            }
        }, None)

        # Mock Stripe Customer Creation
        mock_stripe_cust = MagicMock()
        mock_stripe_cust.id = "cus_mock123"
        mock_create_stripe.return_value = mock_stripe_cust

        payload = {
            "First Name": "Jane",
            "Last Name": "Doe",
            "Email": "jane.doe@example.com",
            "Phone Number": "1234567890",
            "Company": "Acme Corp",
            "Password": "password123",
            "ref": "test_ref"
        }

        response = self.client.post(self.register_url, payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertFalse(data["hasError"])
        self.assertIn("company_id=12345", data["redirect_url"])

        # Check local DB persistence
        self.assertTrue(NotaryClientCompany.objects.filter(id=12345).exists())
        self.assertTrue(NotaryUser.objects.filter(id=67890).exists())

    @patch('stripe_payment.utils.create_stripe_customer')
    @patch('stripe_payment.services.NotaryDashServices.create_client_user')
    @patch('stripe_payment.services.NotaryDashServices.create_client')
    def test_registration_missing_company(self, mock_create_client, mock_create_user, mock_create_stripe):
        # Mock NotaryDash Client Creation
        mock_create_client.return_value = {
            "data": {
                "id": 12346,
                "owner_id": 11,
                "parent_company_id": None,
                "type": "regular",
                "company_name": "Jane Doe's Company",
                "parent_company_name": None,
                "attr": {},
                "address": {},
                "deleted_at": None,
                "created_at": "2026-06-08T00:00:00Z",
                "updated_at": "2026-06-08T00:00:00Z"
            }
        }
        
        # Mock NotaryDash User Creation
        mock_create_user.return_value = ({
            "data": {
                "id": 67891,
                "first_name": "Jane",
                "last_name": "Doe",
                "name": "Jane Doe",
                "email": "jane.doe2@example.com",
                "photo_url": None,
                "country_code": "US",
                "tz": "America/New_York",
                "attr": {},
                "last_login_at": None,
                "last_ip": None,
                "last_company_id": 12346,
                "email_unverified": False,
                "disabled": False,
                "deleted_at": None,
                "created_at": "2026-06-08T00:00:00Z",
                "updated_at": "2026-06-08T00:00:00Z",
                "type": "regular"
            }
        }, None)

        mock_stripe_cust = MagicMock()
        mock_stripe_cust.id = "cus_mock124"
        mock_create_stripe.return_value = mock_stripe_cust

        payload = {
            "First Name": "Jane",
            "Last Name": "Doe",
            "Email": "jane.doe2@example.com",
            "Phone Number": "1234567890",
            "Password": "password123"
        }

        # Submit without Company field
        response = self.client.post(self.register_url, payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertIn("company_id=12346", data["redirect_url"])

        # Check company was created with the generated name
        company_obj = NotaryClientCompany.objects.get(id=12346)
        self.assertEqual(company_obj.company_name, "Jane Doe's Company")

    @patch('stripe_payment.utils.create_stripe_customer')
    @patch('stripe_payment.services.NotaryDashServices.create_client_user')
    @patch('stripe_payment.services.NotaryDashServices.create_client')
    def test_registration_duplicate_email(self, mock_create_client, mock_create_user, mock_create_stripe):
        # Create an existing user
        NotaryClientCompany.objects.create(
            id=12347,
            company_name="Existing Company",
        )
        NotaryUser.objects.create(
            id=67892,
            email="existing@example.com",
            first_name="Existing",
            last_name="User",
            last_company_id=12347
        )

        payload = {
            "First Name": "Duplicate",
            "Last Name": "User",
            "Email": "existing@example.com",
            "Password": "password123"
        }

        # Submit registration for already registered email - should return duplicate info with 200 OK
        response = self.client.post(self.register_url, payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data["valid"])
        self.assertTrue(data["hasError"])
        self.assertEqual(data["code"], "duplicate")
        self.assertEqual(data["message"], "Email already registered")

        # Now test the Framer Webhook duplicate handling which should succeed with 200 OK and existing details
        webhook_payload = {
            "First Name": "Duplicate",
            "Last Name": "User",
            "Email": "existing@example.com",
            "Password": "password123"
        }
        # Webhook signature verification is skipped when FRAMER_WEBHOOK_SECRET is not set
        response = self.client.post(
            self.webhook_url,
            webhook_payload,
            content_type='application/json',
            HTTP_FRAMER_SIGNATURE='mock_signature',
            HTTP_FRAMER_WEBHOOK_SUBMISSION_ID='sub_123'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["message"], "Account already exists")
        self.assertIn("company_id=12347", data["url"])
        self.assertIn("client_id=67892", data["url"])
