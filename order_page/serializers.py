# serializers.py
from rest_framework import serializers
from .models import (
    TermsOfConditions, Bundle, BundleGroup,
    ServiceCategory,
    IndividualService,
    ServiceForm,
    FormItem,
    OptionGroup,
    OptionItem,
    Submenu,
    SubmenuItem,
    SubmenuPriceChange,
    ModalOption,
    Disclosure,
    ServiceVariance
    
    )

class TermsOfConditionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsOfConditions
        fields = ['id', 'title', 'body', 'created_at', 'updated_at']



class BundleSerializer(serializers.ModelSerializer):
    """
    Serializer for individual bundles.
    Converts `base_price` → `basePrice` and `discounted_price` → `price`
    """
    basePrice = serializers.DecimalField(source="base_price", max_digits=10, decimal_places=2)
    price = serializers.DecimalField(source="discounted_price", max_digits=10, decimal_places=2)

    class Meta:
        model = Bundle
        fields = ["name", "description", "basePrice", "price"]


class BundleGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for bundle groups 
   
    """
    bundles = BundleSerializer(many=True, read_only=True)

    class Meta:
        model = BundleGroup
        fields = ["header", "subheader", "bundles"]



# -------------------------------------------------------------------
# OptionItem Serializer
# -------------------------------------------------------------------
class OptionItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="identifier")

    class Meta:
        model = OptionItem
        fields = ["id", "label", "value", "disabled", "price_change"]


# -------------------------------------------------------------------
# OptionGroup Serializer
# -------------------------------------------------------------------
class OptionGroupSerializer(serializers.ModelSerializer):
    items = OptionItemSerializer(many=True)
    type = serializers.CharField()
    minimumRequired = serializers.IntegerField(source="minimum_required")

    class Meta:
        model = OptionGroup
        fields = ["type", "minimumRequired", "items"]


# -------------------------------------------------------------------
# Submenu Item Serializer
# -------------------------------------------------------------------
class SubmenuItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="identifier")

    class Meta:
        model = SubmenuItem
        fields = ["id", "label", "type", "value", "min_value", "max_value"]


# -------------------------------------------------------------------
# Submenu Serializer
# -------------------------------------------------------------------
class SubmenuSerializer(serializers.ModelSerializer):
    items = SubmenuItemSerializer(many=True)
    type = serializers.CharField()

    class Meta:
        model = Submenu
        fields = ["type", "items"]


# -------------------------------------------------------------------
# SubmenuPriceChange Serializer (flattened key:value)
# -------------------------------------------------------------------
class SubmenuPriceChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmenuPriceChange
        fields = ["key", "change_type", "value"]


# -------------------------------------------------------------------
# Modal Option Serializer
# -------------------------------------------------------------------
class ModalOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModalOption
        fields = ["each_item", "label", "field_name", "field_type", "required"]


# -------------------------------------------------------------------
# Disclosure Serializer
# -------------------------------------------------------------------
class DisclosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disclosure
        fields = ["type", "message"]


# -------------------------------------------------------------------
# Form Item Serializer (core “items”)
# -------------------------------------------------------------------
class FormItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="identifier")
    options = serializers.SerializerMethodField()
    submenuPriceChange = serializers.SerializerMethodField()

    class Meta:
        model = FormItem
        fields = [
            "id",
            "title",
            "subtitle",
            "price",
            "base_price",
            "protection_invalid",
            "options",
            "submenuPriceChange",
        ]

    def get_options(self, obj):
        groups = obj.option_groups.all()
        if not groups.exists():
            return {}
        # For this design, we assume one group per item for simplicity
        group = groups.first()
        return OptionGroupSerializer(group).data

    def get_submenuPriceChange(self, obj):
        changes = obj.submenu_price_changes.all()
        if not changes.exists():
            return None
        # Convert list into JS-like dict of {key: {type, value}}
        return {
            ch.key: {
                "type": ch.change_type,
                "value": ch.value,
            }
            for ch in changes
        }


# -------------------------------------------------------------------
# Service Form Serializer
# -------------------------------------------------------------------
class ServiceFormSerializer(serializers.ModelSerializer):
    items = FormItemSerializer(many=True)
    options = serializers.SerializerMethodField()
    submenu = serializers.SerializerMethodField()
    modalOption = serializers.SerializerMethodField()

    class Meta:
        model = ServiceForm
        fields = [
            "title",
            "description",
            "items",
            "options",
            "submenu",
            "modalOption",
        ]

    def get_options(self, obj):
        # Placeholder (some forms may not have additional options)
        return {}

    def get_submenu(self, obj):
        submenu = obj.submenus.first()
        return SubmenuSerializer(submenu).data if submenu else None

    def get_modalOption(self, obj):
        modal_opts = obj.modal_options.all()
        if not modal_opts.exists():
            return None
        # Match the structure: { eachItem: bool, validItem: [], form: [ {..}, ... ] }
        first = modal_opts.first()
        return {
            "eachItem": first.each_item,
            "validItem": [],
            "form": ModalOptionSerializer(modal_opts, many=True).data,
        }


# -------------------------------------------------------------------
# Individual Service Serializer
# -------------------------------------------------------------------
class IndividualServiceSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug")
    form = ServiceFormSerializer()
    disclosure = DisclosureSerializer(many=True, source="disclosures")

    class Meta:
        model = IndividualService
        fields = [
            "id",
            "title",
            "subtitle",
            "header",
            "subheader_html",
            "order_protection",
            "order_protection_type",
            "order_protection_disabled",
            "order_protection_value",
            "form",
            "disclosure",
        ]


# -------------------------------------------------------------------
# Service Category Serializer
# -------------------------------------------------------------------
class ServiceCategorySerializer(serializers.ModelSerializer):
    services = IndividualServiceSerializer(many=True)

    class Meta:
        model = ServiceCategory
        fields = ["title", "description", "services"]
        

class ServiceVarianceSerializer(serializers.ModelSerializer):
    """
    Combines the selected ServiceCategory + all related BundleGroups
    into a unified JSON output for frontend consumption.
    """

    # Nested serializers
    service_category = ServiceCategorySerializer(read_only=True)
    bundle_group = BundleGroupSerializer(many=True, read_only=True)

    # Optional: list of client IDs (or you can expand this to a full serializer later)
    clients = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = ServiceVariance
        fields = [
            "id",
            "name",
            "version_number",
            "is_default",
            "is_active",
            "notes",
            "service_category",
            "bundle_group",
            "clients",
            "created_at",
            "updated_at",
        ]