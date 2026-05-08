from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("order_page", "0037_formitem_min_lead_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="bundle",
            name="mobile_home_discount_valid",
            field=models.BooleanField(
                default=True,
                verbose_name="Mobile Home Discount",
                help_text="If True, the mobile home discount (15% off) applies to this bundle.",
            ),
        ),
        migrations.AddField(
            model_name="bundle",
            name="multi_unit_valid",
            field=models.BooleanField(
                default=True,
                verbose_name="Multi-Unit Pricing",
                help_text="If True, multi-unit tiered pricing (additional units at 50%) applies to this bundle.",
            ),
        ),
        migrations.AddField(
            model_name="formitem",
            name="mobile_home_discount_valid",
            field=models.BooleanField(
                default=True,
                verbose_name="Mobile Home Discount",
                help_text="If True, the mobile home discount (15% off) applies to this item.",
            ),
        ),
        migrations.AddField(
            model_name="formitem",
            name="multi_unit_valid",
            field=models.BooleanField(
                default=True,
                verbose_name="Multi-Unit Pricing",
                help_text="If True, multi-unit tiered pricing (additional units at 50%) applies to this item.",
            ),
        ),
    ]
