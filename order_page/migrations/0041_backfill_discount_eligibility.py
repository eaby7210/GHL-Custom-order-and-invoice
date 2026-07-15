# Backfills FormItem.discount_eligible / discount_requires_option to match
# the stacking-discount rules currently hardcoded in the frontend's
# src/lib/discountRules.js — reconciled against live catalog identifiers
# (some of that file's item ids are stale/dead against prod data; only the
# items confirmed to actually exist are backfilled here).
from django.db import migrations

# identifier -> requires_option
DISCOUNT_ELIGIBLE_ITEMS = {
    "PHbasic": True,
    "NTinperson": False,
    "wt-videos": False,
    "LBstandard": False,
    "LBsameday": False,
    "LBremove": False,
    "LBcode": False,
    "wellnessCheck": False,
    "letterPost": False,
}


def backfill(apps, schema_editor):
    FormItem = apps.get_model("order_page", "FormItem")
    for identifier, requires_option in DISCOUNT_ELIGIBLE_ITEMS.items():
        FormItem.objects.filter(identifier=identifier).update(
            discount_eligible=True,
            discount_requires_option=requires_option,
        )


def unset(apps, schema_editor):
    FormItem = apps.get_model("order_page", "FormItem")
    FormItem.objects.filter(identifier__in=DISCOUNT_ELIGIBLE_ITEMS.keys()).update(
        discount_eligible=False,
        discount_requires_option=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("order_page", "0040_formitem_discount_eligibility"),
    ]

    operations = [
        migrations.RunPython(backfill, unset),
    ]
