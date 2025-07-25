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
    PHONE_TYPE_CHOICES = [
        ("mobile", "Mobile"),
        ("landline", "Landline"),
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
    
    company_id = models.CharField(max_length=100,null=True, blank=True)
    user_id= models.CharField(max_length=100, null=True, blank=True)
    owner_id= models.CharField(max_length=100, null=True, blank=True)
    
    contact_first_name_sched = models.CharField(max_length=100,null=True, blank=True)
    contact_last_name_sched = models.CharField(max_length=100,null=True, blank=True)
    contact_phone_sched_type = models.CharField(max_length=20, choices=PHONE_TYPE_CHOICES, null=True, blank=True)
    contact_phone_sched = models.CharField(max_length=20,null=True, blank=True)
    contact_email_sched = models.EmailField(null=True, blank=True)
    
    contact_first_name = models.CharField(max_length=100,null=True, blank=True)
    contact_last_name = models.CharField(max_length=100,null=True, blank=True)
    contact_phone_type = models.CharField(max_length=20, choices=PHONE_TYPE_CHOICES, null=True, blank=True)
    contact_phone = models.CharField(max_length=20,null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    
    cosigner_first_name = models.CharField(max_length=100, null=True, blank=True)
    cosigner_last_name = models.CharField(max_length=100, null=True, blank=True)
    cosigner_phone_type = models.CharField(max_length=20, choices=PHONE_TYPE_CHOICES, null=True, blank=True)
    cosigner_phone = models.CharField(max_length=20, null=True, blank=True)
    cosigner_email = models.EmailField(null=True, blank=True)
    
    company_name = models.CharField(max_length=255, null=True, blank=True)
    # Consent
    accepted_at = models.DateTimeField(null=True, blank=True)
    tbd = models.BooleanField(default=False)
    sp_instruction = models.TextField(null=True, blank=True)

    # Stripe Relationship
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True)
    location_id = models.CharField(max_length=50, null=True, blank=True)
    
    coupon_code = models.CharField(max_length=50, null=True, blank=True)
    coupon_id = models.CharField(max_length=50, null=True, blank=True)
    coupon_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    coupon_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    invoice_id = models.CharField(max_length=50, null=True, blank=True)
    

class ALaCarteService(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="a_la_carte_services")

    key = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    prompt = models.TextField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    addons_price = models.DecimalField(max_digits=10, decimal_places=2)
    reduced_names = models.CharField(max_length=255, null=True, blank=True)
    # Optional input (like maintenance descriptions)
    submenu_input = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.order.contact_first_name_sched} {self.order.contact_last_name_sched} ({self.order.unit})"


class ALaCarteAddOn(models.Model):
    service = models.ForeignKey(ALaCarteService, on_delete=models.CASCADE, related_name="addons")
    key = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name} for {self.service.name}"


class ALaCarteSubMenu(models.Model):
    service = models.OneToOneField(ALaCarteService, on_delete=models.CASCADE, related_name="submenu")
    option = models.CharField(max_length=100, null=True, blank=True)
    label = models.CharField(max_length=255,null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    prompt_label = models.CharField(max_length=255, null=True, blank=True, default=None)
    prompt_value = models.TextField(null=True, blank=True, default=None) 
    

    def __str__(self):
        return f"Submenu for {self.service.name}"


class Coupon(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)  # Optional name for the coupon
    code = models.CharField(max_length=100, unique=True)  # user-facing code (id from Stripe)
    stripe_coupon_id = models.CharField(max_length=100)   # technically same as code from Stripe
    amount_off = models.IntegerField(null=True, blank=True)
    percent_off = models.FloatField(null=True, blank=True)
    duration = models.CharField(max_length=20, null=True, blank=True)
    currency = models.CharField(max_length=10, null=True, blank=True)
    valid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.valid}"

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


class StripeWebhookEventLog(models.Model):
    event_id = models.CharField(max_length=100, primary_key=True)
    event_type = models.CharField(max_length=50)
    event_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    error_message = models.TextField(null=True, blank=True)
    json_body = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.event_type} - {self.event_id}"

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

class NotaryClientCompany(models.Model):
    id = models.BigIntegerField(primary_key=True)  # Matches NotaryDash ID
    owner_id = models.BigIntegerField()
    parent_company_id = models.BigIntegerField()
    
    type = models.CharField(max_length=50)  # e.g., 'client'
    company_name = models.CharField(max_length=255)
    parent_company_name = models.CharField(max_length=255, null=True, blank=True)

    attr = models.JSONField(default=dict, null=True, blank=True)  # Stores dynamic keys like phone, accounting_email

    address = models.JSONField(default=dict, null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.company_name


class NotaryUser(models.Model):
    id = models.BigIntegerField(primary_key=True)
    
    email = models.EmailField()
    email_unverified = models.BooleanField(null=True, blank=True)
    
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    name = models.CharField(max_length=255)

    photo_url = models.URLField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)

    last_company = models.ForeignKey(
        NotaryClientCompany,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )

    attr = models.JSONField(default=dict, blank=True)
    disabled = models.BooleanField(null=True, blank=True)
    type = models.CharField(max_length=50)
    country_code = models.CharField(max_length=10, null=True, blank=True)
    tz = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    has_roles = models.JSONField(default=list, blank=True)

    # Pivot fields
    pivot_active = models.BooleanField(default=True)
    pivot_role_id = models.IntegerField(null=True, blank=True)
    pivot_company = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.email