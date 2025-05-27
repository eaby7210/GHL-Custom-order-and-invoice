from django.core.management.base import BaseCommand
from core.services import UserServices
import json

class Command(BaseCommand):
    help = "Fetch users from GoHighLevel API and store them in the database."

    # def add_arguments(self, parser):
    #     parser.add_argument('--query', type=str, help='Optional query to filter contacts')

    def handle(self, *args, **kwargs):
        # query = kwargs.get('query')
        try:
            result = UserServices.pull_users()
            self.stdout.write(self.style.SUCCESS(json.dumps(result,indent=4)))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))