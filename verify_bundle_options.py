import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from stripe_payment.models import Order, Bundle, BundleOption, BundleModalOption

def verify():
    # Create dummy order
    order = Order.objects.create(
        unit_type="single",
        service_type="bundled",
        total_price=Decimal("100.00")
    )
    print(f"Created Order: {order.id}")

    # Create bundle
    bundle = Bundle.objects.create(
        order=order,
        name="Test Bundle",
        base_price=Decimal("50.00"),
        price=Decimal("50.00")
    )
    print(f"Created Bundle: {bundle}")

    # Create BundleOption
    option = BundleOption.objects.create(
        bundle=bundle,
        name="Option 1",
        description="Test Option",
        value="Value 1",
        price=Decimal("10.00")
    )
    print(f"Created BundleOption: {option}")

    # Create BundleModalOption
    modal_option = BundleModalOption.objects.create(
        bundle=bundle,
        name="Modal Option 1",
        description="Test Modal Option",
        value="Modal Value 1",
        price=Decimal("5.00")
    )
    print(f"Created BundleModalOption: {modal_option}")

    # Verify
    assert BundleOption.objects.filter(bundle=bundle).count() == 1
    assert BundleModalOption.objects.filter(bundle=bundle).count() == 1
    print("Verification successful!")

if __name__ == "__main__":
    try:
        verify()
    except Exception as e:
        print(f"Verification failed: {e}")
