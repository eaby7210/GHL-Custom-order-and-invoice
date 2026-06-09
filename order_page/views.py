# views.py
import hmac
import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    TermsOfConditions, TypeformResponse, TypeformParser, TypeformAnswer,
    ServiceVariance, NotaryClientCompany, FramerRegistrationSubmission,
)
from rest_framework.decorators import api_view
from .serializers import TermsOfConditionsSerializer, ServiceVarianceSerializer
from rest_framework import status
import json
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from stripe_payment.services import NotaryDashServices
from stripe_payment.models import NotaryClientCompany, NotaryUser
from stripe_payment.utils import create_stripe_customer
from django.core.cache import cache
from tolt.models import Link, Partner
from tolt.services import ToltService
from .services import GoogleService


def validate_framer_registration_email(email):
    """
    Validate email for Framer signup (format + NotaryUser duplication).
    Returns dict with valid, hasError, code, message for Framer override components.
    """
    normalized = (email or "").strip()
    if not normalized:
        return {
            "valid": False,
            "hasError": True,
            "code": "required",
            "message": "Email is required",
        }

    try:
        validate_email(normalized)
    except ValidationError:
        return {
            "valid": False,
            "hasError": True,
            "code": "invalid_format",
            "message": "Please enter a valid email address",
        }

    is_registered = NotaryUser.objects.filter(
        email__iexact=normalized,
        deleted_at__isnull=True,
    ).exists()
    if is_registered:
        return {
            "valid": False,
            "hasError": True,
            "code": "duplicate",
            "message": "Email already registered",
        }

    return {
        "valid": True,
        "hasError": False,
        "code": "ok",
        "message": "",
    }


def is_framer_webhook_signature_valid(secret, submission_id, payload, signature):
    """Verify Framer-Signature per Framer webhook docs (HMAC-SHA256 over body + submission id)."""
    if len(signature) != 71 or not signature.startswith('sha256='):
        return False
    if not submission_id:
        return False
    payload_hmac = hmac.new(secret.encode('utf-8'), digestmod=hashlib.sha256)
    payload_hmac.update(payload)
    payload_hmac.update(submission_id.encode('utf-8'))
    expected_signature = 'sha256=' + payload_hmac.hexdigest()
    return hmac.compare_digest(signature.encode('utf-8'), expected_signature.encode('utf-8'))


def ensure_notary_client_company_local(company_id):
    """
    Ensure a NotaryClientCompany row exists for this NotaryDash client id.
    If missing locally, GET /api/v2/clients/{id} and upsert (same shape as create flow).
    Returns (NotaryClientCompany | None, error_message | None).
    """
    if company_id is None:
        return None, "Missing company id for NotaryClientCompany"
    try:
        pk = int(company_id)
    except (TypeError, ValueError):
        return None, "Invalid company id for NotaryClientCompany"

    existing = NotaryClientCompany.objects.filter(id=pk).first()
    if existing:
        return existing, None

    client_response = NotaryDashServices.get_client(str(pk))
    if not client_response:
        return None, "Failed to fetch client from NotaryDash for last_company_id"

    client_data = client_response.get("data") or {}
    remote_id = client_data.get("id")
    if not remote_id:
        return None, "NotaryDash client response missing id"

    client_obj, _ = NotaryClientCompany.objects.update_or_create(
        id=remote_id,
        defaults={
            "owner_id": client_data.get("owner_id"),
            "parent_company_id": client_data.get("parent_company_id"),
            "type": client_data.get("type"),
            "company_name": client_data.get("company_name"),
            "parent_company_name": client_data.get("parent_company_name"),
            "attr": client_data.get("attr", {}),
            "address": client_data.get("address") or {},
            "deleted_at": client_data.get("deleted_at"),
            "created_at": client_data.get("created_at"),
            "updated_at": client_data.get("updated_at"),
            "active": client_data.get("active", True),
        },
    )
    print(f"✅ Synced NotaryClientCompany from API: {client_obj} (ID: {client_obj.id})")
    return client_obj, None


def _framer_payload_get(payload, *keys):
    """Read a Framer form field (case-insensitive key match)."""
    if not isinstance(payload, dict):
        return None
    lower_map = {
        str(k).lower(): v for k, v in payload.items() if isinstance(k, str)
    }
    for key in keys:
        val = lower_map.get(key.lower())
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _strip_field(value):
    """Strip whitespace; empty strings become None."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def _split_full_name(name):
    full = (name or "").strip()
    if not full:
        return "", ""
    parts = full.split(None, 1)
    first = parts[0].strip() if parts else ""
    last = parts[1].strip() if len(parts) > 1 else ""
    return first, last


def normalize_registration_fields(fields):
    """Strip and normalize registration input before NotaryDash API calls."""
    email = _strip_field(fields.get("email"))
    if email:
        email = email.lower()

    first_name = _strip_field(fields.get("first_name")) or ""
    last_name = _strip_field(fields.get("last_name")) or ""
    company = _strip_field(fields.get("company")) or ""
    phone = _strip_field(fields.get("phone"))
    ref = _strip_field(fields.get("ref"))
    password = _strip_field(fields.get("password"))
    password_confirmation = _strip_field(fields.get("password_confirmation"))
    if password and not password_confirmation:
        password_confirmation = password

    return {
        "email": email,
        "company": company,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "ref": ref,
        "password": password,
        "password_confirmation": password_confirmation if password else None,
    }


def build_notary_client_user_payload(
    *,
    first_name,
    last_name,
    email,
    phone=None,
    password=None,
    password_confirmation=None,
):
    """
    NotaryDash POST /clients/{id}/users body.

    When ``password`` is set: ``email_credentials`` is False and both password
    fields are sent. Otherwise NotaryDash emails credentials to the user.
    """
    user = {
        "first_name": first_name or "",
        "last_name": last_name or "",
        "email": email,
        "attr": {"phone": phone or ""},
    }
    if password:
        user["password"] = password
        user["password_confirmation"] = password_confirmation or password
        email_credentials = False
    else:
        email_credentials = True

    return {
        "user": user,
        "email_credentials": email_credentials,
    }


def _framer_payload_phone(payload):
    """
    Phone from Framer override payload. Prefers ``Phone Number``; falls back to
    extra inputs whose key looks like a phone mask (e.g. ``(123) 456-7890``).
    """
    phone = _framer_payload_get(payload, "Phone Number", "phone", "phone number")
    if phone:
        return _strip_field(phone)
    if not isinstance(payload, dict):
        return None
    for key, val in payload.items():
        if not isinstance(key, str):
            continue
        candidate = str(val).strip() if val is not None else ""
        if len(candidate) < 7 or sum(c.isdigit() for c in candidate) < 7:
            continue
        key_lower = key.lower()
        if "phone" in key_lower or any(c.isdigit() for c in key):
            return _strip_field(candidate)
    return None


def parse_framer_registration_payload(payload):
    """Extract registration fields from a Framer override / webhook JSON body."""
    first_name = _framer_payload_get(
        payload, "First Name", "first name", "first_name"
    )
    last_name = _framer_payload_get(
        payload, "Last Name", "last name", "last_name"
    )
    if not first_name and not last_name:
        first_name, last_name = _split_full_name(
            _framer_payload_get(payload, "Name", "name")
        )

    password = _framer_payload_get(payload, "Password", "password")
    password_confirmation = _framer_payload_get(
        payload,
        "Confirm Password",
        "password confirmation",
        "password_confirmation",
        "confirm password",
    )

    return normalize_registration_fields({
        "email": _framer_payload_get(payload, "Email", "email", "email address"),
        "company": _framer_payload_get(payload, "Company", "company"),
        "first_name": first_name,
        "last_name": last_name,
        "phone": _framer_payload_phone(payload),
        "ref": _framer_payload_get(payload, "ref"),
        "password": password,
        "password_confirmation": password_confirmation,
    })


def framer_registration_fields_for_log(fields):
    """Safe copy of parsed registration fields (no password values)."""
    if not isinstance(fields, dict):
        return fields
    safe = dict(fields)
    if safe.get("password"):
        safe["password"] = "[redacted]"
    if safe.get("password_confirmation"):
        safe["password_confirmation"] = "[redacted]"
    return safe


def redact_framer_raw_payload(payload):
    """Redact sensitive keys before persisting raw Framer JSON."""
    if not isinstance(payload, dict):
        return payload
    safe = {}
    for key, value in payload.items():
        key_lower = str(key).lower()
        if "password" in key_lower:
            safe[key] = "[redacted]"
        else:
            safe[key] = value
    return safe


def record_framer_registration_submission(
    *,
    source,
    raw_payload,
    parsed_fields=None,
    http_status=None,
    response_payload=None,
    framer_submission_id="",
):
    """Persist incoming Framer registration attempt (passwords redacted)."""
    email = None
    if isinstance(parsed_fields, dict):
        email = parsed_fields.get("email")
    if not email and isinstance(raw_payload, dict):
        email = _framer_payload_get(raw_payload, "Email", "email")

    success = http_status == status.HTTP_201_CREATED

    try:
        FramerRegistrationSubmission.objects.create(
            source=source,
            framer_submission_id=framer_submission_id or "",
            email=email,
            raw_payload=redact_framer_raw_payload(raw_payload or {}),
            parsed_payload=framer_registration_fields_for_log(parsed_fields)
            if parsed_fields
            else None,
            http_status=http_status,
            response_payload=response_payload,
            success=success,
        )
    except Exception as exc:
        print(f"Failed to record Framer registration submission: {exc}")


def build_framer_registration_submit_response(result, http_status):
    """
    Response JSON for Framer override fetch().

    Expects ``redirect_url``, ``valid``, ``hasError``, and ``message`` at the top
    level (see Framer ``submitAndValidate``).
    """
    if http_status == status.HTTP_201_CREATED:
        redirect_url = result.get("url") or result.get("redirect_url")
        return {
            "valid": True,
            "hasError": False,
            "code": "ok",
            "message": result.get("message", ""),
            "redirect_url": redirect_url,
            "url": redirect_url,
            "registration": result,
        }, http_status

    msg = (result or {}).get("message", "Registration failed.")
    body = {
        "valid": False,
        "hasError": True,
        "code": "registration_failed",
        "message": msg,
        "registration": result,
    }
    if isinstance(result, dict) and result.get("errors"):
        body["errors"] = result["errors"]
    return body, http_status


def framer_registration_email_from_request(request):
    """Email for validation: GET query param or POST body (DRF data or Framer JSON)."""
    email = None
    if request.method == "GET":
        email = request.query_params.get("email")
    elif getattr(request, "data", None) and isinstance(request.data, dict):
        email = request.data.get("email")
    else:
        payload = framer_parse_json_body(request)
        if payload is not None:
            email = _framer_payload_get(payload, "Email", "email")

    normalized = normalize_registration_fields({"email": email})
    return normalized.get("email")


def framer_parse_json_body(request):
    """Parse raw request body as JSON; None if empty or invalid."""
    try:
        body = request.body
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return None


def framer_registration_payload_from_request(request):
    """
    Registration JSON for Framer override fetch() calls (not the Framer webhook).
    Uses DRF-parsed body when available, otherwise raw JSON.
    """
    if getattr(request, "data", None) and isinstance(request.data, dict):
        return request.data
    return framer_parse_json_body(request)


def framer_verify_webhook_signature_or_none(request):
    """
    Verify Framer-Signature when secret + headers are present.
    Returns a DRF Response on failure, or None to continue.
    """
    body = request.body
    signature = request.headers.get("Framer-Signature", "")
    submission_id = request.headers.get("Framer-Webhook-Submission-Id", "")
    secret = getattr(settings, "FRAMER_WEBHOOK_SECRET", "") or ""
    if secret and signature and submission_id:
        if not is_framer_webhook_signature_valid(
            secret, submission_id, body, signature
        ):
            print("Framer: invalid signature")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    elif not secret:
        print(
            "Framer: FRAMER_WEBHOOK_SECRET not set, "
            "skipping signature verification"
        )
    return None


def submit_framer_registration_from_payload(payload):
    """
    Validate email (Framer override shape), then NotaryDash + Tolt signup.
    Returns (response_body, http_status) for FramerRegistrationSubmitView.
    """
    fields = parse_framer_registration_payload(payload)
    email_check = validate_framer_registration_email(fields.get("email"))
    if not email_check["valid"]:
        return email_check, status.HTTP_200_OK

    result, http_status = create_notary_user_from_registration_form(**fields)
    return build_framer_registration_submit_response(result, http_status)


def resolve_tolt_partner_from_ref(ref_token):
    """
    Resolve Tolt Partner from a ref tracking value (local Link DB, then Tolt API).
    """
    token = (ref_token or "").strip()
    if not token:
        return None

    qs = (
        Link.objects.filter(partner__isnull=False)
        .exclude(value__isnull=True)
        .exclude(value="")
        .select_related("partner")
        .order_by("-created_at")
    )
    link = (
        qs.filter(value=token).first()
        or qs.filter(value__iexact=token).first()
        or qs.filter(value__icontains=token).first()
    )
    if link and link.partner:
        print(f"[Framer] Partner from local Link {link.id} (ref={token})")
        return link.partner

    try:
        response = ToltService.fetch_links(param="ref", value=token, per_page=10)
        for link_data in response.get("data") or []:
            link_value = (link_data.get("value") or "").strip()
            if link_value.lower() != token.lower():
                continue
            link_obj, _ = Link.create_or_update_from_api(link_data)
            if link_obj.partner:
                print(f"[Framer] Partner from Tolt API link {link_obj.id} (ref={token})")
                return link_obj.partner

            partner_id = link_data.get("partner_id")
            if not partner_id:
                continue

            partner = Partner.objects.filter(id=partner_id).first()
            if not partner:
                partner_resp = ToltService.fetch_partner(partner_id)
                partner_payload = partner_resp.get("data") if partner_resp.get("success") else partner_resp
                if isinstance(partner_payload, dict) and partner_payload.get("id"):
                    partner, _ = Partner.create_or_update_from_api(partner_payload)

            if partner:
                link_obj.partner = partner
                link_obj.save(update_fields=["partner"])
                print(f"[Framer] Partner synced from Tolt API (ref={token}, partner={partner.id})")
                return partner
    except Exception as exc:
        print(f"[Framer] Tolt link lookup failed for ref={token}: {exc}")

    print(f"[Framer] No Tolt partner found for ref={token}")
    return None


def create_notary_user_from_registration_form(
    *,
    email,
    company,
    first_name,
    last_name,
    phone=None,
    ref=None,
    password=None,
    password_confirmation=None,
):
    """
    Create NotaryDash client + user and persist locally (Framer / direct signup).
    Returns (payload_dict, http_status).
    """
    normalized = normalize_registration_fields({
        "email": email,
        "company": company,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "ref": ref,
        "password": password,
        "password_confirmation": password_confirmation,
    })
    email = normalized["email"]
    company = normalized["company"]
    first_name = normalized["first_name"]
    last_name = normalized["last_name"]
    phone = normalized["phone"]
    ref = normalized["ref"]
    password = normalized["password"]
    password_confirmation = normalized["password_confirmation"]

    if not email:
        return {"message": "Missing email"}, status.HTTP_400_BAD_REQUEST

    email_check = validate_framer_registration_email(email)
    if not email_check["valid"]:
        if email_check.get("code") == "duplicate":
            existing_user = NotaryUser.objects.filter(email__iexact=email, deleted_at__isnull=True).first()
            if existing_user:
                company_id = existing_user.last_company_id
                user_id = existing_user.id
                return (
                    {
                        "status": "ok",
                        "message": "Account already exists",
                        "url": f"https://go.investorbootz.com/thankyou?company_id={company_id}&client_id={user_id}",
                    },
                    status.HTTP_200_OK,
                )
        return {"message": email_check["message"]}, status.HTTP_400_BAD_REQUEST

    if not company:
        return {"message": "Missing company"}, status.HTTP_400_BAD_REQUEST

    partner = resolve_tolt_partner_from_ref(ref) if ref else None

    client_payload = {"company_name": company}
    client_user_payload = build_notary_client_user_payload(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        password=password,
        password_confirmation=password_confirmation,
    )

    client_obj = NotaryClientCompany.objects.filter(company_name=company).first()
    if client_obj:
        print(f"✅ Found existing NotaryClientCompany: {client_obj.company_name} (ID: {client_obj.id})")
        client_id = client_obj.id
    else:
        client_response = NotaryDashServices.create_client(
            client_payload, retry_on_rate_limit=False
        )
        if not client_response:
            return {"message": "Failed to create client"}, status.HTTP_400_BAD_REQUEST

        client_data = client_response.get("data", {})
        client_id = client_data.get("id")
        if not client_id:
            return {"message": "No client ID returned"}, status.HTTP_400_BAD_REQUEST

        client_obj, _ = NotaryClientCompany.objects.update_or_create(
            id=client_id,
            defaults={
                "owner_id": client_data.get("owner_id"),
                "parent_company_id": client_data.get("parent_company_id"),
                "type": client_data.get("type"),
                "company_name": client_data.get("company_name"),
                "parent_company_name": client_data.get("parent_company_name"),
                "attr": client_data.get("attr", {}),
                "address": client_data.get("address", {}),
                "deleted_at": client_data.get("deleted_at"),
                "created_at": client_data.get("created_at"),
                "updated_at": client_data.get("updated_at"),
                "active": client_data.get("active", True),
            },
        )
        print(f"✅ Saved NotaryClientCompany: {client_obj}")

    if not client_obj.stripe_customer_id:
        stripe_customer = create_stripe_customer(client_obj.company_name, email=email)
        if stripe_customer:
            client_obj.stripe_customer_id = stripe_customer.id
            client_obj.save()

    user_response, user_error = NotaryDashServices.create_client_user(
        client_id=client_id,
        user_data=client_user_payload,
        retry_on_rate_limit=False,
    )
    if user_error:
        http_status = user_error.get("status_code") or status.HTTP_400_BAD_REQUEST
        return user_error, http_status

    user_data = user_response.get("data", {})
    user_id = user_data.get("id")
    last_company_id = user_data.get("last_company_id")
    company_id = last_company_id if last_company_id else client_id

    if not user_id:
        return {"message": "User creation failed"}, status.HTTP_400_BAD_REQUEST

    _, sync_err = ensure_notary_client_company_local(company_id)
    if sync_err:
        return {"message": sync_err}, status.HTTP_502_BAD_GATEWAY

    is_first_user = not NotaryUser.objects.filter(last_company_id=company_id).exists()
    full_name = " ".join(p for p in (first_name, last_name) if p).strip()

    user_defaults = {
        "first_name": user_data.get("first_name") or first_name or "",
        "last_name": user_data.get("last_name") or last_name or "",
        "name": full_name or user_data.get("name") or email,
        "email": user_data.get("email") or email,
        "photo_url": user_data.get("photo_url"),
        "country_code": user_data.get("country_code"),
        "tz": user_data.get("tz"),
        "attr": user_data.get("attr", {}),
        "last_login_at": user_data.get("last_login_at"),
        "last_ip": user_data.get("last_ip"),
        "last_company_id": company_id,
        "email_unverified": user_data.get("email_unverified"),
        "disabled": user_data.get("disabled"),
        "deleted_at": user_data.get("deleted_at"),
        "created_at": user_data.get("created_at"),
        "updated_at": user_data.get("updated_at"),
        "type": user_data.get("type"),
    }
    if partner is not None:
        user_defaults["partner_id"] = partner.id

    user_obj, _ = NotaryUser.objects.update_or_create(id=user_id, defaults=user_defaults)

    if is_first_user:
        user_obj.is_admin = True
        user_obj.save(update_fields=["is_admin"])

    if user_obj.partner_id:
        from .tasks import create_tolt_customer_for_notary_user
        create_tolt_customer_for_notary_user.delay(user_obj.id)

    print(f"✅ Saved NotaryUser from Framer: {user_obj}")

    return (
        {
            "status": "ok",
            "message": "Account Created",
            "url": f"https://go.investorbootz.com/thankyou?company_id={company_id}&client_id={user_id}",
        },
        status.HTTP_201_CREATED,
    )


class LatestTermsOfConditionsView(APIView):
    """
    Returns the latest Terms of Conditions (by updated_at).
    """

    def get(self, request, *args, **kwargs):
        latest_tos = TermsOfConditions.objects.order_by('-updated_at').first()
        if not latest_tos:
            return Response({"detail": "No Terms of Conditions found."}, status=404)
        
        user_id = request.query_params.get('user_id')
        if user_id:
            user = NotaryUser.objects.filter(id=user_id).first()
            if user and user.signed_terms.filter(id=latest_tos.id).exists():
                return Response({"signed": True})

        serializer = TermsOfConditionsSerializer(latest_tos)
        return Response(serializer.data)




@method_decorator(csrf_exempt, name='dispatch')
class TypeFormWebhook(APIView):

        def post(self, request):
 

            try:
                # print(f'Raw payload {json.dumps(request.data, indent=4)}')
                try:
                    payload = request.data
                    # print(f'Recieved Payload {json.dumps(payload, indent=4)}')
                except json.JSONDecodeError:
                    return HttpResponseBadRequest("Invalid JSON payload")

                email = None
                for ans in payload.get("form_response", {}).get("answers", []):
                    if "email" in ans:
                        email = ans["email"]
                        break
                print(f"Recieving typeform webhook with email {email}")

                resp_obj = TypeformParser.save_webhook(payload)
                
                # Check for Partner Mappings and update GHL contact
                # email = resp_obj.get_answer_by_title("Email")
                # if email:
                #     from .tasks import ghl_update_contact
                #     print(f"Triggering ghl_update_contact for {email}")
                #     ghl_update_contact(email, resp_obj.id)
                # else:
                #     print("No email found in Typeform response, skipping ghl_update_contact task.")

                return Response({"status": "ok", "response_id": resp_obj.id}, status=status.HTTP_201_CREATED) #type:ignore



            except Exception as e:
                print("Typeform Webhook Error:", e)
                return JsonResponse({"error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class FramerWebhookView(APIView):
    """
    Receives Framer form submissions (JSON POST).
    Verifies Framer-Signature when FRAMER_WEBHOOK_SECRET is configured.
    """

    authentication_classes = []
    parser_classes = []  # keep raw body intact for HMAC (do not use request.data)

    def post(self, request):
        print(f"Framer webhook signature: {request.headers.get('Framer-Signature', '')}")
        sig_err = framer_verify_webhook_signature_or_none(request)
        if sig_err:
            return sig_err

        payload = framer_parse_json_body(request)
        if payload is None:
            return Response(
                {"error": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        submission_id = request.headers.get("Framer-Webhook-Submission-Id", "")
        print(f"Framer webhook submission_id={submission_id}")
        print(f"Framer webhook payload:\n{json.dumps(payload, indent=2)}")

        parsed_fields = parse_framer_registration_payload(payload)
        try:
            result, http_status = create_notary_user_from_registration_form(
                **parsed_fields
            )
            record_framer_registration_submission(
                source=FramerRegistrationSubmission.SOURCE_WEBHOOK,
                raw_payload=payload,
                parsed_fields=parsed_fields,
                http_status=http_status,
                response_payload=result,
                framer_submission_id=submission_id,
            )
            return Response(result, status=http_status)
        except Exception as exc:
            print(f"Framer webhook processing error: {exc}")
            record_framer_registration_submission(
                source=FramerRegistrationSubmission.SOURCE_WEBHOOK,
                raw_payload=payload,
                parsed_fields=parsed_fields,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                response_payload={"error": str(exc)},
                framer_submission_id=submission_id,
            )
            return Response(
                {"error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@method_decorator(csrf_exempt, name='dispatch')
class FramerEmailValidationView(APIView):
    """
    Validates registration email for Framer form overrides (onBlur).

    GET:  /framer/validate-email/?email=user@example.com  (no request body)
    POST: JSON body { "email": "user@example.com" }
    """

    authentication_classes = []

    def get(self, request):
        return self._validate(request)

    def post(self, request):
        return self._validate(request)

    def _validate(self, request):
        result = validate_framer_registration_email(
            framer_registration_email_from_request(request)
        )
        return Response(result, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class FramerRegistrationSubmitView(APIView):
    """
    POST from Framer custom override code (fetch), not the Framer webhook.

    Accepts JSON like getFormData(): First Name, Last Name (or Name), Email,
    Phone Number, Company, Password, ref.

    When Password is present, NotaryDash receives password +
    password_confirmation and email_credentials is false.

    Responses for override ``submitAndValidate``:
    - Invalid email: 200, ``valid: false``, ``hasError: true``, ``message``
    - Success: 201, ``valid: true``, ``redirect_url`` (go.investorbootz.com URL)
    - Registration error: 4xx, ``hasError: true``, top-level ``message``
    """

    authentication_classes = []

    def post(self, request):
        payload = framer_registration_payload_from_request(request)
        if payload is None:
            return Response(
                {
                    "valid": False,
                    "hasError": True,
                    "code": "invalid_json",
                    "message": "Invalid JSON payload",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed_fields = parse_framer_registration_payload(payload)
        print(
            "Framer registration submit (override API): "
            f"{json.dumps(framer_registration_fields_for_log(parsed_fields), default=str)}"
        )

        try:
            body, http_status = submit_framer_registration_from_payload(payload)
            record_framer_registration_submission(
                source=FramerRegistrationSubmission.SOURCE_OVERRIDE,
                raw_payload=payload,
                parsed_fields=parsed_fields,
                http_status=http_status,
                response_payload=body,
            )
            return Response(body, status=http_status)
        except Exception as exc:
            print(f"Framer registration submit error: {exc}")
            error_body = {
                "valid": False,
                "hasError": True,
                "code": "server_error",
                "message": str(exc),
            }
            record_framer_registration_submission(
                source=FramerRegistrationSubmission.SOURCE_OVERRIDE,
                raw_payload=payload,
                parsed_fields=parsed_fields,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                response_payload=error_body,
            )
            return Response(
                error_body,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotaryCreationView(APIView):
    """
    Creates a client + client user on NotaryDash and stores them locally.
    """

    def post(self, request):
        data = request.data
        print(f"Received payload: {json.dumps(data, indent=4)}")
        email = data.get("email")

        # Validate email & time threshold
        time_threshold = timezone.now() - timedelta(minutes=1)
        if not email:
            return Response({"message": "Missing email"}, status=status.HTTP_400_BAD_REQUEST)

        # 1️⃣ Get recent Typeform response for this email
        email_answers = (
            TypeformAnswer.objects
            .select_related('response')
            .filter(
                answer_type='email',
                value_text=email,
                response__submitted_at__gte=time_threshold
            )
            .order_by('-response__submitted_at')
        )
        print(f"[NotaryCreationView] Time threshold: {time_threshold}")
        print(f"[NotaryCreationView] Checking answers for email: {email}")
        
        # Debug: check if any answers exist for this email regardless of time
        all_email_answers = TypeformAnswer.objects.filter(answer_type='email', value_text=email).count()
        print(f"[NotaryCreationView] Total answers for email (all time): {all_email_answers}")

        valid_answers_count = email_answers.count()
        print(f"[NotaryCreationView] Valid answers count (>= threshold): {valid_answers_count}")

        recent_responses = TypeformResponse.objects.filter(
            id__in=email_answers.values_list('response_id', flat=True)
        ).select_related('form').prefetch_related('answers__field')

        recent_response = recent_responses.first()
        if not recent_response:
            print("[NotaryCreationView] No recent Typeform response found after filtering.")
            return Response({"message": "No recent Typeform response found"}, status=status.HTTP_204_NO_CONTENT)

        print(f"Using recent response: {recent_response.id}") #type:ignore

        partner_mapping = recent_response.resolve_typeform_partner_mapping()
        if partner_mapping:
            print(
                f"[NotaryCreationView] Typeform partner mapping: "
                f"{partner_mapping.id} ({partner_mapping.choice_label})"
            )

        # Hidden ref → Tolt Link (resolve whenever hidden may carry ref).
        partner_from_hidden = recent_response.resolve_partner_from_hidden_tolt_link()
        if partner_from_hidden:
            print(
                f"[NotaryCreationView] Partner from Typeform hidden ref → "
                f"Tolt partner_id={partner_from_hidden.id}"
            )

        # partner_id: use mapping FK if set, else hidden ref; vice versa is the
        # same (one or the other). Skip only when neither yields a partner.
        partner_id_from_mapping = None
        if partner_mapping is not None:
            partner_id_from_mapping = partner_mapping.partner_id
            if partner_id_from_mapping is None:
                pmap_partner = getattr(partner_mapping, "partner", None)
                if pmap_partner is not None:
                    partner_id_from_mapping = pmap_partner.id

        partner_id_from_hidden = (
            partner_from_hidden.id if partner_from_hidden is not None else None
        )

        resolved_partner_id = partner_id_from_mapping or partner_id_from_hidden

        if resolved_partner_id is not None:
            if not partner_id_from_mapping and partner_id_from_hidden:
                print(
                    "[NotaryCreationView] partner_id from hidden only "
                    f"(mapping unset): {resolved_partner_id}"
                )
            elif (
                partner_id_from_mapping
                and partner_id_from_hidden
                and partner_id_from_mapping != partner_id_from_hidden
            ):
                print(
                    "[NotaryCreationView] mapping vs hidden differ; "
                    f"using mapping partner_id={partner_id_from_mapping}"
                )

        typeform_fields = normalize_registration_fields({
            "email": recent_response.get_answer_by_title("Email"),
            "company": recent_response.get_answer_by_title("Company"),
            "first_name": recent_response.get_answer_by_title("First name"),
            "last_name": recent_response.get_answer_by_title("Last name"),
            "phone": recent_response.get_answer_by_title("Phone number"),
        })

        client_payload = {
            "company_name": typeform_fields["company"],
        }

        client_user_payload = {
            "user": {
                "first_name": typeform_fields["first_name"],
                "last_name": typeform_fields["last_name"],
                "email": typeform_fields["email"],
                "attr": {
                    "phone": typeform_fields["phone"] or "",
                },
            },
            "email_credentials": True,
        }

        # 3️⃣ Create or Get client
        company_name_key = client_payload.get("company_name")
        client_obj = NotaryClientCompany.objects.filter(company_name=company_name_key).first()

        if client_obj:
            print(f"✅ Found existing NotaryClientCompany: {client_obj.company_name} (ID: {client_obj.id})")
            client_id = client_obj.id
        else:
            # Create client in NotaryDash
            client_response = NotaryDashServices.create_client(client_payload)
            if not client_response:
                return Response({"message": "Failed to create client"}, status=status.HTTP_400_BAD_REQUEST)

            client_data = client_response.get("data", {})
            client_id = client_data.get("id")

            if not client_id:
                return Response({"message": "No client ID returned"}, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Save NotaryClientCompany locally
            client_obj, _ = NotaryClientCompany.objects.update_or_create(
                id=client_id,
                defaults={
                    "owner_id": client_data.get("owner_id"),
                    "parent_company_id": client_data.get("parent_company_id"),
                    "type": client_data.get("type"),
                    "company_name": client_data.get("company_name"),
                    "parent_company_name": client_data.get("parent_company_name"),
                    "attr": client_data.get("attr", {}),
                    "address": client_data.get("address", {}),
                    "deleted_at": client_data.get("deleted_at"),
                    "created_at": client_data.get("created_at"),
                    "updated_at": client_data.get("updated_at"),
                    "active": client_data.get("active", True),
                }
            )

            print(f"✅ Saved NotaryClientCompany: {client_obj}")

        # Create Stripe Customer if not exists
        if not client_obj.stripe_customer_id:
            stripe_customer = create_stripe_customer(client_obj.company_name, email=email)
            if stripe_customer:
                client_obj.stripe_customer_id = stripe_customer.id
                client_obj.save()


        # 4️⃣ Create client user
        user_response, user_error = NotaryDashServices.create_client_user(
            client_id=client_id, user_data=client_user_payload
        )

        if user_error:
            return Response(user_error, status=status.HTTP_400_BAD_REQUEST)

        user_data = user_response.get("data", {})
        user_id = user_data.get("id")
        last_company_id = user_data.get("last_company_id")
        company_id = last_company_id if last_company_id else client_id

        if user_id:
            _, sync_err = ensure_notary_client_company_local(company_id)
            if sync_err:
                return Response(
                    {"message": sync_err},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Check for existing users to determine admin status
            is_first_user = not NotaryUser.objects.filter(last_company_id=company_id).exists()
            
            user_defaults = {
                "first_name": user_data.get("first_name"),
                "last_name": user_data.get("last_name"),
                "email": user_data.get("email"),
                "photo_url": user_data.get("photo_url"),
                "country_code": user_data.get("country_code"),
                "tz": user_data.get("tz"),
                "attr": user_data.get("attr", {}),
                "last_login_at": user_data.get("last_login_at"),
                "last_ip": user_data.get("last_ip"),
                "last_company_id": company_id,
                "email_unverified": user_data.get("email_unverified"),
                "disabled": user_data.get("disabled"),
                "deleted_at": user_data.get("deleted_at"),
                "created_at": user_data.get("created_at"),
                "updated_at": user_data.get("updated_at"),
                "type": user_data.get("type"),
            }
            # Link mapping row when present; always set partner_id when we
            # resolved one (mapping FK or hidden ref — partner_id is canonical).
            if partner_mapping is not None:
                user_defaults["typeform_partner_mapping"] = partner_mapping
            if resolved_partner_id is not None:
                user_defaults["partner_id"] = resolved_partner_id

            # ✅ Save NotaryUser locally
            user_obj, _ = NotaryUser.objects.update_or_create(
                id=user_id,
                defaults=user_defaults,
            )
            
            # Apply admin status if applicable and new logic dictates
            # Note: We only force it to True if they are the first user. 
            # If the user already existed and we are just updating, we usually preserve their status.
            # However, if 'is_first_user' is True, it implies NO users existed before this point for this company.
            if is_first_user:
                user_obj.is_admin = True
                user_obj.save()

            if user_obj.partner_id:
                from .tasks import create_tolt_customer_for_notary_user
                create_tolt_customer_for_notary_user.delay(user_obj.id)

            print(f"✅ Saved NotaryUser: {user_obj}")

            # 5️⃣ Return success response
            return Response(
                {
                    "message": "Account Created",
                    "url": f"https://go.investorbootz.com/?company_id={company_id}&client_id={user_id}",
                },
                status=status.HTTP_201_CREATED,
            )

        return Response({"message": "User creation failed"}, status=status.HTTP_400_BAD_REQUEST)




SERVICE_LOOKUP_CACHE_SECONDS = 15 * 60


class ServiceLookupView(APIView):
    """
    Returns the detailed service + bundle structure for a given company.
    If company_id = 'default', returns the active default variance.
    Otherwise:
      - Attempts to find a variance assigned to the company.
      - Falls back to default if none exists.

    Successful responses are cached for SERVICE_LOOKUP_CACHE_SECONDS (15 minutes).
    """

    @staticmethod
    def _service_lookup_cache_key(company_id: str) -> str:
        return f"order_page:service_lookup:v1:{company_id.strip()}"

    def get(self, request, company_id: str):
        try:
            cache_key = self._service_lookup_cache_key(company_id)
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload, status=status.HTTP_200_OK)

            # Case 1: If explicitly requesting the default
            if company_id.lower() == "default":
                variance = ServiceVariance.get_default()
                if not variance:
                    return Response(
                        {"detail": "No default active service variance found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            else:
                if not company_id:
                    return Response(
                        {"detail": "Company ID is required."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Case 2: Try to find company-specific variance
                client = get_object_or_404(NotaryClientCompany, id=company_id)

                variance = (
                    ServiceVariance.objects.filter(clients=client, is_active=True)
                    .prefetch_related("bundle_group__bundles", "service_category__services")
                    .first()
                )

                # Fallback to default
                if not variance:
                    variance = ServiceVariance.get_default()
                    if not variance:
                        return Response(
                            {"detail": "No active variance found for client or default."},
                            status=status.HTTP_404_NOT_FOUND,
                        )

            # Serialize result
            serializer = ServiceVarianceSerializer(variance)
            data = serializer.data
            cache.set(cache_key, data, SERVICE_LOOKUP_CACHE_SECONDS)
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




class GooglePlacesAutocompleteView(APIView):
    """
    Search for places using Google Places Autocomplete API.
    Validates user, caches results, and returns simplified response.
    """
    def post(self, request):
        user_id = request.data.get('user_id')
        text = request.data.get('text')
        
        if not user_id or not text:
            return Response(
                {"detail": "Both 'user_id' and 'text' are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Validate User
        if not NotaryUser.objects.filter(id=user_id).exists():
             return Response(
                {"detail": "Invalid User ID."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Check Cache
        cache_key = f"autocomplete_{text.lower().strip().replace(' ', '_')}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)
            
        # Fetch from Google
        service = GoogleService()
        result = service.get_autocomplete(text)
        
        if "error" in result:
             # Pass through Google error usually, or generic 500
             return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
             
        # Transform Response
        suggestions = []
        for item in result.get('suggestions', []):
            place_pred = item.get('placePrediction')
            if place_pred:
                suggestions.append({
                    "description": place_pred.get('text', {}).get('text'),
                    "place_id": place_pred.get('placeId')
                })
        
        # Cache the result (60 mins = 3600 seconds)
        cache.set(cache_key, suggestions, timeout=3600)
        
        return Response(suggestions)





class GooglePlaceDetailsView(APIView):
    """
    Get detailed information about a place, including parsed address and timezone.
    """
    def post(self, request):
        place_id = request.data.get('place_id')
        
        if not place_id:
            return Response(
                {"detail": "'place_id' is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        service = GoogleService()
        
        # 1. Get Place Details
        # Requesting location for timezone and addressComponents for parsing
        fields = "addressComponents,location" 
        details_result = service.get_place_details(place_id, fields=fields)
        
        if "error" in details_result:
            return Response(details_result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # 2. Parse Address
        components = details_result.get('addressComponents', [])
        location = details_result.get('location', {})
        
        address_map = {
            'street_number': '',
            'route': '',
            'locality': '',
            'administrative_area_level_1': '',
            'postal_code': '',
            'subpremise': ''
        }
        
        for comp in components:
            types = comp.get('types', [])
            for t in types:
                if t in address_map:
                    # Prefer shortText for state/administrative_area_level_1 for frontend compatibility
                    if t == 'administrative_area_level_1':
                         address_map[t] = comp.get('shortText') or comp.get('longText')
                    else:
                        address_map[t] = comp.get('longText') or comp.get('shortText')
                    
        street_address = f"{address_map['street_number']} {address_map['route']}".strip()
        
        response_data = {
            "street_address": street_address,
            "city": address_map['locality'],
            "state": address_map['administrative_area_level_1'],
            "postal_code": address_map['postal_code'],
            "unit": address_map['subpremise'],
            # Timezone fields placeholders
            "timezone_id": None,
            "timezone_name": None
        }

        # 3. Get Timezone
        lat = location.get('latitude')
        lng = location.get('longitude')
        
        if lat is not None and lng is not None:
            tz_result = service.get_timezone(lat, lng)
            if "timeZoneId" in tz_result:
                response_data["timezone_id"] = tz_result.get("timeZoneId")
                response_data["timezone_name"] = tz_result.get("timeZoneName")
        
        return Response(response_data)
