from celery import shared_task
from stripe_payment.management.commands.pull_notary_company import Command as pull_companies
import logging, json

logger = logging.getLogger(__name__)

@shared_task
def example_task(arg1, arg2):
    # Your task logic here
    return arg1 + arg2

@shared_task
def sample_beat_task():
    # Logic for the periodic task
    logger.info("Sample beat task executed.")
    return "Task completed"

@shared_task
def create_order_task(order_id, user_id):
    pass

@shared_task
def pull_clients():
    p =pull_companies()
    p.handle()


# process-wide singleton: the one persistent NotaryDash web-session login,
# lazily started on first use. Only ever touched from this task, which is
# routed to the single-concurrency `notarydash_web` queue (see
# dj_IBstripe/settings.py CELERY_TASK_ROUTES) - never call this directly
# from a gunicorn worker or the default Celery queue.
_notarydash_web_session = None


def _get_notarydash_web_session():
    global _notarydash_web_session
    if _notarydash_web_session is None:
        from django.conf import settings
        from stripe_payment.notarydash_web import NDWebSession

        session = NDWebSession()
        session.login(settings.NOTARY_WEB_EMAIL, settings.NOTARY_WEB_PASS)
        _notarydash_web_session = session
    return _notarydash_web_session


@shared_task(bind=True, max_retries=1)
def notarydash_web_call(self, method, path, json_data=None):
    """
    Fallback transport for a NotaryDash API call via a real logged-in
    browser session, used when the Bearer-key API is rate-limited (see
    stripe_payment/notarydash_web.py for why this exists).

    Returns the parsed JSON response dict on success, or None on any
    failure - callers treat None exactly like a failed Bearer-key call,
    falling through to the existing retry/refund path unchanged.
    """
    try:
        session = _get_notarydash_web_session()
        return session.call(method, path, json_data)
    except Exception as e:
        logger.error(f"notarydash_web_call failed ({method} {path}): {e}")
        # drop the session so the next call re-logs-in from scratch,
        # rather than reusing a possibly-broken browser/context
        global _notarydash_web_session
        _notarydash_web_session = None
        return None


def process_tos_for_ghl(user_id: int, contact_id: int):
    from stripe_payment.models import NotaryUser
    from core.services import ContactServices
    from core.models import Contact
    notary_user = NotaryUser.objects.filter(id=user_id).first()
    last_tos = notary_user.signed_terms.order_by('-updated_at').first()
    if not notary_user:
        return
    contact_update_payload={
        "customFields": [
             {
                "id": "1gdlUMPAHflS6thKSC6U",
                "key": "contact.tos_signed_at",
                "field_value": notary_user.last_signed_at.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "yHPqdzxgyYR900Gaqs7l", 
                "key": "contact.signed_tos",
                "field_value": f"{last_tos.title} {last_tos.version_id if last_tos.version_id else last_tos.updated_at.strftime('%Y-%m-%d')}"
            },
        ]

    }
    contact = Contact.objects.filter(id=contact_id).first()
    if not contact:
        contact_data = ContactServices.get_contact("n7iGMwfy1T5lZZacxygj", contact_id)
        contact = ContactServices.save_contact(contact_data)
    if contact:
       response= ContactServices.push_contact(contact, contact_update_payload)
       print("updated contact with tos")
    
@shared_task
def check_duplicate_payment_method(customer_id, payment_intent_id):
    """
    Checks if the payment method used in the given PaymentIntent is a duplicate
    (same fingerprint) of an existing saved card for the customer.
    If so, it detaches the new one to prevent duplicates.
    Returns a string indicating the outcome for logging/debugging.
    """
    import stripe
    from .utils import list_payment_methods
    
    try:
        # 1. Retrieve the PaymentIntent
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        if not pi or not pi.payment_method:
            return "Skipped: No payment method on PaymentIntent"

        new_pm_object = pi.payment_method 

        # 2. Get the full PaymentMethod object
        if isinstance(new_pm_object, str):
            new_pm = stripe.PaymentMethod.retrieve(new_pm_object)
        else:
            new_pm = new_pm_object

        # 3. Validate it's a card with a fingerprint
        if not new_pm or not new_pm.card or not new_pm.card.fingerprint:
            return "Skipped: Payment method is not a card or missing fingerprint"

        new_fingerprint = new_pm.card.fingerprint
        existing_methods = list_payment_methods(customer_id)

        # 4. Check for duplicates
        for pm in existing_methods:
            # Skip comparing to itself
            if pm.id == new_pm.id:
                continue
            
            # Ensure existing method has a card fingerprint
            if not pm.card or not pm.card.fingerprint:
                continue

            if pm.card.fingerprint == new_fingerprint:
                print(f"⚠️ Duplicate payment method detected (Fingerprint: {new_fingerprint}). Detaching new one: {new_pm.id}, Keeping old one: {pm.id}")
                stripe.PaymentMethod.detach(new_pm.id)
                return f"Detached duplicate: {new_pm.id}"

        return "No duplicate found"

    except Exception as e:
        error_msg = f"⚠️ Error in duplicate payment method check task: {e}"
        print(error_msg)
        return error_msg


def handle_fulfillment_timeout_and_refund(order_id):
    """
    Called when order fulfillment fails after 24 hours of retries or due to a non-retryable failure.
    Retrieves the Stripe PaymentIntent (via db or looking up on Stripe), processes refund if
    amount > 0, otherwise marks the invoice metadata in Stripe as failed without a refund.
    Marks the local order processing status as failed.
    """
    import stripe
    from django.conf import settings
    from stripe_payment.models import Order
    from stripe_payment.utils import payment_intent_from_paid_invoice

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        print(f"❌ Order {order_id} not found for refund/failure processing.")
        return

    print(f"🔄 Starting refund/failure processing for Order {order.id}...")

    # 1. Try to retrieve Stripe PaymentIntent
    intent = None

    # Check order.stripe_intent_id
    if order.stripe_intent_id:
        try:
            intent = stripe.PaymentIntent.retrieve(order.stripe_intent_id)
        except Exception as e:
            print(f"Error retrieving PI from stripe_intent_id {order.stripe_intent_id}: {e}")

    # Check invoice payments list if intent is still None
    if not intent and order.invoice_id:
        try:
            invoice = stripe.Invoice.retrieve(order.invoice_id)
            pi_id = getattr(invoice, "payment_intent", None)
            if pi_id:
                intent = stripe.PaymentIntent.retrieve(pi_id)
            else:
                intent = payment_intent_from_paid_invoice(invoice)
        except Exception as e:
            print(f"Error retrieving PI from invoice {order.invoice_id}: {e}")

    # Check Checkout Session if intent is still None
    if not intent and order.stripe_session_id:
        try:
            session = stripe.checkout.Session.retrieve(order.stripe_session_id)
            pi_id = getattr(session, "payment_intent", None)
            if pi_id:
                intent = stripe.PaymentIntent.retrieve(pi_id)
        except Exception as e:
            print(f"Error retrieving PI from Checkout Session {order.stripe_session_id}: {e}")

    # 2. Process Refund or mark transaction based on Stripe PaymentIntent
    if intent:
        amount_charged = getattr(intent, "amount", 0)
        if amount_charged > 0:
            try:
                # Perform refund
                refund = stripe.Refund.create(
                    payment_intent=intent.id,
                    reason="requested_by_customer",
                    metadata={"reason": "NotaryDash Downstream Fulfillment Failure 24h Timeout"}
                )
                print(f"✅ Automated Refund Executed for Order {order.id}: {refund.id}")
            except Exception as re:
                print(f"⚠️ Critical: Failed to automatically refund PaymentIntent {intent.id}: {re}")
        else:
            # Payable amount is 0 (due to 100% discount, etc.)
            print(f"ℹ️ PaymentIntent {intent.id} has amount=0. No refund needed.")
            if order.invoice_id:
                try:
                    stripe.Invoice.modify(
                        order.invoice_id,
                        metadata={"fulfillment_status": "failed_no_refund_needed_zero_amount"}
                    )
                    print(f"✅ Stripe Invoice {order.invoice_id} marked as fulfillment failed (zero amount).")
                except Exception as ie:
                    print(f"⚠️ Failed to update Invoice metadata: {ie}")
    else:
        # PaymentIntent is None
        print(f"ℹ️ No Stripe PaymentIntent found for Order {order.id} (payable might be 0).")
        if order.invoice_id:
            try:
                stripe.Invoice.modify(
                    order.invoice_id,
                    metadata={"fulfillment_status": "failed_no_refund_needed_zero_amount"}
                )
                print(f"✅ Stripe Invoice {order.invoice_id} marked as fulfillment failed (zero amount/no PI).")
            except Exception as ie:
                print(f"⚠️ Failed to update Invoice metadata: {ie}")

    # 3. Mark the order as failed in DB
    order.processing_status = "failed"
    order.save(update_fields=["processing_status"])
    print(f"❌ Order {order.id} marked as failed in local database.")


@shared_task(bind=True, max_retries=5)
def fulfill_order_task(self, order_id, event):
    """
    Celery task that attempts to fulfill an order by calling process_order.
    Retries up to 5 times using exponential backoff, then recursively reschedules itself
    after 30 seconds if under the 24-hour limit.
    """
    import time
    from django.core.cache import cache
    from stripe_payment.models import Order
    from stripe_payment.views import process_order, PROCESS_ORDER_RETRYABLE

    print(f"Celery Fulfill Order Task: Order {order_id}, attempt {self.request.retries}")

    # Check start time in cache
    start_time_key = f"order_fulfillment_start_time:{order_id}"
    start_time = cache.get(start_time_key)
    if not start_time:
        start_time = time.time()
        cache.set(start_time_key, start_time, 26 * 60 * 60)

    # Check 24-hour limit
    if time.time() - start_time > 24 * 60 * 60:
        print(f"❌ Order {order_id} has exceeded the 24-hour fulfillment limit. Initiating refund/failure.")
        handle_fulfillment_timeout_and_refund(order_id)
        # Clean cache key on timeout
        cache.delete(start_time_key)
        return False

    try:
        order_obj = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        print(f"❌ Order {order_id} not found in database.")
        return False

    # Idempotency lock Check
    if order_obj.processing_status == "completed":
        print(f"✅ Order {order_id} already completed.")
        cache.delete(start_time_key)
        return True

    # Acquire lock by updating to 'processing'
    rows_updated = Order.objects.filter(
        id=order_id,
        processing_status__in=["pending", "failed"],
    ).update(processing_status="processing")

    if rows_updated == 0:
        print(f"⚠️ Order {order_id} is already being processed or completed. Skipping task to maintain idempotency.")
        return True

    order_obj.refresh_from_db()

    # Call the core process_order logic
    try:
        processed = process_order(event, order_obj)
    except Exception as exc:
        print(f"❌ Unexpected exception inside fulfill_order_task execution: {exc}")
        Order.objects.filter(id=order_id).update(processing_status="failed")
        raise exc

    if processed is True:
        order_obj.processing_status = "completed"
        order_obj.save(update_fields=["processing_status"])
        print(f"✅ Order {order_id} fulfilled successfully in Celery.")
        cache.delete(start_time_key)
        return True
    elif processed is PROCESS_ORDER_RETRYABLE:
        # Retryable failure
        order_obj.processing_status = "failed"
        order_obj.save(update_fields=["processing_status"])

        # Calculate backoff countdown: exponential backoff
        countdown = 5 * (2 ** self.request.retries)
        print(f"⚠️ Fulfill Order Task: NotaryDash returned retryable status. Retrying attempt {self.request.retries + 1}/5 in {countdown}s...")
        try:
            self.retry(countdown=countdown)
        except Exception as retry_exc:
            from celery.exceptions import MaxRetriesExceededError
            if isinstance(retry_exc, MaxRetriesExceededError):
                print(f"⚠️ Max 5 retries exceeded for Order {order_id}. Scheduling next recursive attempt batch in 30 seconds.")
                fulfill_order_task.apply_async(args=[order_id, event], countdown=30)
            else:
                raise retry_exc
    else:
        # Non-retryable failure
        order_obj.processing_status = "failed"
        order_obj.save(update_fields=["processing_status"])
        print(f"❌ Non-retryable error in process_order for Order {order_id}.")
        handle_fulfillment_timeout_and_refund(order_id)
        cache.delete(start_time_key)
        return False


def revoke_order_fulfillment_tasks(order_id):
    """
    Search and revoke any active, scheduled, or reserved Celery tasks for a completed order.
    """
    from celery import current_app
    try:
        inspect = current_app.control.inspect()
        
        stages = [
            ("scheduled", inspect.scheduled()),
            ("active", inspect.active()),
            ("reserved", inspect.reserved()),
        ]
        
        revoked_ids = []
        for stage_name, stage_data in stages:
            if not stage_data:
                continue
            for worker, tasks in stage_data.items():
                if not tasks:
                    continue
                for task in tasks:
                    if task.get("name") == "stripe_payment.tasks.fulfill_order_task":
                        args = task.get("args")
                        if args and len(args) > 0 and str(args[0]) == str(order_id):
                            task_id = task.get("id")
                            if task_id:
                                current_app.control.revoke(task_id, terminate=True)
                                revoked_ids.append(task_id)
                                print(f"✅ Revoked {stage_name} task {task_id} for Order {order_id}")
        return revoked_ids
    except Exception as e:
        print(f"⚠️ Error revoking Celery tasks for Order {order_id}: {e}")
        return []



