from django.db import models
from datetime import datetime



class Partner(models.Model):
    id = models.CharField(primary_key=True, max_length=64)  # Tolt Partner ID
    first_name = models.CharField(max_length=128, null=True, blank=True)
    last_name = models.CharField(max_length=128, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    program_id = models.CharField(max_length=64, null=True, blank=True)
    organization_id = models.CharField(max_length=64, null=True, blank=True)
    group_id = models.CharField(max_length=64, null=True, blank=True)
    payout_method = models.CharField(max_length=64, null=True, blank=True)
    payout_email = models.EmailField(null=True, blank=True)
    country_code = models.CharField(max_length=8, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tolt_partner"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @staticmethod
    def create_or_update_from_api(data: dict):
        mapping = {
            "id": data.get("id"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "email": data.get("email"),
            "company_name": data.get("company_name"),
            "program_id": data.get("program_id"),
            "organization_id": data.get("organization_id"),
            "group_id": data.get("group_id"),
            "payout_method": data.get("payout_method"),
            "payout_email": (data.get("payout_details") or {}).get("email"),
            "country_code": data.get("country_code"),
            "created_at": datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")) if data.get("created_at") else None,
        }
        obj, created = Partner.objects.update_or_create(
            id=mapping["id"], defaults=mapping
        )
        return obj, created


class Customer(models.Model):
    id = models.CharField(primary_key=True, max_length=64)  # Tolt Customer ID
    email = models.EmailField(null=True, blank=True)
    partner = models.ForeignKey(
        Partner, null=True, blank=True, on_delete=models.SET_NULL, related_name="customers"
    )
    name = models.CharField(max_length=255, null=True, blank=True)
    customer_id = models.CharField(max_length=128, null=True, blank=True)  # external customer reference
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, null=True, blank=True)
    program_id = models.CharField(max_length=64, null=True, blank=True)
    organization_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "tolt_customer"

    def __str__(self):
        return f"{self.name} ({self.email})"

    @staticmethod
    def create_or_update_from_api(data: dict):
        partner = None
        if data.get("partner_id"):
            partner, _ = Partner.objects.get_or_create(id=data["partner_id"])

        mapping = {
            "id": data.get("id"),
            "email": data.get("email"),
            "partner": partner,
            "name": data.get("name"),
            "customer_id": data.get("customer_id"),
            "created_at": datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")) if data.get("created_at") else None,
            "updated_at": datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")) if data.get("updated_at") else None,
            "status": data.get("status"),
            "program_id": data.get("program_id"),
            "organization_id": data.get("organization_id"),
        }
        obj, created = Customer.objects.update_or_create(
            id=mapping["id"], defaults=mapping
        )
        return obj, created
    
    @staticmethod
    def from_webhook(payload: dict):
        """
        Create or update a Customer from a Tolt webhook payload.
        Expected structure:
        {
            "type": "customer.created" | "customer.updated",
            "timestamp": "...",
            "data": { ...customer fields... }
        }
        """
        data = payload.get("data", {}) or {}

        # --- Partner association ---
        partner = None
        if data.get("partner_id"):
            partner, _ = Partner.objects.get_or_create(id=data["partner_id"])

        # --- Helper to convert timestamps safely ---
        def parse_ts(value):
            if not value:
                return None
            try:
                value = value.replace("Z", "+00:00")
                return datetime.fromisoformat(value)
            except Exception:
                return None

        mapping = {
            "id": data.get("id"),
            "email": data.get("email"),
            "partner": partner,
            "name": data.get("name"),
            "customer_id": data.get("customer_id"),
            "created_at": parse_ts(data.get("created_at")),
            "updated_at": parse_ts(payload.get("timestamp")),   # webhook timestamp
            "status": data.get("status"),
            "program_id": data.get("program_id"),
            "organization_id": data.get("organization_id"),
        }

        # --- Save ---
        obj, created = Customer.objects.update_or_create(
            id=mapping["id"], defaults=mapping
        )

        return obj, created



class Link(models.Model):
    id = models.CharField(primary_key=True, max_length=64)  # Tolt Link ID
    param = models.CharField(max_length=64, null=True, blank=True)
    value = models.CharField(max_length=255, null=True, blank=True)
    partner = models.ForeignKey(
        Partner, null=True, blank=True, on_delete=models.SET_NULL, related_name="links"
    )
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    program_id = models.CharField(max_length=64, null=True, blank=True)
    organization_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "tolt_link"

    def __str__(self):
        return f"Link {self.id} ({self.param}={self.value})"

    @staticmethod
    def create_or_update_from_api(data: dict):
        partner = None
        if data.get("partner_id"):
            partner= Partner.objects.filter(id=data["partner_id"]).first()


        mapping = {
            "id": data.get("id"),
            "param": data.get("param"),
            "value": data.get("value"),
            "partner": partner,
            "created_at": datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")) if data.get("created_at") else None,
            "updated_at": datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")) if data.get("updated_at") else None,
            "program_id": data.get("program_id"),
            "organization_id": data.get("organization_id"),
        }
        obj, created = Link.objects.update_or_create(
            id=mapping["id"], defaults=mapping
        )
        return obj, created

    @staticmethod
    def create_or_update_from_webhook(payload: dict):
        data = payload.get("data", {})
        link, created = Link.create_or_update_from_api(data)
        return link, created, payload.get("type")


class Transaction(models.Model):
    id = models.CharField(primary_key=True, max_length=64)  # Tolt Transaction ID
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    customer = models.ForeignKey(
        "Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    billing_type = models.CharField(max_length=64, null=True, blank=True)  # e.g. "subscription"
    charge_id = models.CharField(max_length=64, null=True, blank=True)
    click_id = models.CharField(max_length=64, null=True, blank=True)
    product_id = models.CharField(max_length=64, null=True, blank=True)
    product_name = models.CharField(max_length=255, null=True, blank=True)
    source = models.CharField(max_length=64, null=True, blank=True)  # e.g. "stripe"
    interval = models.CharField(max_length=32, null=True, blank=True)  # e.g. "month"
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    # Relationship with partner/program if needed
    program_id = models.CharField(max_length=64, null=True, blank=True)
    partner = models.ForeignKey(
        "Partner", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )

    class Meta:
        db_table = "tolt_transaction"

    def __str__(self):
        return f"Transaction {self.id} ({self.product_name} - {self.amount})"

    @staticmethod
    def create_or_update_from_api(data: dict):
        # ✅ resolve customer if exists
        customer = None
        if data.get("customer_id"):
            customer, _ = Customer.objects.get_or_create(id=data["customer_id"])

        # ✅ resolve partner if exists
        partner = None
        if data.get("partner_id"):
            partner, _ = Partner.objects.get_or_create(id=data["partner_id"])

        mapping = {
            "id": data.get("id"),
            "amount": (int(data.get("amount")or 0) ) / 100,  # cents → dollars (optional)
            "customer": customer,
            "billing_type": data.get("billing_type"),
            "charge_id": data.get("charge_id"),
            "click_id": data.get("click_id"),
            "product_id": data.get("product_id"),
            "product_name": data.get("product_name"),
            "source": data.get("source"),
            "interval": data.get("interval"),
            "created_at": datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")) if data.get("created_at") else None,
            "updated_at": datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")) if data.get("updated_at") else None,
            "program_id": data.get("program_id"),
            "partner": partner,
        }

        obj, created = Transaction.objects.update_or_create(
            id=mapping["id"], defaults=mapping
        )
        return obj, created


