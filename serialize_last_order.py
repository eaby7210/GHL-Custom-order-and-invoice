import os
import django
import json
from decimal import Decimal
from datetime import datetime, date
from django.db import models

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')
django.setup()

from stripe_payment.models import (
    Order, Bundle, BundleOption, BundleModalOption,
    ALaCarteService, ALaCarteItem, ALaCarteOption, ALaCarteSubMenuItem
)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def serialize_model(instance):
    """Serialize a model instance to a dictionary."""
    data = {}
    for field in instance._meta.fields:
        value = getattr(instance, field.name)
        if isinstance(field, models.ForeignKey):
             if value:
                 data[field.name] = value.pk
             else:
                 data[field.name] = None
        else:
            data[field.name] = value
    return data

def main():
    try:
        last_order = Order.objects.last()
        if not last_order:
            print("No orders found.")
            return

        print(f"Serializing Order ID: {last_order.id}")

        order_data = serialize_model(last_order)
        
        # Serialize Bundles
        bundles = []
        for bundle in last_order.bundles.all():
            bundle_data = serialize_model(bundle)
            
            # Serialize Bundle Options
            options = []
            for option in bundle.options.all():
                options.append(serialize_model(option))
            bundle_data['options'] = options
            
            # Serialize Bundle Modal Options
            modal_options = []
            for modal_option in bundle.modal_options.all():
                modal_options.append(serialize_model(modal_option))
            bundle_data['modal_options'] = modal_options
            
            bundles.append(bundle_data)
        
        order_data['bundles'] = bundles

        # Serialize A La Carte Services
        ala_carte_services = []
        for service in last_order.a_la_carte_services.all():
            service_data = serialize_model(service)
            
            items = []
            for item in service.items.all():
                item_data = serialize_model(item)
                
                # Serialize Item Options
                item_options = []
                for option in item.options.all():
                    item_options.append(serialize_model(option))
                item_data['options'] = item_options
                
                # Serialize Submenu Items
                submenu_items = []
                for sub_item in item.submenu_items.all():
                    submenu_items.append(serialize_model(sub_item))
                item_data['submenu_items'] = submenu_items

                # Serialize Modal Options
                modal_options = []
                for modal_option in item.modal_options.all():
                    modal_options.append(serialize_model(modal_option))
                item_data['modal_options'] = modal_options
                
                items.append(item_data)
            
            service_data['items'] = items
            ala_carte_services.append(service_data)
            
        order_data['a_la_carte_services'] = ala_carte_services

        output_file = 'last_order_dump.json'
        with open(output_file, 'w') as f:
            json.dump(order_data, f, cls=DateTimeEncoder, indent=4)
        
        print(f"Successfully serialized last order to {output_file}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
