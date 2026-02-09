class WebhookEventKeys:

    TEST_EVENT = "test.event"
    # Notary Order Events
    NOTARY_ORDER_CREATED = "notary_dash.order_created"
    
    # Order Events
    ORDER_CREATED = "order.created"
    # Dynamic Order Status Events
    # These correspond to the Processing Status choices in Order model
    ORDER_PENDING = "order.pending"
    ORDER_PROCESSING = "order.processing"
    ORDER_COMPLETED = "order.completed"
    ORDER_FAILED = "order.failed"
    
    # Notary Client Company Events
    NOTARY_CLIENT_COMPANY_CREATED = "notary_dash.client_company_created"
    NOTARY_CLIENT_COMPANY_UPDATED = "notary_dash.client_company_updated"
    
    # Notary User Events
    NOTARY_USER_CREATED = "notary_dash.user_created"
    NOTARY_USER_UPDATED = "notary_dash.user_updated"

    @staticmethod
    def get_order_event(status):
        """Returns the event name for a given order processing status."""
        return f"order.{status}"

WEBHOOK_EVENT_DESCRIPTIONS = {
    WebhookEventKeys.NOTARY_ORDER_CREATED: "Triggered when a notary order is successfully created.Response from NotaryDash",
    WebhookEventKeys.ORDER_CREATED: "Triggered when a new Order is created. Detailed data from Database",
    WebhookEventKeys.ORDER_PENDING: "Triggered when an Order status changes to pending.",
    WebhookEventKeys.ORDER_PROCESSING: "Triggered when an Order status changes to processing.",
    WebhookEventKeys.ORDER_COMPLETED: "Triggered when an Order is successfully completed.After Generating Order Invoice",
    WebhookEventKeys.ORDER_FAILED: "Triggered when an Order fails processing.",
    WebhookEventKeys.NOTARY_CLIENT_COMPANY_CREATED: "Triggered when a new Notary Client Company is created.",
    WebhookEventKeys.NOTARY_CLIENT_COMPANY_UPDATED: "Triggered when a Notary Client Company details are updated.",
    WebhookEventKeys.NOTARY_USER_CREATED: "Triggered when a new Notary User is created.",
    WebhookEventKeys.NOTARY_USER_UPDATED: "Triggered when a Notary User details are updated.",
    WebhookEventKeys.TEST_EVENT:"Test Event."
}
