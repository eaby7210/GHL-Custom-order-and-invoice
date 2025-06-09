from django.apps import AppConfig


class StripePaymentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stripe_payment'
    
    def ready(self):
        import stripe_payment.tasks
