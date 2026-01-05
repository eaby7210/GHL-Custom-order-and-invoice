from django.core.management.base import BaseCommand
from stripe_payment.models import NotaryUser, NotaryClientCompany

class Command(BaseCommand):
    help = 'Promotes the oldest user in each company to admin status.'

    def handle(self, *args, **options):
        companies = NotaryClientCompany.objects.all()
        count = 0
        
        for company in companies:
            # Find users belonging to this company
            users = NotaryUser.objects.filter(last_company=company).order_by('created_at')
            
            if users.exists():
                oldest_user = users.first()
                if not oldest_user.is_admin:
                    oldest_user.is_admin = True
                    oldest_user.save()
                    self.stdout.write(self.style.SUCCESS(f'Promoted {oldest_user} (ID: {oldest_user.id}) to admin for company {company.company_name}'))
                    count += 1
                else:
                    self.stdout.write(f'User {oldest_user} is already admin for company {company.company_name}')
            else:
                self.stdout.write(self.style.WARNING(f'No users found for company {company.company_name}'))

        self.stdout.write(self.style.SUCCESS(f'Successfully processed {companies.count()} companies. Promoted {count} users.'))
