from django.core.management.base import BaseCommand
from datetime import datetime
from django.utils.timezone import make_aware, is_naive
import logging, json,time
from django.db import transaction
from typing import Dict, Any, Tuple
import requests
from tolt.services import ToltService
from django.core.management.base import CommandError
from tolt.models import Partner
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError


from django.db import transaction
from django.utils.dateparse import parse_datetime



logger = logging.getLogger(__name__)
def parse_and_make_aware(dt_str):
    dt = parse_datetime(dt_str) if dt_str else None
    if dt and is_naive(dt):
        return make_aware(dt)
    return dt

class Command(BaseCommand):
    help = 'Fetch all partners from Tolt API and sync to database using pagination'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-after',
            type=int,

            help='partner ID to start fetching after ',
        )
        parser.add_argument(
            '--end-before',
            type=int,
            help='Partner ID to stop fetching before ',
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=3,
            help='Maximum number of retries for failed API requests (default: 3)'
        )
        parser.add_argument(
            '--retry-delay',
            type=int,
            default=5,
            help='Delay in seconds between retries (default: 5)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of records to process in each database transaction (default: 50)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without saving to database'
        )
        parser.add_argument(
            '--per-page',
            type=int,
            help='Number of records to fetch per API request (max 100, default 100)',
            default=100
        )

    def handle(self, *args, **options):
        """Main command handler"""
        per_page = options.get("per-page",100) # Ensure max 100 per API limits
        # max_retries = options.get("")
        # retry_delay = options['retry_delay']
        # batch_size = options['batch_size']
        dry_run = options.get('dry_run', False)
        has_more = True
        start_after = options.get('start_after')
        end_before = options.get('end_before')
        
        while has_more:
            self.stdout.write(f"Fetching partners after ID {start_after} before ID {end_before} ")
            try:
                
                response = ToltService.fetch_partners(start_after, end_before, per_page)
                partners = response.get('data', [])
                has_more = response.get('has_more', False)
            
                if partners:
                    self.stdout.write(f"Fetched {len(partners)} partners from Tolt API.")
                    self.stdout.write(f"first partner ID: {partners[0].get('id')}, last partner ID: {partners[-1].get('id')}")
                    start_after = partners[-1].get('id')
                    if dry_run:
                        self.stdout.write("Dry run mode - not saving to database.")
                    else:
                        with transaction.atomic():
                          
                            for partner_data in partners:
                                try:
                                    partner, created = Partner.create_or_update_from_api(partner_data)
                                    action = "Created" if created else "Updated"
                                    # self.stdout.write(f"{action} Partner ID {partner.id}")
                                except Exception as e:
                                    self.stderr.write(self.style.ERROR(f"Error processing partner data: {e}"))
                                # Commit after each batch
                            transaction.on_commit(lambda: self.stdout.write(f"Committed batch of {len(partners)} partners."))
            except RequestException as e:
                self.stderr.write(self.style.ERROR(f"Error fetching partners: {e}"))
                raise e
            
            