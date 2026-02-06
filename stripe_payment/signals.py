from django.dispatch import Signal

# Signal sent when a notary order is successfully created via Stripe payment flow
# Arguments:
# - notary_order: dict (the order payload sent to NotaryDash)
# - order_response: dict (the response from NotaryDash)
notary_order_created = Signal()
