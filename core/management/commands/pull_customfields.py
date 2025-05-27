from django.core.management.base import BaseCommand
from core.services import CustomfieldServices

class Command(BaseCommand):
    help = "Fetch contacts from GoHighLevel API and store them in the database."

    def add_arguments(self, parser):
        parser.add_argument('--model', type=str, help='Optional model to filter custom fields')

    def handle(self, *args, **kwargs):
        model = kwargs.get('model')
        try:
            result = CustomfieldServices.pull_customfields(model)
            self.stdout.write(self.style.SUCCESS(result))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))