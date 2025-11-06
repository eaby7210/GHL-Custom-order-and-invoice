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




class SubmenuPriceChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmenuPriceChange
        fields = ["key", "change_type", "value"]

class SubmenuItemSerializer(serializers.ModelSerializer):
    price_changes = SubmenuPriceChangeSerializer(
        many=True,
        read_only=True,
        # source="price_changes"
        )

    class Meta:
        model = SubmenuItem
        fields = [
            "identifier",
            "label",
            "type",
            "value",
            "min_value",
            "max_value",
            "price_changes",
        ]

class SubmenuSerializer(serializers.ModelSerializer):
    items = SubmenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Submenu
        fields = ["type", "label", "items"]

class OptionItemSerializer(serializers.ModelSerializer):
    # Matches JS: { id, label, value, disabled, priceChange }
    class Meta:
        model = OptionItem
        fields = [
            "identifier",
            "label",
            "value",
            "disabled",
            "price_change",
        ]

class OptionGroupSerializer(serializers.ModelSerializer):
    items = OptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = OptionGroup
        fields = [
            "type",
            "minimum_required",
            "items",
        ]

class FormItemSerializer(serializers.ModelSerializer):
    options = OptionGroupSerializer(source="option_group", read_only=True)
    submenu_price_changes = serializers.SerializerMethodField()

    class Meta:
        model = FormItem
        fields = [
            "identifier",
            "title",
            "subtitle",
            "price",
            "base_price",
            "protection_invalid",
            "options",
            "submenu_price_changes",
        ]

    def get_submenu_price_changes(self, obj):
        """
        Returns submenu price changes as a dict structure like:
        {
          "pages11_39": { "type": "add", "value": 30 },
          "witness": { "type": "multiple", "value": 25 }
        }
        """
        if not hasattr(obj, "option_group") or not obj.option_group:
            return None
        # Collect related submenu price changes through related submenu items if any
        submenu_changes = {}
        submenu_items = SubmenuItem.objects.filter(price_changes__isnull=False).distinct()
        for item in submenu_items:
            for change in item.price_changes.all():
                submenu_changes[change.key] = {
                    "type": change.change_type,
                    "value": change.value,
                }
        return submenu_changes or None

class ModalOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModalOption
        fields = [
            "each_item",
            "label",
            "field_name",
            "field_type",
            "required",
        ]

class ServiceFormSerializer(serializers.ModelSerializer):
    items = FormItemSerializer(many=True, read_only=True)
    submenus = SubmenuSerializer(many=True, read_only=True)
    modal_options = ModalOptionSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceForm
        fields = [
            "title",
            "description",
            "items",
            "submenus",
            "modal_options",
        ]

class DisclosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disclosure
        fields = ["type", "message"]

class IndividualServiceSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="service_id")
    form = ServiceFormSerializer(source="form_ref", read_only=True)
    disclosure = DisclosureSerializer(many=True, source="disclosures", read_only=True)

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

class ServiceCategorySerializer(serializers.ModelSerializer):
    services = IndividualServiceSerializer(many=True, read_only=True)

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