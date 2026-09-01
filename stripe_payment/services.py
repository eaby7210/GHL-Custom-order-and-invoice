from core.services import OAuthServices
import requests
import json, time
from django.conf import settings
from django.core.cache import cache
from requests.exceptions import RequestException

DEFAULT_TIMEOUT = 25

# NotaryDash get_client_one_user — avoid hammering API for stable profile data.
NOTARY_CLIENT_ONE_USER_CACHE_SECONDS = 15 * 24 * 60 * 60

# how long to wait for the web-session fallback: covers a cold login
# (~5-10s observed) plus one API call, comfortably under gunicorn's 400s
# worker timeout - this bounded wait is exactly what avoids repeating the
# failure pattern that got a request killed mid-retry (see order 12704).
NOTARYDASH_WEB_FALLBACK_TIMEOUT = 45


def _try_web_fallback(method, path, json_data=None):
    """
    Attempt a NotaryDash call via the web-session fallback (see
    stripe_payment/notarydash_web.py) when the Bearer-key API has failed.

    Returns the parsed JSON dict on success, or None on any failure -
    including the flag being off, the task timing out, or the fallback
    worker being down. None here means "fall through to today's existing
    behavior", never a new failure mode.
    """
    if not settings.NOTARYDASH_WEB_FALLBACK_ENABLED:
        return None
    try:
        from stripe_payment.tasks import notarydash_web_call
        return notarydash_web_call.apply_async(
            args=[method, path, json_data]
        ).get(timeout=NOTARYDASH_WEB_FALLBACK_TIMEOUT)
    except Exception as e:
        print(f"⚠️ NotaryDash web-session fallback failed ({method} {path}): {e}")
        return None

def request_with_retry(url, headers, params=None, max_retries=5, delay=30, timeout=DEFAULT_TIMEOUT):
    """
    Performs GET request with automatic retry on status 429 and network errors.
    
    Args:
        url (str): Request URL
        headers (dict): Request headers
        params (dict): Query params
        max_retries (int): Max retry attempts
        delay (int/float): Initial delay between retries (seconds). Increases exponentially.
        timeout (int/float): Request timeout (seconds)
    """
    attempt = 0

    while attempt < max_retries:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)

            # success
            if 200 <= response.status_code < 300:
                return response

            # rate limited → retry
            if response.status_code == 429:
                attempt += 1
                wait_time = min(delay * (2 ** (attempt - 1)), 120)
                print(f"⚠️ Rate limit hit (429). Retrying in {wait_time} seconds... [{attempt}/{max_retries}]")
                time.sleep(wait_time)
                continue
            
            # other error (5xx) -> maybe retry? For now, we return response if it's not 429 but connected.
            return response

        except RequestException as e:
            attempt += 1
            wait_time = min(delay * (2 ** (attempt - 1)), 120)
            print(f"⚠️ Request failed: {e}. Retrying in {wait_time} seconds... [{attempt}/{max_retries}]")
            time.sleep(wait_time)
            continue

    print("❌ Max retries exceeded for:", url)
    return None

CREATE_CLIENT_USER_ERROR_MESSAGE = "Failed to create client user"


def parse_notarydash_error_response(
    response, *, default_message=CREATE_CLIENT_USER_ERROR_MESSAGE
):
    """
    Build a client-facing payload from a NotaryDash 4xx/5xx response.

    ``message`` always includes ``default_message``; field/API detail is appended
    when present and exposed under ``errors``.
    """
    body = None
    if response is not None:
        try:
            body = response.json()
        except (ValueError, AttributeError, TypeError):
            text = (getattr(response, "text", None) or "").strip()
            payload = {"message": default_message, "errors": {}}
            if text:
                payload["detail"] = text
            if response is not None:
                payload["status_code"] = response.status_code
            return payload

    if not isinstance(body, dict):
        payload = {"message": default_message, "errors": {}}
        if response is not None:
            payload["status_code"] = response.status_code
        return payload

    errors = {}
    nested = body.get("errors")
    if isinstance(nested, dict):
        for key, val in nested.items():
            field = str(key)
            if isinstance(val, list):
                errors[field] = [str(item) for item in val if item is not None]
            elif val is not None:
                errors[field] = [str(val)]
    else:
        for key, val in body.items():
            if key in ("message", "success", "error", "data"):
                continue
            field = str(key)
            if isinstance(val, list):
                errors[field] = [str(item) for item in val if item is not None]
            elif val is not None:
                errors[field] = [str(val)]

    parts = []
    for field, msgs in errors.items():
        label = field.split(".")[-1].replace("_", " ").strip().title() or field
        for msg in msgs:
            text = str(msg)
            parts.append(
                text if label.lower() in text.lower() else f"{label}: {text}"
            )

    api_message = body.get("message") or body.get("error")
    if parts:
        detail = parts[0] if len(parts) == 1 else "; ".join(parts)
        message = f"{default_message}. {detail}"
    elif api_message and str(api_message).strip():
        api_message = str(api_message).strip()
        message = (
            api_message
            if api_message == default_message
            or api_message.startswith(default_message)
            else f"{default_message}. {api_message}"
        )
    else:
        message = default_message

    payload = {"message": message, "errors": errors}
    if response is not None:
        payload["status_code"] = response.status_code
    return payload


def post_with_retry(
    url,
    headers,
    json_data=None,
    max_retries=5,
    delay=30,
    timeout=DEFAULT_TIMEOUT,
    *,
    retry_on_rate_limit=True,
):
    """
    Performs POST request with optional retry on status 429 and network errors.

    When ``retry_on_rate_limit`` is False, 429 and network errors are returned
    immediately (no sleep) — use for user-facing requests such as Framer signup.
    """
    attempt = 0

    while attempt < max_retries:
        try:
            response = requests.post(url, headers=headers, json=json_data, timeout=timeout)

            if 200 <= response.status_code < 300:
                return response

            if response.status_code == 429:
                if not retry_on_rate_limit:
                    print("⚠️ Rate limit hit (429). Returning NotaryDash response immediately.")
                    return response
                attempt += 1
                wait_time = min(delay * (2 ** (attempt - 1)), 120)
                print(f"⚠️ Rate limit hit (429). Retrying in {wait_time} seconds... [{attempt}/{max_retries}]")
                time.sleep(wait_time)
                continue

            return response

        except RequestException as e:
            if not retry_on_rate_limit:
                print(f"⚠️ Request failed: {e}. No retry (retry_on_rate_limit=False).")
                return None
            attempt += 1
            wait_time = min(delay * (2 ** (attempt - 1)), 120)
            print(f"⚠️ Request failed: {e}. Retrying in {wait_time} seconds... [{attempt}/{max_retries}]")
            time.sleep(wait_time)
            continue

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
        try:
            response = requests.post(url, headers=headers, json=data, timeout=DEFAULT_TIMEOUT)

            if response.status_code == 201:
                # print(json.dumps(response.json(),indent=4))
                # InvoiceServices.save_contact(response.json().get("contact"))
                return response.json()
            else:
                print(f"❌ Failed to create Invoice: {response.status_code} - {response.text}")
                return None
        except RequestException as e:
            print(f"❌ Exception creating Invoice: {e}")
            return None
    
    @staticmethod
    def get_invoice(location_id, invoice_id):
        headers = OAuthServices.get_valid_headers(location_id)
        querystring = {"altId":location_id,"altType":"location"}
        url = f"https://services.leadconnectorhq.com/invoices/{invoice_id}"
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=DEFAULT_TIMEOUT)

            if 200 <= response.status_code < 300:
                print(f"✅ Invoice {invoice_id} retrieved successfully.")
                # print(json.dumps(response.json(), indent=4))
                return response.json()
            else:
                print(f"❌ Failed to retrieve Invoice {invoice_id}: {response.status_code} - {response.text}")
                return None
        except RequestException as e:
            print(f"❌ Exception retrieving Invoice {invoice_id}: {e}")
            return None
    
    @staticmethod
    def send_invoice(location_id, invoice_id, data):
        headers = OAuthServices.get_valid_headers(location_id)
        url = f"https://services.leadconnectorhq.com/invoices/{invoice_id}/send"
        try:
            response = requests.post(url, headers=headers, json=data, timeout=DEFAULT_TIMEOUT)

            if 200 <= response.status_code < 300:
                print(f"✅ Invoice {invoice_id} sent successfully.")
                return response.json().get("invoice", {})
            else:
                print(f"❌ Failed to send Invoice {invoice_id}: {response.status_code} - {response.text}")
                return None
        except RequestException as e:
            print(f"❌ Exception sending Invoice {invoice_id}: {e}")
            return None

    @staticmethod
    def record_payment(location_id, invoice_id, data):
        headers = OAuthServices.get_valid_headers(location_id)
        url = f"https://services.leadconnectorhq.com/invoices/{invoice_id}/record-payment"
        try:
            response = requests.post(url, headers=headers, json=data, timeout=DEFAULT_TIMEOUT)

            if 200 <= response.status_code < 300:
                print(f"✅ Manual payment for Invoice {invoice_id} processed successfully.")
                return response.json().get("invoice", {})
            else:
                print(f"❌ Failed to process manual payment for Invoice {invoice_id}: {response.status_code} - {response.text}")
                return None
        except RequestException as e:
            print(f"❌ Exception recording payment for Invoice {invoice_id}: {e}")
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
    def get_client_once(id: str):
        """
        Single GET to /api/v2/clients/{id} with no retries (unlike get_client).

        Use when one request is enough, e.g. to detect NotaryDash HTTP 429 without
        retry/backoff loops. Client user details should still use get_client_one_user
        (retries + cache).

        Returns:
            (body_dict, None) on 2xx JSON success.
            (None, "rate_limited") on HTTP 429.
            (None, "error") on network errors, non-2xx, or invalid JSON.
        """
        url = f"{BASE_URL}/api/v2/clients/{id}"
        try:
            response = requests.get(
                url, headers=Notary_header, timeout=DEFAULT_TIMEOUT
            )
        except RequestException as exc:
            print(f"❌ get_client_once network error: {exc}")
            return None, "error"

        if response.status_code == 429:
            print("❌ get_client_once: NotaryDash returned 429 Too Many Requests")
            fallback = _try_web_fallback("GET", f"/api/v2/clients/{id}")
            if fallback is not None:
                print("✅ get_client_once: recovered via web-session fallback.")
                return fallback, None
            return None, "rate_limited"

        if 200 <= response.status_code < 300:
            try:
                body = response.json()
            except ValueError:
                print("❌ get_client_once: response was not valid JSON")
                return None, "error"
            print("✅ Client retrieved successfully (single request).")
            return body, None

        print(
            f"❌ get_client_once failed: "
            f"{response.status_code if response is not None else 'No Response'}"
        )
        return None, "error"

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
        env_tag = "test" if settings.NOTARY_TEST else "prod"
        cache_key = (
            "stripe_payment:notarydash:client_one_user:v1:"
            f"{env_tag}:{client_id}:{user_id}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            print("✅ Single client user (cache hit).")
            return cached

        url = f"{BASE_URL}/api/v2/clients/{client_id}/users/{user_id}"

        response = request_with_retry(url, headers=Notary_header)

        if response and 200 <= response.status_code < 300:
            print("✅ Single client user retrieved successfully.")
            payload = response.json()
            cache.set(cache_key, payload, NOTARY_CLIENT_ONE_USER_CACHE_SECONDS)
            return payload

        print(f"❌ Failed: {response.status_code if response else 'No Response'}")
        return None

    @staticmethod
    def get_client_one_user_once(client_id, user_id):
        """
        Single GET to /api/v2/clients/{client_id}/users/{user_id}, no retries.

        Use where the caller already has this user cached in the DB (NotaryUser)
        and can fall back to that record on failure — avoids blocking the
        request/webhook worker on 429 backoff sleeps for data we already have.

        Returns:
            (body_dict, None) on 2xx JSON success (also cache-hit).
            (None, "rate_limited") on HTTP 429.
            (None, "error") on network errors, non-2xx, or invalid JSON.
        """
        env_tag = "test" if settings.NOTARY_TEST else "prod"
        cache_key = (
            "stripe_payment:notarydash:client_one_user:v1:"
            f"{env_tag}:{client_id}:{user_id}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            print("✅ Single client user (cache hit).")
            return cached, None

        url = f"{BASE_URL}/api/v2/clients/{client_id}/users/{user_id}"
        try:
            response = requests.get(url, headers=Notary_header, timeout=DEFAULT_TIMEOUT)
        except RequestException as exc:
            print(f"❌ get_client_one_user_once network error: {exc}")
            return None, "error"

        if response.status_code == 429:
            print("❌ get_client_one_user_once: NotaryDash returned 429 Too Many Requests")
            fallback = _try_web_fallback("GET", f"/api/v2/clients/{client_id}/users/{user_id}")
            if fallback is not None:
                print("✅ get_client_one_user_once: recovered via web-session fallback.")
                cache.set(cache_key, fallback, NOTARY_CLIENT_ONE_USER_CACHE_SECONDS)
                return fallback, None
            return None, "rate_limited"

        if 200 <= response.status_code < 300:
            try:
                payload = response.json()
            except ValueError:
                print("❌ get_client_one_user_once: response was not valid JSON")
                return None, "error"
            print("✅ Single client user retrieved successfully (single request).")
            cache.set(cache_key, payload, NOTARY_CLIENT_ONE_USER_CACHE_SECONDS)
            return payload, None

        print(f"❌ get_client_one_user_once failed: {response.status_code}")
        return None, "error"

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
        # print("Creating order with data:", json.dumps(data, indent=4, default=str))

        # retry_on_rate_limit=False: this is called synchronously from request
        # handlers (Stripe webhook, m2m views). A blocking retry loop here can
        # sleep past gunicorn's worker timeout and get the worker killed
        # mid-request, aborting order processing before the caller's own
        # PROCESS_ORDER_RETRYABLE -> fulfill_order_task fallback ever runs.
        # Fail fast on 429 instead and let that Celery-based retry own it.
        response = post_with_retry(
            url, headers=Notary_header, json_data=data, retry_on_rate_limit=False
        )

        if response and 200 <= response.status_code < 300:
            print("✅ Order created successfully.")
            return response.json()

        print(f"❌ Failed to create order: {response.status_code if response else 'No Response'} - {response.text if response else ''}")
        fallback = _try_web_fallback("POST", "/api/v2/orders", data)
        if fallback is not None:
            print("✅ create_order: recovered via web-session fallback.")
            return fallback
        return None

    @staticmethod
    def create_products(data):
        url = f"{BASE_URL}/api/v2/companies/{data.get('client_id')}/products"

        # see create_order() above for why retry_on_rate_limit=False here
        response = post_with_retry(
            url, headers=Notary_header, json_data=data, retry_on_rate_limit=False
        )

        if response and 200 <= response.status_code < 300:
            print("✅ Products created successfully.")
            return response.json()

        print(f"❌ Failed to create products: {response.status_code if response else 'No Response'} - {response.text if response else ''}")
        client_id = data.get('client_id')
        fallback = _try_web_fallback("POST", f"/api/v2/companies/{client_id}/products", data)
        if fallback is not None:
            print("✅ create_products: recovered via web-session fallback.")
            return fallback
        return None

    @staticmethod
    def create_client(data, *, retry_on_rate_limit=True):
        url = f"{BASE_URL}/api/v2/clients"

        response = post_with_retry(
            url,
            headers=Notary_header,
            json_data=data,
            retry_on_rate_limit=retry_on_rate_limit,
        )

        if response and 200 <= response.status_code < 300:
            print("✅ Client created successfully.")
            return response.json()

        print(f"❌ Failed to create client: {response.status_code if response else 'No Response'} - {response.text if response else ''}")
        return None

    @staticmethod
    def create_client_user(client_id: str, user_data: dict, *, retry_on_rate_limit=True):
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
            (success_json, error_payload) — exactly one of the tuple values is None.
            error_payload has ``message`` and optional ``errors`` field map.
        """
        url = f"{BASE_URL}/api/v2/clients/{client_id}/users"
        headers = {
            **Notary_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = post_with_retry(
                url,
                headers=headers,
                json_data=user_data,
                retry_on_rate_limit=retry_on_rate_limit,
            )

            if response and 200 <= response.status_code < 300:
                print("✅ Client user created successfully.")
                return response.json(), None

            print(
                f"❌ Failed to create client user: "
                f"{response.status_code if response else 'No Response'} - "
                f"{response.text if response else ''}"
            )
            return None, parse_notarydash_error_response(
                response, default_message=CREATE_CLIENT_USER_ERROR_MESSAGE
            )
        except Exception as e:
            print(f"❌ Exception creating client user: {e}")
            return None, {
                "message": CREATE_CLIENT_USER_ERROR_MESSAGE,
                "errors": {},
            }