from django.core.management.base import BaseCommand
from stripe_payment.models import NotaryClientCompany
import stripe
from django.conf import settings

class Command(BaseCommand):
    help = 'Removes duplicate Stripe payment methods (cards) for all customers based on fingerprint.'

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Filter companies that have a stripe_customer_id
        companies = NotaryClientCompany.objects.filter(stripe_customer_id__isnull=False).exclude(stripe_customer_id='')
        
        total_companies = companies.count()
        self.stdout.write(f"Starting duplicate card cleanup for {total_companies} companies...")

        for company in companies:
            # self.stdout.write(f"Checking company: {company.company_name} ({company.stripe_customer_id})")
            try:
                # List all card payment methods
                payment_methods = stripe.PaymentMethod.list(
                    customer=company.stripe_customer_id,
                    type="card",
                    limit=100 
                )
                
                # Group by fingerprint
                fingerprints = {}
                # Using auto_paging_iter to ensure we get all if > 100 (though unlikely for individual customer)
                for pm in payment_methods.auto_paging_iter():
                    if not pm.card or not pm.card.fingerprint:
                        continue
                        
                    fp = pm.card.fingerprint
                    if fp not in fingerprints:
                        fingerprints[fp] = []
                    fingerprints[fp].append(pm)
                
                duplicates_found = False
                
                for fp, pms in fingerprints.items():
                    if len(pms) > 1:
                        duplicates_found = True
                        self.stdout.write(f"[{company.company_name}] Found {len(pms)} cards with fingerprint {fp}")
                        
                        # Determine which one to keep
                        keeper = None
                        default_pm_id = company.stripe_default_payment_method

                        # 1. Prefer the one marked as default in our DB (or Stripe's default if we checked that)
                        for pm in pms:
                            if pm.id == default_pm_id:
                                keeper = pm
                                break
                        
                        # 2. If no default match, prefer the Oldest one (assumed to be the original)
                        if not keeper:
                             # Sort by created timestamp ascending (oldest first)
                             pms.sort(key=lambda x: x.created)
                             keeper = pms[0]
                        
                        self.stdout.write(f"   -> Keeping: {keeper.id} (Created: {keeper.created})")
                        
                        for pm in pms:
                            if pm.id != keeper.id:
                                self.stdout.write(f"   -> Detaching: {pm.id}")
                                try:
                                    stripe.PaymentMethod.detach(pm.id)
                                except Exception as e:
                                    self.stderr.write(f"   -> ❌ Error detaching {pm.id}: {e}")

            except Exception as e:
                self.stderr.write(f"Error processing company {company.id} - {company.company_name}: {e}")

        self.stdout.write(self.style.SUCCESS('Duplicate card cleanup completed.'))
