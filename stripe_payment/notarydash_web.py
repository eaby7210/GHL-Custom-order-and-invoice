"""
Fallback transport for NotaryDash's API: a real logged-in browser session
against orders.investorbootz.com, used when the Bearer-key API is
rate-limited. Confirmed this is on a *separate* rate-limit bucket from the
API key, and NotaryDash has approved this as a stopgap while they fix a bug
in their own API-call metering.

Every endpoint we need has an identical path and JSON shape on both
app.notarydash.com (Bearer key) and orders.investorbootz.com (cookie
session) - only the auth mechanism and base URL differ. So this module is
just a thin transport: same `data` dicts already built for the Bearer calls
get reposted here unchanged.

Plain `requests` never gets the `nd_token` cookie the API needs - it's
gated behind a bot-detection check that only a real browser satisfies
(confirmed: Playwright login gets it, plain HTTP session replay doesn't).

Playwright's sync API must run in one dedicated thread for its whole
lifetime (its objects aren't safe to touch from other threads, and running
it inline poisons the calling thread's asyncio state - confirmed this
breaks Django's ORM with SynchronousOnlyOperation). This module is only
ever imported/used from the single-concurrency `notarydash_web` Celery
queue (see tasks.notarydash_web_call) - never call NDWebSession directly
from a gunicorn worker or the default Celery queue.
"""
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

ORDERS_BASE = "https://orders.investorbootz.com"


class LoginFailed(Exception):
    pass


class NDWebSession:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._executor.submit(self._init_browser).result()

    # --- everything below runs inside the single worker thread ---

    def _init_browser(self):
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            channel="chromium-headless-shell", headless=True
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def _login_impl(self, email, password):
        self.page.goto(f"{ORDERS_BASE}/login", wait_until="networkidle")
        self.page.fill('input[name="email"]', email)
        self.page.fill('input[name="password"]', password)
        with self.page.expect_navigation(wait_until="networkidle"):
            self.page.click('button[type="submit"]')

        if "password/expired" in self.page.url:
            raise LoginFailed(
                "NotaryDash web account's password has expired - needs a "
                "manual login in a real browser once to clear it."
            )

        cookies = self.context.cookies()
        names = {c["name"] for c in cookies}
        if "nd_token" not in names or "nd_session" not in names:
            raise LoginFailed(
                "Login did not establish a session - check "
                "NOTARY_WEB_EMAIL/NOTARY_WEB_PASS."
            )

    def _headers(self):
        cookies = self.context.cookies()
        xsrf_val = next((c["value"] for c in cookies if c["name"] == "XSRF-TOKEN"), None)
        return {
            "x-xsrf-token": urllib.parse.unquote(xsrf_val) if xsrf_val else "",
            "x-requested-with": "XMLHttpRequest",
            "accept": "application/json",
            "content-type": "application/json;charset=UTF-8",
        }

    def _request_impl(self, method, path, json_data=None):
        url = f"{ORDERS_BASE}{path}"
        headers = self._headers()
        if method == "GET":
            resp = self.page.request.get(url, headers=headers)
        elif method == "POST":
            resp = self.page.request.post(url, headers=headers, data=json.dumps(json_data or {}))
        elif method == "PUT":
            resp = self.page.request.put(url, headers=headers, data=json.dumps(json_data or {}))
        else:
            raise ValueError(f"Unsupported method: {method}")
        return resp

    def _call_impl(self, method, path, json_data=None, _retried=False):
        resp = self._request_impl(method, path, json_data)

        if resp.status == 401 and not _retried:
            # session/cookie likely expired - re-login once and retry
            self._login_impl(self._email, self._password)
            return self._call_impl(method, path, json_data, _retried=True)

        if 200 <= resp.status < 300:
            try:
                return resp.json()
            except Exception:
                return None
        return None

    def _close_impl(self):
        try:
            self.browser.close()
        finally:
            self._playwright.stop()

    # --- public API: submit to the worker thread, block for the result ---

    def login(self, email, password):
        self._email = email
        self._password = password
        return self._executor.submit(self._login_impl, email, password).result()

    def call(self, method, path, json_data=None):
        return self._executor.submit(self._call_impl, method, path, json_data).result()

    def close(self):
        try:
            self._executor.submit(self._close_impl).result()
        finally:
            self._executor.shutdown(wait=False)
