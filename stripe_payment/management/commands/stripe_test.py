from django.core.management.base import BaseCommand
from stripe_payment.models import NotaryUser, NotaryClientCompany
from stripe_payment.utils import list_payment_methods
import json

class Command(BaseCommand):
    help = 'Test script to fetch payment methods for a user'

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int, help='NotaryUser ID')

    def handle(self, *args, **options):
        user_id = options['user_id']
        try:
            user = NotaryUser.objects.get(id=user_id)
            self.stdout.write(self.style.SUCCESS(f"Found User: {user.id} - {user.email}"))
            
            if not user.last_company:
                self.stdout.write(self.style.ERROR(f"User {user_id} has no last_company association."))
                return

            company = user.last_company
            self.stdout.write(f"Company: {company.company_name} (ID: {company.id})")
            
            if not company.stripe_customer_id:
                self.stdout.write(self.style.ERROR(f"Company {company.id} has no Stripe Customer ID."))
                return
            
            customer_id = company.stripe_customer_id
            self.stdout.write(f"Stripe Customer ID: {customer_id}")
            
            methods = list_payment_methods(customer_id)
            self.stdout.write(self.style.SUCCESS(f"Found {len(methods)} payment methods:"))
            
            for pm in methods:
                 self.stdout.write(json.dumps(pm, indent=4, default=str))
                 self.stdout.write("-" * 40)

        except NotaryUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"NotaryUser with ID {user_id} not found."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
