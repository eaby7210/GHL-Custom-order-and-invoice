from django.core.management.base import BaseCommand
from stripe_payment.models import Order
from stripe_payment.serializer import OrderSerializer
from core.services import KeapSocketService
import json

class Command(BaseCommand):
    help = 'Push an order to Keap Sync Service'

    def add_arguments(self, parser):
        parser.add_argument('order_id', type=str, help='UUID of the Order')

    def handle(self, *args, **options):
        order_id = options['order_id']
        
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Order {order_id} not found'))
            return

        serializer = OrderSerializer(order)
        data = serializer.data
        
        self.stdout.write(f"Pushing Order {order_id} to Keap...")
        
        # Assume endpoint is 'sync-order' or similar - adjusting based on generic requirement
        # If user didn't specify endpoint, we'll use root or a default.
        # Let's assume the receiving service listens on root or specific path.
        # Using 'order' as endpoint for now.
        print(f"DEBUG: Payload being sent:\n{json.dumps(data, indent=2)}")
        
        response = KeapSocketService.send_data("gsync/unix-test/", data)
        
        if response and "error" not in response:
            self.stdout.write(self.style.SUCCESS(f'Successfully pushed order. Response: {response}'))
        else:
             self.stdout.write(self.style.ERROR(f'Failed to push order. Response: {response}'))
