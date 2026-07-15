# Marks the 2 catalog groups found this session where two priceChange-type
# options can both be checked at once with no defined winner: PHbasic's
# (basic_interior/basic_exterior) and supervisedpropaccess's
# (spa1hr/spa2hr) option groups. Both groups contain only that pair and
# aren't reused by any other FormItem, so group-level radio is exact --
# no other item's options are affected.
from django.db import migrations

RADIO_GROUP_ITEMS = ["PHbasic", "supervisedpropaccess"]


def backfill(apps, schema_editor):
    FormItem = apps.get_model("order_page", "FormItem")
    for fi in FormItem.objects.filter(identifier__in=RADIO_GROUP_ITEMS).select_related("option_group"):
        if fi.option_group:
            fi.option_group.type = "radio"
            fi.option_group.save(update_fields=["type"])


def unset(apps, schema_editor):
    FormItem = apps.get_model("order_page", "FormItem")
    for fi in FormItem.objects.filter(identifier__in=RADIO_GROUP_ITEMS).select_related("option_group"):
        if fi.option_group:
            fi.option_group.type = "checkbox"
            fi.option_group.save(update_fields=["type"])


class Migration(migrations.Migration):

    dependencies = [
        ("order_page", "0042_optiongroup_enable_radio_type"),
    ]

    operations = [
        migrations.RunPython(backfill, unset),
    ]
