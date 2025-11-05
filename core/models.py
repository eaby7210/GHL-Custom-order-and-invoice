from django.db import models
from django.utils.timezone import now


class OAuthToken(models.Model):
    access_token = models.TextField()
    token_type = models.CharField(max_length=100, default="Brearer")
    expires_at = models.DateField()
    refresh_token = models.TextField()
    scope = models.TextField()
    userType = models.CharField(max_length=100)
    companyId = models.CharField(max_length=100)
    company_name = models.CharField(max_length=200, null=True, blank=True)
    LocationId = models.CharField(max_length=100,unique=True)
    userId = models.CharField(max_length=100)
    
    def is_expired(self):
        """Check if the access token is expired"""
        return now().date() >= self.expires_at
    
    def __str__(self):
        return f"{self.LocationId} - {self.token_type}"
 

class Contact(models.Model):
    id = models.CharField(max_length=50, primary_key=True)  
    first_name = models.CharField(max_length=100,null=True)
    last_name = models.CharField(max_length=100,null=True)
    email = models.EmailField(null=True, blank=True, unique=True)
    phone = models.CharField(max_length=100,null=True, blank=True, unique=True)
    country = models.CharField(max_length=10,null=True, blank=True)
    location_id = models.CharField(max_length=50, null=True, blank=True)
    type = models.CharField(max_length=20, choices=[("lead", "Lead"), ("customer", "Customer")],null=True, blank=True)
    date_added = models.DateTimeField(default=now )  
    date_updated = models.DateTimeField(auto_now=True)  
    dnd = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

