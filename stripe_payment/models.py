from django.db import models
from decimal import Decimal


class Order(models.Model):
    UNIT_TYPE_CHOICES = [
        ("single", "Single"),
        ("multiple", "Multiple"),
    ]
    SERVICE_TYPE_CHOICES = [
        ("a_la_carte", "A La Carte"),
        ("bundled", "Bundled"),
    ]

    unit_type = models.CharField(max_length=20, choices=UNIT_TYPE_CHOICES)
    address = models.TextField(null=True, blank=True)
    streetAddress = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)

    unit = models.CharField(max_length=100,null=True, blank=True)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES)
    
    # Bundled service fields
    bundle_group = models.CharField(max_length=255, null=True, blank=True)
    bundle_item = models.CharField(max_length=255, null=True, blank=True)
    
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Occupancy & Access
    occupancy_vacant = models.BooleanField(default=False)
    occupancy_occupied = models.BooleanField(default=False)
    access_lock_box = models.BooleanField(default=False)
    lock_box_code = models.CharField(max_length=50, blank=True, null=True)
    lock_box_location = models.TextField(blank=True, null=True)
    access_app_lock_box = models.BooleanField(default=False)
    access_meet_contact = models.BooleanField(default=False)
    access_hidden_key = models.BooleanField(default=False)
    hidden_key_directions = models.TextField(blank=True, null=True)
    access_community_access = models.BooleanField(default=False)
    community_access_instructions = models.TextField(blank=True, null=True)
    access_door_code = models.BooleanField(default=False)
    door_code_value = models.CharField(max_length=50, blank=True, null=True)

    # Scheduling & Contact
    preferred_datetime = models.DateTimeField(null=True, blank=True)
    contact_name_sched = models.CharField(max_length=100,null=True, blank=True)
    contact_phone_sched = models.CharField(max_length=20,null=True, blank=True)
    contact_email_sched = models.EmailField(null=True, blank=True)
    
    # Consent
    accepted_at = models.DateTimeField(null=True, blank=True)
    tbd = models.BooleanField(default=False)

    # Stripe Relationship
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class ALaCarteService(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="a_la_carte_services")

    key = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    prompt = models.TextField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    addons_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Optional input (like maintenance descriptions)
    submenu_input = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.order.contact_name_sched}"


class ALaCarteAddOn(models.Model):
    service = models.ForeignKey(ALaCarteService, on_delete=models.CASCADE, related_name="addons")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name} for {self.service.name}"


class ALaCarteSubMenu(models.Model):
    service = models.OneToOneField(ALaCarteService, on_delete=models.CASCADE, related_name="submenu")
    option = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return f"Submenu for {self.service.name}"


class StripeCharge(models.Model):
    charge_id = models.CharField(max_length=100, unique=True)
    payment_intent_id = models.CharField(max_length=100, null=True, blank=True)
    amount = models.IntegerField()
    currency = models.CharField(max_length=10)
    paid = models.BooleanField(default=False)
    status = models.CharField(max_length=50)
    captured = models.BooleanField(default=False)
    receipt_url = models.URLField(null=True, blank=True)
    customer_email = models.EmailField(null=True, blank=True)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    billing_country = models.CharField(max_length=2, null=True, blank=True)
    brand = models.CharField(max_length=50, null=True, blank=True)
    last4 = models.CharField(max_length=4, null=True, blank=True)
    exp_month = models.IntegerField(null=True, blank=True)
    exp_year = models.IntegerField(null=True, blank=True)
    network_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    created = models.DateTimeField()
    livemode = models.BooleanField(default=False)

    def __str__(self):
        return self.charge_id


class CheckoutSession(models.Model):
    session_id = models.CharField(max_length=100, primary_key=True)
    payment_intent = models.CharField(max_length=100, null=True, blank=True)
    amount_subtotal = models.IntegerField()
    amount_total = models.IntegerField()
    currency = models.CharField(max_length=10)
    payment_status = models.CharField(max_length=50)
    customer_email = models.EmailField(null=True, blank=True)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created = models.DateTimeField()

    def __str__(self):
        return self.session_id


from django.db import models

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]

    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed'),
    ]

    _id = models.CharField(max_length=50, primary_key=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    live_mode = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    alt_id = models.CharField(max_length=50)
    alt_type = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    invoice_number = models.CharField(max_length=50)
    currency = models.CharField(max_length=10)
    issue_date = models.DateField()
    due_date = models.DateField()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    title = models.CharField(max_length=255)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = 'invoice'

class BusinessDetails(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='business_details')
    name = models.CharField(max_length=255)
    phone_no = models.CharField(max_length=20)

    class Meta:
        db_table = 'business_details'

class Discount(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='discount')
    type = models.CharField(max_length=20, choices=Invoice.DISCOUNT_TYPE_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'discount'

