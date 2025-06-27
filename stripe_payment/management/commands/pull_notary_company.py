from django.core.management.base import BaseCommand
from stripe_payment.services import NotaryDashServices
from datetime import datetime
from stripe_payment.models import NotaryClientCompany
from django.utils.timezone import make_aware
import logging

logger = logging.getLogger(__name__)



class Command(BaseCommand):
    help = "Pull Notary Company data from the Notary API and save it to the database"

    def handle(self, *args, **kwargs):
        self.stdout.write("📥 write Pulling Notary Company data from the Notary API...")
        logger.info("📥 logger Pulling Notary Company data from the Notary API...")
        print("📥 print Pulling Notary Company data from the Notary API...")
        url = None  # Start with the initial URL
        while True:
            # Fetch data from the Notary API
            response = NotaryDashServices.get_clients(url)
            if not response or "data" not in response:
                logger.info("❌ No data received from the API.")
                break

            # Save data to the NotaryClientCompany model
            for company_data in response["data"]:
                NotaryClientCompany.objects.update_or_create(
                    id=company_data["id"],
                    defaults={
                        "owner_id": company_data["owner_id"],
                        "parent_company_id": company_data["parent_company_id"],
                        "type": company_data["type"],
                        "company_name": company_data["company_name"].strip(),
                        "parent_company_name": company_data.get("parent_company_name"),
                        "attr": company_data["attr"],
                        "address": company_data.get("address"),
                        "deleted_at": make_aware(datetime.strptime(company_data["deleted_at"], "%Y-%m-%d %H:%M:%S")) if company_data["deleted_at"] else None,
                        "created_at": make_aware(datetime.strptime(company_data["created_at"], "%Y-%m-%d %H:%M:%S")),
                        "updated_at": make_aware(datetime.strptime(company_data["updated_at"], "%Y-%m-%d %H:%M:%S")),
                        "active": company_data["active"],
                    }
                )

            logger.info(f"✅ Saved {len(response['data'])} companies.")

            # Check for the next page URL
            url = response.get("links", {}).get("next")
            if not url:
                logger.info("🚀 All pages processed.")
                break

