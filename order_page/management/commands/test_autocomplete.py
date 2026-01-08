from django.core.management.base import BaseCommand
from order_page.services import GoogleService
import json

class Command(BaseCommand):
    help = 'Test Google Places Autocomplete API'

    def add_arguments(self, parser):
        parser.add_argument('input', type=str, help='Text string to search on')

    def handle(self, *args, **kwargs):
        input_text = kwargs['input']
        service = GoogleService()
        
        self.stdout.write(f"Searching for: {input_text}")
        result = service.get_autocomplete(input_text)
        
        self.stdout.write(json.dumps(result, indent=2))
