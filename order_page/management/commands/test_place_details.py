from django.core.management.base import BaseCommand
from order_page.services import GoogleService
import json

class Command(BaseCommand):
    help = 'Test Google Place Details API'

    def add_arguments(self, parser):
        parser.add_argument('place_id', type=str, help='Google Place ID')

    def handle(self, *args, **kwargs):
        place_id = kwargs['place_id']
        service = GoogleService()
        
        self.stdout.write(f"Fetching details for Place ID: {place_id}")
        result = service.get_place_details(place_id)
        
        # Display full response
        self.stdout.write("\n=== Full Response ===")
        self.stdout.write(json.dumps(result, indent=2))
        
        if "error" in result:
             self.stdout.write(self.style.ERROR("API returned an error."))
             return

        # Parse and display address details
        self.stdout.write("\n=== Address Details ===")
        components = result.get('addressComponents', [])
        
        address_map = {
            'street_number': '',
            'route': '',
            'locality': '',
            'administrative_area_level_1': '',
            'postal_code': '',
            'subpremise': ''
        }
        
        for comp in components:
            types = comp.get('types', [])
            for t in types:
                if t in address_map:
                    address_map[t] = comp.get('longText') or comp.get('shortText')
                    
        street_address = f"{address_map['street_number']} {address_map['route']}".strip()
        
        self.stdout.write(f"Street Address: {street_address}")
        self.stdout.write(f"City: {address_map['locality']}")
        self.stdout.write(f"State: {address_map['administrative_area_level_1']}")
        self.stdout.write(f"Postal Code: {address_map['postal_code']}")
        
        if address_map['subpremise']:
            self.stdout.write(f"Unit: {address_map['subpremise']}")
