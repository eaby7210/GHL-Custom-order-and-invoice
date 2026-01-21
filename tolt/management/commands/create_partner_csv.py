import csv
import sys
from django.core.management.base import BaseCommand
from tolt.models import Link

class Command(BaseCommand):
    help = 'Generates a CSV file with partner link details'

    def handle(self, *args, **options):
        filename = 'partner_links.csv'
        headers = ['partner_id', 'partner_email', 'link_id', 'param', 'value']

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)

                links = Link.objects.select_related('partner').all()
                count = 0
                
                for link in links:
                    partner = link.partner
                    row = [
                        partner.id if partner else '',
                        partner.email if partner else '',
                        link.id,
                        link.param,
                        link.value
                    ]
                    writer.writerow(row)
                    count += 1
            
            self.stdout.write(self.style.SUCCESS(f'Successfully generated {filename} with {count} rows'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error generating CSV: {str(e)}'))
