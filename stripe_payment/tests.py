from unittest.mock import patch

from django.test import TestCase

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
