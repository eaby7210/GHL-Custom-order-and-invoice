# Generated by Django 5.2.1 on 2025-06-04 10:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_payment', '0013_order_location_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotaryClientCompany',
            fields=[
                ('id', models.BigIntegerField(primary_key=True, serialize=False)),
                ('owner_id', models.BigIntegerField()),
                ('parent_company_id', models.BigIntegerField()),
                ('type', models.CharField(max_length=50)),
                ('company_name', models.CharField(max_length=255)),
                ('parent_company_name', models.CharField(blank=True, max_length=255, null=True)),
                ('attr', models.JSONField(blank=True, default=dict)),
                ('address', models.TextField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField()),
                ('active', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='NotaryUser',
            fields=[
                ('id', models.BigIntegerField(primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('email_unverified', models.BooleanField(blank=True, null=True)),
                ('first_name', models.CharField(max_length=255)),
                ('last_name', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('photo_url', models.URLField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('last_login_at', models.DateTimeField(blank=True, null=True)),
                ('last_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('attr', models.JSONField(blank=True, default=dict)),
                ('disabled', models.BooleanField(blank=True, null=True)),
                ('type', models.CharField(max_length=50)),
                ('country_code', models.CharField(blank=True, max_length=10, null=True)),
                ('tz', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField()),
                ('has_roles', models.JSONField(blank=True, default=list)),
                ('pivot_active', models.BooleanField(default=True)),
                ('pivot_role_id', models.IntegerField(blank=True, null=True)),
                ('pivot_company', models.CharField(blank=True, max_length=255, null=True)),
                ('last_company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='stripe_payment.notaryclientcompany')),
            ],
        ),
    ]
