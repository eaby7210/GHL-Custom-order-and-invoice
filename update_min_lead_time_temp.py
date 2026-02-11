import os
import django

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')

# Setup Django
django.setup()

from order_page.models import Bundle, FormItem

def run_update():
    print("Starting update of min_lead_time...")

    # Update Bundle objects
    bundles_to_update = Bundle.objects.filter(min_lead_time=0)
    bundle_count = bundles_to_update.count()
    print(f"Found {bundle_count} Bundle objects with min_lead_time=0.")
    
    updated_bundles = 0
    for bundle in bundles_to_update:
        bundle.min_lead_time = 3
        bundle.save()
        updated_bundles += 1
    
    print(f"Successfully updated {updated_bundles} Bundle objects.")

    # Update FormItem objects
    items_to_update = FormItem.objects.filter(min_lead_time=0)
    item_count = items_to_update.count()
    print(f"Found {item_count} FormItem objects with min_lead_time=0.")
    
    updated_items = 0
    for item in items_to_update:
        item.min_lead_time = 3
        item.save()
        updated_items += 1
    
    print(f"Successfully updated {updated_items} FormItem objects.")
    print("Update complete.")

if __name__ == "__main__":
    run_update()
