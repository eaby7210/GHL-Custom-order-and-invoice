from django.core.management.base import BaseCommand
from stripe_payment.services import NotaryDashServices
from datetime import datetime
from stripe_payment.models import NotaryClientCompany, NotaryUser
from django.utils.timezone import make_aware

class Command(BaseCommand):
    help = "Pull Notary User data from the Notary API and save it to the database"

    def handle(self, *args, **kwargs):
        self.stdout.write("📥 Pulling Notary User data from the Notary API...")
        notary_clients = NotaryClientCompany.objects.all()
        for notary_client in notary_clients:
            self.stdout.write(f"Processing Notary Client: {notary_client.company_name} (ID: {notary_client.id})")
            url = None
            while True:
                # Fetch user data from the Notary API
                response = NotaryDashServices.get_client_user(notary_client.id, url)
                if not response or "data" not in response:
                    self.stdout.write(f"❌ No data received for client {notary_client.id}.")
                    break

                # Save user data to the NotaryUser model
                for user_data in response["data"]:
                    NotaryUser.objects.update_or_create(
                        id=user_data["id"],
                        defaults={
                            "last_company": notary_client,
                            "email": user_data["email"],
                            "first_name": user_data["first_name"],
                            "last_name": user_data["last_name"],
                            "attr": user_data.get("attr", {}),
                            "disabled": user_data.get("disabled"),
                            "type": user_data.get("type"),
                            "country_code": user_data.get("country_code"),
                            "tz": user_data.get("tz"),
                            "created_at": make_aware(datetime.strptime(user_data["created_at"], "%Y-%m-%d %H:%M:%S")),
                            "updated_at": make_aware(datetime.strptime(user_data["updated_at"], "%Y-%m-%d %H:%M:%S")),
                        }
                    )

                self.stdout.write(f"✅ Saved {len(response['data'])} users for client {notary_client.id}.")

                # Check for the next page URL
                url = response.get("links", {}).get("next")
                if not url:
                    self.stdout.write("🚀 All pages processed.")
                    break