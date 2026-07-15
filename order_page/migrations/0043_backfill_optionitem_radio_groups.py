# Marks the 2 catalog cases found this session where two priceChange-type
# options in the same item can be checked simultaneously with no defined
# winner: basic_interior/basic_exterior (PHbasic) and spa1hr/spa2hr
# (supervisedpropaccess). Everything else stays type=None -> checkbox,
# unchanged behavior.
from django.db import migrations

RADIO_GROUPS = {
    "photo_scope": ["basic_interior", "basic_exterior"],
    "access_duration": ["spa1hr", "spa2hr"],
}


def backfill(apps, schema_editor):
    OptionItem = apps.get_model("order_page", "OptionItem")
    for group_name, identifiers in RADIO_GROUPS.items():
        OptionItem.objects.filter(identifier__in=identifiers).update(
            type="radio", name=group_name
        )


def unset(apps, schema_editor):
    OptionItem = apps.get_model("order_page", "OptionItem")
    all_ids = [i for ids in RADIO_GROUPS.values() for i in ids]
    OptionItem.objects.filter(identifier__in=all_ids).update(type=None, name=None)


class Migration(migrations.Migration):

    dependencies = [
        ("order_page", "0042_optionitem_selection_type"),
    ]

    operations = [
        migrations.RunPython(backfill, unset),
    ]
