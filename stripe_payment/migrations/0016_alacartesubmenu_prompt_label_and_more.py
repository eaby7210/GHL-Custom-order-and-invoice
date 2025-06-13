# Generated by Django 5.2.1 on 2025-06-07 19:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_payment', '0015_alacarteservice_reduced_names_order_company_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='alacartesubmenu',
            name='prompt_label',
            field=models.CharField(blank=True, default=None, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='alacartesubmenu',
            name='prompt_value',
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='alacartesubmenu',
            name='label',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='alacartesubmenu',
            name='option',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
