from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from requests.exceptions import RequestException

from stripe_payment.services import NotaryDashServices


class NotaryDashRateLimitTests(TestCase):
    """
    create_order/create_products used to retry-with-sleep on 429 (up to
    30+60+120+120+120=470s) from inside synchronous request handlers
    (Stripe webhook, m2m views) - that can exceed gunicorn's worker timeout
    and get the worker killed mid-request, before the caller's own
    PROCESS_ORDER_RETRYABLE -> fulfill_order_task fallback ever runs.
    They must fail fast on 429 instead and let that fallback own retries.
    """

    @patch("stripe_payment.services.post_with_retry")
    def test_create_order_fails_fast_on_rate_limit(self, mock_post):
        mock_post.return_value = None
        NotaryDashServices.create_order({"client_id": 1})
        self.assertFalse(mock_post.call_args.kwargs.get("retry_on_rate_limit", True))

    @patch("stripe_payment.services.post_with_retry")
    def test_create_products_fails_fast_on_rate_limit(self, mock_post):
        mock_post.return_value = None
        NotaryDashServices.create_products({"client_id": 1})
        self.assertFalse(mock_post.call_args.kwargs.get("retry_on_rate_limit", True))


class NotaryDashWebFallbackTests(TestCase):
    """
    Web-session fallback (approved by NotaryDash as a stopgap for their own
    API-metering bug) must be a no-op when the flag is off - byte-identical
    to today's behavior - and only attempted after the Bearer-key call has
    already failed.
    """

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=False)
    def test_try_web_fallback_noop_when_flag_off(self):
        from stripe_payment.services import _try_web_fallback

        with patch("stripe_payment.tasks.notarydash_web_call") as mock_task:
            result = _try_web_fallback("GET", "/api/v2/clients/1")
        mock_task.apply_async.assert_not_called()
        self.assertIsNone(result)

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    def test_try_web_fallback_calls_task_when_flag_on(self):
        from stripe_payment.services import _try_web_fallback

        with patch("stripe_payment.tasks.notarydash_web_call") as mock_task:
            mock_task.apply_async.return_value.get.return_value = {"data": {"id": 1}}
            result = _try_web_fallback("GET", "/api/v2/clients/1")
        mock_task.apply_async.assert_called_once_with(
            args=["GET", "/api/v2/clients/1", None]
        )
        self.assertEqual(result, {"data": {"id": 1}})

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    def test_try_web_fallback_swallows_exceptions(self):
        from stripe_payment.services import _try_web_fallback

        with patch("stripe_payment.tasks.notarydash_web_call") as mock_task:
            mock_task.apply_async.return_value.get.side_effect = TimeoutError()
            result = _try_web_fallback("GET", "/api/v2/clients/1")
        self.assertIsNone(result)

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_uses_fallback_on_429(self, mock_get, mock_fallback):
        mock_get.return_value = MagicMock(status_code=429)
        mock_fallback.return_value = {"data": {"id": 1}}

        body, err = NotaryDashServices.get_client_once("1")

        mock_fallback.assert_called_once_with("GET", "/api/v2/clients/1")
        self.assertEqual(body, {"data": {"id": 1}})
        self.assertIsNone(err)

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_falls_through_when_fallback_fails(self, mock_get, mock_fallback):
        mock_get.return_value = MagicMock(status_code=429)
        mock_fallback.return_value = None

        body, err = NotaryDashServices.get_client_once("1")

        self.assertIsNone(body)
        self.assertEqual(err, "rate_limited")

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.requests.get")
    @patch("stripe_payment.services.cache")
    def test_get_client_one_user_once_uses_fallback_on_429(self, mock_cache, mock_get, mock_fallback):
        mock_cache.get.return_value = None
        mock_get.return_value = MagicMock(status_code=429)
        mock_fallback.return_value = {"data": {"id": 1}}

        body, err = NotaryDashServices.get_client_one_user_once(1, 2)

        mock_fallback.assert_called_once_with("GET", "/api/v2/clients/1/users/2")
        self.assertEqual(body, {"data": {"id": 1}})
        self.assertIsNone(err)

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.post_with_retry")
    def test_create_order_uses_fallback_when_bearer_call_fails(self, mock_post, mock_fallback):
        mock_post.return_value = None
        mock_fallback.return_value = {"data": {"id": 1, "order_id": 99}}

        result = NotaryDashServices.create_order({"client_id": 1})

        mock_fallback.assert_called_once_with("POST", "/api/v2/orders", {"client_id": 1})
        self.assertEqual(result, {"data": {"id": 1, "order_id": 99}})

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.post_with_retry")
    def test_create_products_uses_fallback_when_bearer_call_fails(self, mock_post, mock_fallback):
        mock_post.return_value = None
        mock_fallback.return_value = {"data": {"id": 5}}

        result = NotaryDashServices.create_products({"client_id": 1})

        mock_fallback.assert_called_once_with(
            "POST", "/api/v2/companies/1/products", {"client_id": 1}
        )
        self.assertEqual(result, {"data": {"id": 5}})

    # --- remaining branches: success paths, cache, and every failure kind
    # that doesn't involve the fallback at all - closing out full coverage
    # of the four wrapped functions, not just the fallback-specific paths ---

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=False)
    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_429_flag_off_never_touches_fallback_task(self, mock_get):
        mock_get.return_value = MagicMock(status_code=429)
        with patch("stripe_payment.tasks.notarydash_web_call") as mock_task:
            body, err = NotaryDashServices.get_client_once("1")
        mock_task.apply_async.assert_not_called()
        self.assertIsNone(body)
        self.assertEqual(err, "rate_limited")

    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_network_error(self, mock_get):
        mock_get.side_effect = RequestException("boom")
        body, err = NotaryDashServices.get_client_once("1")
        self.assertIsNone(body)
        self.assertEqual(err, "error")

    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_success(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": {"id": 1}})
        body, err = NotaryDashServices.get_client_once("1")
        self.assertEqual(body, {"data": {"id": 1}})
        self.assertIsNone(err)

    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_invalid_json(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("bad json")
        mock_get.return_value = resp
        body, err = NotaryDashServices.get_client_once("1")
        self.assertIsNone(body)
        self.assertEqual(err, "error")

    @patch("stripe_payment.services.requests.get")
    def test_get_client_once_other_error_status(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        body, err = NotaryDashServices.get_client_once("1")
        self.assertIsNone(body)
        self.assertEqual(err, "error")

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.requests.get")
    @patch("stripe_payment.services.cache")
    def test_get_client_one_user_once_falls_through_when_fallback_fails(self, mock_cache, mock_get, mock_fallback):
        mock_cache.get.return_value = None
        mock_get.return_value = MagicMock(status_code=429)
        mock_fallback.return_value = None
        body, err = NotaryDashServices.get_client_one_user_once(1, 2)
        self.assertIsNone(body)
        self.assertEqual(err, "rate_limited")

    @patch("stripe_payment.services.cache")
    def test_get_client_one_user_once_cache_hit(self, mock_cache):
        mock_cache.get.return_value = {"data": {"id": 2}}
        body, err = NotaryDashServices.get_client_one_user_once(1, 2)
        self.assertEqual(body, {"data": {"id": 2}})
        self.assertIsNone(err)

    @patch("stripe_payment.services.cache")
    @patch("stripe_payment.services.requests.get")
    def test_get_client_one_user_once_network_error(self, mock_get, mock_cache):
        mock_cache.get.return_value = None
        mock_get.side_effect = RequestException("boom")
        body, err = NotaryDashServices.get_client_one_user_once(1, 2)
        self.assertIsNone(body)
        self.assertEqual(err, "error")

    @patch("stripe_payment.services.cache")
    @patch("stripe_payment.services.requests.get")
    def test_get_client_one_user_once_success(self, mock_get, mock_cache):
        mock_cache.get.return_value = None
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": {"id": 2}})
        body, err = NotaryDashServices.get_client_one_user_once(1, 2)
        self.assertEqual(body, {"data": {"id": 2}})
        self.assertIsNone(err)

    @patch("stripe_payment.services.cache")
    @patch("stripe_payment.services.requests.get")
    def test_get_client_one_user_once_invalid_json(self, mock_get, mock_cache):
        mock_cache.get.return_value = None
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("bad json")
        mock_get.return_value = resp
        body, err = NotaryDashServices.get_client_one_user_once(1, 2)
        self.assertIsNone(body)
        self.assertEqual(err, "error")

    @patch("stripe_payment.services.cache")
    @patch("stripe_payment.services.requests.get")
    def test_get_client_one_user_once_other_error_status(self, mock_get, mock_cache):
        mock_cache.get.return_value = None
        mock_get.return_value = MagicMock(status_code=500)
        body, err = NotaryDashServices.get_client_one_user_once(1, 2)
        self.assertIsNone(body)
        self.assertEqual(err, "error")

    @patch("stripe_payment.services.post_with_retry")
    def test_create_order_success_first_try_no_fallback(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"data": {"id": 1, "order_id": 99}}
        )
        with patch("stripe_payment.services._try_web_fallback") as mock_fallback:
            result = NotaryDashServices.create_order({"client_id": 1})
        mock_fallback.assert_not_called()
        self.assertEqual(result, {"data": {"id": 1, "order_id": 99}})

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.post_with_retry")
    def test_create_order_fallback_also_fails_returns_none(self, mock_post, mock_fallback):
        mock_post.return_value = None
        mock_fallback.return_value = None
        result = NotaryDashServices.create_order({"client_id": 1})
        self.assertIsNone(result)

    @patch("stripe_payment.services.post_with_retry")
    def test_create_products_success_first_try_no_fallback(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"data": {"id": 5}})
        with patch("stripe_payment.services._try_web_fallback") as mock_fallback:
            result = NotaryDashServices.create_products({"client_id": 1})
        mock_fallback.assert_not_called()
        self.assertEqual(result, {"data": {"id": 5}})

    @override_settings(NOTARYDASH_WEB_FALLBACK_ENABLED=True)
    @patch("stripe_payment.services._try_web_fallback")
    @patch("stripe_payment.services.post_with_retry")
    def test_create_products_fallback_also_fails_returns_none(self, mock_post, mock_fallback):
        mock_post.return_value = None
        mock_fallback.return_value = None
        result = NotaryDashServices.create_products({"client_id": 1})
        self.assertIsNone(result)


class NDWebSessionTests(TestCase):
    """
    Direct tests of NDWebSession's _impl methods (the actual logic, run
    inside the executor thread in production) - bypassing __init__'s real
    Playwright browser launch and the thread-submission wrappers, since
    those are trivial delegation with nothing worth re-testing.
    """

    def _session(self):
        from stripe_payment.notarydash_web import NDWebSession

        session = NDWebSession.__new__(NDWebSession)
        session.page = MagicMock()
        session.context = MagicMock()
        session._email = "admin@example.com"
        session._password = "secret"
        return session

    def test_login_impl_success(self):
        from stripe_payment.notarydash_web import LoginFailed

        session = self._session()
        session.page.url = "https://orders.investorbootz.com/orders"
        session.context.cookies.return_value = [
            {"name": "nd_token", "value": "t"},
            {"name": "nd_session", "value": "s"},
        ]
        try:
            session._login_impl("a@b.com", "pw")
        except LoginFailed:
            self.fail("_login_impl raised LoginFailed on a valid session")

    def test_login_impl_password_expired(self):
        from stripe_payment.notarydash_web import LoginFailed

        session = self._session()
        session.page.url = "https://orders.investorbootz.com/password/expired"
        with self.assertRaises(LoginFailed):
            session._login_impl("a@b.com", "pw")

    def test_login_impl_missing_session_cookies(self):
        from stripe_payment.notarydash_web import LoginFailed

        session = self._session()
        session.page.url = "https://orders.investorbootz.com/orders"
        session.context.cookies.return_value = []
        with self.assertRaises(LoginFailed):
            session._login_impl("a@b.com", "pw")

    def test_headers_includes_decoded_xsrf_token(self):
        session = self._session()
        session.context.cookies.return_value = [
            {"name": "XSRF-TOKEN", "value": "abc%3Ddef"},
        ]
        headers = session._headers()
        self.assertEqual(headers["x-xsrf-token"], "abc=def")
        self.assertEqual(headers["x-requested-with"], "XMLHttpRequest")

    def test_headers_no_xsrf_cookie(self):
        session = self._session()
        session.context.cookies.return_value = []
        headers = session._headers()
        self.assertEqual(headers["x-xsrf-token"], "")

    def test_request_impl_dispatches_get_post_put(self):
        session = self._session()
        session.context.cookies.return_value = []

        session._request_impl("GET", "/api/v2/clients/1")
        session.page.request.get.assert_called_once()

        session._request_impl("POST", "/api/v2/orders", {"a": 1})
        session.page.request.post.assert_called_once()

        session._request_impl("PUT", "/api/v2/orders/1/status", {"status": "cancelled"})
        session.page.request.put.assert_called_once()

    def test_request_impl_unsupported_method_raises(self):
        session = self._session()
        session.context.cookies.return_value = []
        with self.assertRaises(ValueError):
            session._request_impl("DELETE", "/api/v2/orders/1")

    def test_call_impl_success(self):
        session = self._session()
        session.context.cookies.return_value = []
        session.page.request.get.return_value = MagicMock(status=200, json=lambda: {"data": {}})
        result = session._call_impl("GET", "/api/v2/clients/1")
        self.assertEqual(result, {"data": {}})

    def test_call_impl_401_relogs_in_and_retries_once(self):
        session = self._session()
        session.context.cookies.return_value = [
            {"name": "nd_token", "value": "t"},
            {"name": "nd_session", "value": "s"},
        ]
        session.page.url = "https://orders.investorbootz.com/orders"
        session.page.request.get.side_effect = [
            MagicMock(status=401),
            MagicMock(status=200, json=lambda: {"data": {"ok": True}}),
        ]
        result = session._call_impl("GET", "/api/v2/clients/1")
        self.assertEqual(result, {"data": {"ok": True}})
        self.assertEqual(session.page.request.get.call_count, 2)

    def test_call_impl_401_after_retry_gives_up(self):
        session = self._session()
        session.context.cookies.return_value = [
            {"name": "nd_token", "value": "t"},
            {"name": "nd_session", "value": "s"},
        ]
        session.page.url = "https://orders.investorbootz.com/orders"
        session.page.request.get.return_value = MagicMock(status=401)
        result = session._call_impl("GET", "/api/v2/clients/1")
        self.assertIsNone(result)
        self.assertEqual(session.page.request.get.call_count, 2)

    def test_call_impl_other_error_status(self):
        session = self._session()
        session.context.cookies.return_value = []
        session.page.request.get.return_value = MagicMock(status=500)
        result = session._call_impl("GET", "/api/v2/clients/1")
        self.assertIsNone(result)

    def test_call_impl_invalid_json(self):
        session = self._session()
        session.context.cookies.return_value = []
        resp = MagicMock(status=200)
        resp.json.side_effect = ValueError("bad json")
        session.page.request.get.return_value = resp
        result = session._call_impl("GET", "/api/v2/clients/1")
        self.assertIsNone(result)

    def test_close_impl_stops_playwright_even_if_browser_close_raises(self):
        session = self._session()
        session.browser = MagicMock()
        session.browser.close.side_effect = RuntimeError("already closed")
        session._playwright = MagicMock()
        with self.assertRaises(RuntimeError):
            session._close_impl()
        session._playwright.stop.assert_called_once()

    def test_close_impl_normal(self):
        session = self._session()
        session.browser = MagicMock()
        session._playwright = MagicMock()
        session._close_impl()
        session.browser.close.assert_called_once()
        session._playwright.stop.assert_called_once()


class NotaryDashWebCallTaskTests(TestCase):
    """
    The Celery task + singleton that owns the one persistent NotaryDash web
    session (stripe_payment/tasks.py). Runs eagerly in tests (no real
    Celery worker), NDWebSession itself is mocked out entirely.
    """

    def setUp(self):
        import stripe_payment.tasks as tasks_module
        self._tasks_module = tasks_module
        tasks_module._notarydash_web_session = None

    def tearDown(self):
        self._tasks_module._notarydash_web_session = None

    @patch("stripe_payment.notarydash_web.NDWebSession")
    def test_session_created_once_and_reused(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        first = self._tasks_module._get_notarydash_web_session()
        second = self._tasks_module._get_notarydash_web_session()

        mock_cls.assert_called_once()
        mock_instance.login.assert_called_once()
        self.assertIs(first, second)

    @patch("stripe_payment.notarydash_web.NDWebSession")
    def test_notarydash_web_call_success(self, mock_cls):
        mock_instance = MagicMock()
        mock_instance.call.return_value = {"data": {"id": 1}}
        mock_cls.return_value = mock_instance

        result = self._tasks_module.notarydash_web_call("GET", "/api/v2/clients/1")

        self.assertEqual(result, {"data": {"id": 1}})
        mock_instance.call.assert_called_once_with("GET", "/api/v2/clients/1", None)

    @patch("stripe_payment.notarydash_web.NDWebSession")
    def test_notarydash_web_call_exception_resets_singleton(self, mock_cls):
        mock_instance = MagicMock()
        mock_instance.call.side_effect = RuntimeError("session died")
        mock_cls.return_value = mock_instance

        result = self._tasks_module.notarydash_web_call("GET", "/api/v2/clients/1")

        self.assertIsNone(result)
        self.assertIsNone(self._tasks_module._notarydash_web_session)
