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


from decimal import Decimal
from django.test import SimpleTestCase
from .pricing import (
    recalc_bundle_price,
    _unit_adjusted_item,
    _recalc_item_price,
    _discount_qualified_count,
    _discount_percent_for,
    _resolve_service_protection,
    _service_protection_amount,
)


class PricingEngineTests(SimpleTestCase):
    """
    Pure-function checks for order_page.pricing — no DB required. Mirrors
    the fixtures used by investbootz's src/lib/bundlePricing.test.js so the
    two engines can be sanity-checked against the same numbers.
    """

    databases = set()

    def test_bundle_price_scales_with_unit_count(self):
        catalog_bundle = {
            "name": "Standard Bundle",
            "basePrice": 300,
            "price": 300,
            "mobileHomeDiscountValid": True,
            "multiUnitValid": True,
            "options": {"items": []},
        }
        base, price = recalc_bundle_price(catalog_bundle, is_mobile=False, is_multi_unit=False, num_units=1, selected_options={})
        self.assertEqual(price, Decimal("300.00"))

        base, price = recalc_bundle_price(catalog_bundle, is_mobile=False, is_multi_unit=True, num_units=3, selected_options={})
        self.assertEqual(price, Decimal("600.00"))  # 1 + 0.5*(3-1) = 2x

    def test_bundle_price_mobile_discount_and_checkbox_option(self):
        catalog_bundle = {
            "name": "Mobile Bundle",
            "basePrice": 200,
            "price": 200,
            "mobileHomeDiscountValid": True,
            "multiUnitValid": True,
            "options": {"items": [{"id": "rush", "type": "checkbox", "priceAdd": 25}]},
        }
        base, price = recalc_bundle_price(
            catalog_bundle, is_mobile=True, is_multi_unit=False, num_units=1, selected_options={"rush": True}
        )
        # 200 * 0.85 = 170, + 25 add-on
        self.assertEqual(price, Decimal("195.00"))

    def test_item_price_unit_adjusted_and_priceadd_option(self):
        catalog_item = {
            "id": "PHbasic",
            "price": 100,
            "basePrice": 100,
            "mobileHomeDiscountValid": True,
            "multiUnitValid": True,
            "options": {
                "items": [
                    {"id": "extra", "label": "Extra", "value": False, "priceAdd": 20, "priceChange": None}
                ]
            },
        }
        adjusted = _unit_adjusted_item(catalog_item, is_mobile=False, is_multi_unit=True, num_units=3)
        self.assertEqual(adjusted["price"], Decimal("200.00"))  # 100 * 2x

        price = _recalc_item_price(adjusted, {"extra": True}, {})
        self.assertEqual(price, Decimal("220.00"))  # 200 base + 20 add-on

    def test_item_price_submenu_add(self):
        catalog_item = {
            "id": "NTinperson",
            "price": 50,
            "basePrice": 50,
            "options": {},
            "submenuPriceChange": {"witness": {"type": "add", "value": 15}},
        }
        adjusted = _unit_adjusted_item(catalog_item, is_mobile=False, is_multi_unit=False, num_units=1)
        price = _recalc_item_price(adjusted, {}, {"witness": True})
        self.assertEqual(price, Decimal("65.00"))

    def test_discount_qualified_count_requires_option_for_flagged_items(self):
        catalog_services = {
            "photos": {
                "id": "photos",
                "form": {"items": [{"id": "PHbasic", "discountEligible": True, "discountRequiresOption": True}]},
            },
            "notary": {
                "id": "notary",
                "form": {"items": [{"id": "NTinperson", "discountEligible": True, "discountRequiresOption": False}]},
            },
        }
        a_la_carte_data = [
            {
                "id": "photos",
                "form": {"items": [{"id": "PHbasic", "options": {"items": [{"id": "opt1", "value": False}]}}]},
            },
            {"id": "notary", "form": {"items": [{"id": "NTinperson"}]}},
        ]
        selection = {
            "photos": {"items": {"PHbasic": True}, "options": {"PHbasic": {"opt1": False}}},
            "notary": {"items": {"NTinperson": True}, "options": {"NTinperson": {}}},
        }
        # PHbasic selected but no option checked -> doesn't qualify; NTinperson always qualifies.
        count = _discount_qualified_count(a_la_carte_data, catalog_services, selection)
        self.assertEqual(count, 1)

        selection["photos"]["options"]["PHbasic"]["opt1"] = True
        count = _discount_qualified_count(a_la_carte_data, catalog_services, selection)
        self.assertEqual(count, 2)

    def test_discount_percent_uses_highest_qualifying_tier(self):
        catalog_item = {"id": "LBcode", "discountEligible": True}
        levels = [
            {"items": 2, "percent": 20},
            {"items": 3, "percent": 30},
        ]
        self.assertEqual(_discount_percent_for(catalog_item, qualified_count=1, discount_levels=levels), Decimal("0"))
        self.assertEqual(_discount_percent_for(catalog_item, qualified_count=2, discount_levels=levels), Decimal("20"))
        self.assertEqual(_discount_percent_for(catalog_item, qualified_count=3, discount_levels=levels), Decimal("30"))

    def test_protection_only_applies_for_percent_type(self):
        percent_service = {"order_protection_type": "percent", "order_protection_value": 10}
        fixed_service = {"order_protection_type": "fixed", "order_protection_value": 10}
        self.assertEqual(_service_protection_amount(percent_service, Decimal("100")), Decimal("10.00"))
        # "fixed" is a live no-op today (frontend only ever checks the string "flat",
        # which this catalog's OrderProtectionType never produces) — replicated as-is.
        self.assertEqual(_service_protection_amount(fixed_service, Decimal("100")), Decimal("0"))

    def test_protection_invalid_selection_forces_off(self):
        catalog_service = {
            "order_protection": True,
            "order_protection_value": 10,
            "order_protection_disabled": False,
            "form": {"items": [{"id": "PHpremium30", "protectionInvalid": True}]},
        }
        self.assertFalse(_resolve_service_protection(catalog_service, ["PHpremium30"], explicit_enabled=None))
        self.assertTrue(_resolve_service_protection(catalog_service, ["other-item"], explicit_enabled=None))
        self.assertFalse(_resolve_service_protection(catalog_service, ["other-item"], explicit_enabled=False))
