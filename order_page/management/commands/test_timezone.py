from django.core.management.base import BaseCommand
from order_page.services import GoogleService
import json

class Command(BaseCommand):
    help = 'Test Google Timezone API'

    def add_arguments(self, parser):
        parser.add_argument('latitude', type=float, help='Latitude of the location')
        parser.add_argument('longitude', type=float, help='Longitude of the location')

    def handle(self, *args, **kwargs):
        lat = kwargs['latitude']
        lng = kwargs['longitude']
        service = GoogleService()
        
        self.stdout.write(f"Getting timezone for: {lat}, {lng}")
        result = service.get_timezone(lat, lng)
        
        self.stdout.write(json.dumps(result, indent=2))
