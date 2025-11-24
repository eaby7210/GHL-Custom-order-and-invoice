from django.db import models
from decimal import Decimal
import json



class Order(models.Model):
    UNIT_TYPE_CHOICES = [
        ("single", "Single"),
        ("multiple", "Multiple"),
    ]
    SERVICE_TYPE_CHOICES = [
        ("a_la_carte", "A La Carte"),
        ("bundled", "Bundled"),
         ("mixed", "Mixed"),
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
    # bundle_group = models.CharField(max_length=255, null=True, blank=True)
    # bundle_item = models.CharField(max_length=255, null=True, blank=True)
    
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Occupancy & Access
    occupancy_vacant = models.BooleanField(default=False)
    occupancy_occupied = models.BooleanField(default=False)
    occupancy_status = models.CharField(max_length=20, null=True, blank=True)
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
    client_team_id = models.CharField(max_length=100, null=True, blank=True)
    
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
    order_protection = models.BooleanField(default=False, null=True, blank=True)
    order_protection_price =models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    
class Bundle(models.Model):
    """Each bundle in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="bundles")
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"{self.name} ({self.order.id})" #type:ignore
    
    

class ALaCarteService(models.Model):
    order = models.ForeignKey("Order", related_name="a_la_carte_services", on_delete=models.CASCADE)

    # Service Info
    service_id = models.CharField(max_length=100)   # e.g. "photos", "lockboxes"
    title = models.CharField(max_length=255)        # e.g. "Property Photos"
    subtitle = models.TextField(null=True, blank=True)

    # Form Info
    form_title = models.CharField(max_length=255, null=True, blank=True)
    form_description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.order.id})"

    @classmethod
    def from_api(cls, order, recieved_data):
        """
        Create a service and its related items/options/submenu from API payload.
        """
        a_la_carte_order = recieved_data.get("a_la_carteOrder",[])
        for data in a_la_carte_order:
            service = cls.objects.create(
                order=order,
                service_id=data.get("id"),
                title=data.get("title"),
                subtitle=data.get("subtitle"),
                form_title=data.get("form", {}).get("title"),
                form_description=data.get("form", {}).get("description"),
            )

            for item_data in data.get("form", {}).get("items", []):
                ALaCarteItem.from_api(service, item_data, data.get("form", {}), recieved_data.get("serviceTotals",{}))

        return order


class ALaCarteItem(models.Model):
    service = models.ForeignKey(ALaCarteService, related_name="items", on_delete=models.CASCADE)
    item_id = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    subtitle = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    protection_invalid = models.BooleanField(default=False)

    # Flattened option group fields
    options_type = models.CharField(max_length=50, choices=[
        ("checkbox", "Checkbox"),
        ("counter", "Counter"),
        ("none", "None"),
        ("mixed", "Mixed"),
    ], null=True, blank=True)
    minimum_required = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.title} ({self.service.title})"

    @classmethod
    def from_api(cls, service, data, form_data=None, service_totals=None):
        print(f"Service Totals {json.dumps(service_totals.get(service.service_id, {}).get("items",{}).get(data.get("id"),{}), indent=4)}")
        form_options = data.get("options", {})
        item = cls.objects.create(
            service=service,
            item_id=data.get("id"),
            title=data.get("title"),
            subtitle=data.get("subtitle"),
            price=service_totals.get(service.service_id, {}).get("items",{}).get(data.get("id"),{}).get("discountedPrice",0),
            base_price=data.get("basePrice"),
            protection_invalid=data.get("protectionInvalid", False),
            options_type=form_options.get("type", "none") if form_options else None,
            minimum_required=form_options.get("minimumRequired", 0) if form_options else 0,
        )

        # Create options if present
        if form_options:
            for opt in form_options.get("items", []):
                ALaCarteOption.from_api(item, opt)

        # Create submenu if present (from parent form, not just item)
        if form_data:
            submenu = form_data.get("submenu", {})
            for sub_item in submenu.get("items", []):
                ALaCarteSubMenuItem.from_api(item, sub_item,form_data)

        return item


class ALaCarteOption(models.Model):
    item = models.ForeignKey(ALaCarteItem, related_name="options", on_delete=models.CASCADE)
    option_id = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    value = models.BooleanField(default=False)
    disabled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.label} ({self.item.title})"

    @classmethod
    def from_api(cls, item, data):
        return cls.objects.create(
            item=item,
            option_id=data.get("id"),
            label=data.get("label"),
            value=data.get("value", False),
            disabled=data.get("disabled", False),
        )


class ALaCarteSubMenuItem(models.Model):
    item = models.ForeignKey(ALaCarteItem, related_name="submenu_items", on_delete=models.CASCADE)
    submenu_item_id = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=50, choices=[
        ("counter", "Counter"),
        ("checkbox", "Checkbox"),
    ], default="counter")
    value = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.label} (submenu of {self.item.title})"

    @classmethod
    def from_api(cls, item, data,form_data=None):
        return cls.objects.create(
            item=item,
            submenu_item_id=data.get("id"),
            label=data.get("label"),
            type=data.get("type", "counter"),
            value=data.get("value", 0),
        )
        
        
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
    page_visited = models.BooleanField(default=False)

    def __str__(self):
        return self.email