from django.core.management.base import BaseCommand
from core.models import OAuthToken, Contact, Task, GHLUser
from core.services import TaskServices, ContactServices
from django.db.models import Q, Count, Prefetch, Sum
from core.serializers import ContactSerializer
import json
from django.utils.dateparse import parse_datetime

class Command(BaseCommand):
    help = "Pull tasks for a selected LocationId from existing OAuthToken entries"

    def handle(self, *args, **options):
    
        l_id = str(input("Enter Location Id"))
        c_id = str(input("Enter Contact Id"))
        contact = ContactServices.get_contact(l_id,c_id )
        print(contact)
        ContactServices.save_contact(contact)
        
