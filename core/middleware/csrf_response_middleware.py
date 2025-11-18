# core/middleware/csrf_response_middleware.py
import json
from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.deprecation import MiddlewareMixin

DEFAULT_FIELD = "csrfToken"
DEFAULT_HEADER = "X-CSRFToken"

class CsrfInjectMiddleware(MiddlewareMixin):
    """
    Ensure a CSRF token exists for the request (get_token())
    and, for GET responses with JSON content, inject a top-level
    field containing the token. Always sets X-CSRFToken header.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.field_name = getattr(settings, "CSRF_IN_RESPONSE_FIELD", DEFAULT_FIELD)
        self.header_name = getattr(settings, "CSRF_IN_RESPONSE_HEADER", DEFAULT_HEADER)
        # allow turning off payload injection if desired
        self.inject_into_payload = getattr(settings, "CSRF_IN_RESPONSE_PAYLOAD", True)
        # only for application/json content-types
        self.json_content_types = ("application/json", "application/vnd.api+json")

    def process_request(self, request):
        # Guarantee the token exists and cookie will be set by Django.
        # get_token will return existing token or create a new one.
        try:
            _ = get_token(request)
        except Exception:
            # fail silently - anything that can break token generation shouldn't
            # block normal request handling
            pass
        return None

    def process_response(self, request, response):
        # Always attach token header if available
        try:
            token = get_token(request)
        except Exception:
            token = None

        if token:
            response[self.header_name] = token

        # Only consider injecting into GET JSON responses (common SPA pattern)
        if (
            self.inject_into_payload
            and request.method.upper() == "GET"
            and token
            and response.get("Content-Type")
            and any(ct in response["Content-Type"] for ct in self.json_content_types)
        ):
            try:
                # response.content may be bytes; decode for parsing
                content = response.content.decode(response.charset or "utf-8")
                payload = json.loads(content)

                # Only modify if payload is a JSON object (dict). Avoid arrays, strings.
                if isinstance(payload, dict):
                    # don't overwrite if key exists unless configured
                    if self.field_name not in payload:
                        payload[self.field_name] = token
                    else:
                        # optional: you may choose to overwrite existing value:
                        # payload[self.field_name] = token
                        pass

                    new_content = json.dumps(payload, ensure_ascii=False)
                    response.content = new_content.encode(response.charset or "utf-8")
                    # update proper content-length header
                    if response.has_header("Content-Length"):
                        response["Content-Length"] = str(len(response.content))
            except Exception:
                # Parsing/encoding should not break the response; skip injection if any error
                pass

        return response
