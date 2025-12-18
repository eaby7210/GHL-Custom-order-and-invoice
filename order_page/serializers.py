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
    ServiceVariance,
    BundleOptionGroup, BundleOptionItem,
    BundleModalField,

    BundleModalForm,
    DiscountLevel, CheckDiscloure
    
    )

class TermsOfConditionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsOfConditions
        fields = ['id', 'title', 'body', 'created_at', 'updated_at']


class CheckDiscloureSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckDiscloure
        fields = [
            "name",
            "required",
            "message",
            "sort_order",
            "active_flag"
        ]

class BundleModalFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = BundleModalField
        fields = [
            "label",
            "name",
            "type",
            "required",
            "value",
            "placeholder",
            "help_text",
            "sort_order",
        ]
        
class BundleModalFormSerializer(serializers.ModelSerializer):
    fields = BundleModalFieldSerializer(source="field", many=True, read_only=True) #type:ignore
    check_disclosure = CheckDiscloureSerializer(many=True, read_only=True)

    class Meta:
        model = BundleModalForm
        fields = [
            "title",
            "description",
            "is_active",
            "fields",
            "check_disclosure",
        ]

# -------------------------------------------------------------------
#  Bundle Option Item Serializer
# -------------------------------------------------------------------
class BundleOptionItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="identifier")
    label = serializers.CharField()
    disabled = serializers.BooleanField()
    priceAdd = serializers.DecimalField(source="price_change", max_digits=10, decimal_places=2, required=False)

    # dynamic value field
    value = serializers.SerializerMethodField()

    class Meta:
        model = BundleOptionItem
        fields = ["id", "type", "label","name", "value", "disabled", "priceAdd"]

    def get_value(self, obj):
        """
        Returns dynamic value depending on option type:
        - checkbox/radio → boolean (obj.value)
        - number → obj.num_val
        - text → obj.text_val
        """
        if obj.type in ["checkbox", "radio"]:
            return obj.value
        
        if obj.type == "number":
            return obj.num_val
        
        if obj.type == "text":
            return obj.text_val

        # fallback
        return obj.value


# -------------------------------------------------------------------
#  Bundle Option Group Serializer
# -------------------------------------------------------------------
class BundleOptionGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for bundle option groups.
    Outputs `type`, `minimumRequired`, and `items` to match frontend expectations.
    """
    minimumRequired = serializers.IntegerField(source="minimum_required")
    items = BundleOptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = BundleOptionGroup
        fields = [ "minimumRequired", "items"]


# -------------------------------------------------------------------
#  Bundle Serializer
# -------------------------------------------------------------------
class BundleSerializer(serializers.ModelSerializer):
    """
    Serializer for individual bundles.
    Converts `base_price` → `basePrice`, `discounted_price` → `price`,
    and includes nested options (if available).
    """
    basePrice = serializers.DecimalField(source="base_price", max_digits=10, decimal_places=2)
    price = serializers.DecimalField(source="discounted_price", max_digits=10, decimal_places=2)
    options = serializers.SerializerMethodField()
    modalForm = BundleModalFormSerializer(source="modal_form", read_only=True)

    class Meta:
        model = Bundle
        fields = ["name", "description", "basePrice", "price", "options",  "modalForm", ]

    def get_options(self, obj):
        """
        Returns structured option groups for frontend:
        { type, minimumRequired, items: [...] }
        If multiple groups exist, returns the first or a list (depending on use case).
        """
        option_groups = obj.option_groups.all()
        if not option_groups.exists():
            return {}
        # If there’s only one group, return single dict (to match frontend pattern)
        if option_groups.count() == 1:
            return BundleOptionGroupSerializer(option_groups.first()).data
        # If multiple groups, return list
        return BundleOptionGroupSerializer(option_groups, many=True).data


# -------------------------------------------------------------------
#  Bundle Group Serializer
# -------------------------------------------------------------------
class BundleGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for bundle groups that contain multiple bundles.
    Maps to frontend format: { header, subheader, bundles: [...] }
    """
    bundles = BundleSerializer(many=True, read_only=True)

    class Meta:
        model = BundleGroup
        fields = ["header", "subheader", "bundles"]
        

class SubmenuPriceChangeSerializer(serializers.ModelSerializer):
    key = serializers.CharField(source="submenu_item.identifier")
    type = serializers.CharField(source="change_type")
    class Meta:
        model = SubmenuPriceChange
        fields = ["key", "type", "value"]

class SubmenuItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="identifier")
    valid_item_index = serializers.SerializerMethodField()
    name = serializers.CharField(source="form_name")
    min = serializers.DecimalField(max_digits=10, decimal_places=2, source="min_value")
    max = serializers.DecimalField(max_digits=10, decimal_places=2, source="max_value")

    class Meta:
        model = SubmenuItem
        fields = [
            "id",
            "label",
            "name",
            "type",
            "value",
            "min",
            "max",
            "valid_item_index",
        ]

    def get_valid_item_index(self, obj):
        return []

class SubmenuSerializer(serializers.ModelSerializer):
    items = SubmenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Submenu
        fields = ["type", "items"]

class OptionItemSerializer(serializers.ModelSerializer):
    """
    Serializer for OptionItem supporting dynamic key:
    -> If price_type = "priceAdd", outputs {"priceAdd": <value>}
    -> If price_type = "priceChange", outputs {"priceChange": <value>}
    """
    id = serializers.CharField(source="identifier")
    valid_item_index = serializers.SerializerMethodField()
    priceAdd = serializers.SerializerMethodField()
    priceChange = serializers.SerializerMethodField()

    class Meta:
        model = OptionItem
        fields = [
            "id",
            "label",
            "value",
            "disabled",
            "priceAdd",
            "priceChange",
            "valid_item_index",
        ]

    def get_valid_item_index(self, obj):
        return []  # JS expects an empty array always

    def get_priceAdd(self, obj):
        if obj.price_type == "priceAdd" and obj.price_value is not None:
            return float(obj.price_value)
        return None

    def get_priceChange(self, obj):
        if obj.price_type == "priceChange" and obj.price_value is not None:
            return float(obj.price_value)
        return None


class OptionGroupSerializer(serializers.ModelSerializer):
    items = OptionItemSerializer(many=True, read_only=True)
    minimumRequired = serializers.IntegerField(source="minimum_required")

    class Meta:
        model = OptionGroup
        fields = [
            "type",
            "minimumRequired",
            "items",
        ]

class FormItemSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="identifier")
    basePrice = serializers.DecimalField(source="base_price", max_digits=10, decimal_places=2, allow_null=True)
    protectionInvalid = serializers.BooleanField(source="protection_invalid")
    options = OptionGroupSerializer(source="option_group", read_only=True)
    submenuPriceChange = serializers.SerializerMethodField()

    class Meta:
        model = FormItem
        fields = [
            "id",
            "title",
            "subtitle",
            "price",
            "basePrice",
            "protectionInvalid",
            "options",
            "submenuPriceChange",
        ]

    def get_submenuPriceChange(self, obj):
        """
        Output exactly like:
        {
            "pages11_39": { "type": "add", "value": 30 },
            "witness": { "type": "multiple", "value": 25 }
        }
        """
        changes = {}
        for change in obj.submenu_price_changes.select_related("submenu_item").all():
            key = change.submenu_item.identifier
            changes[key] = {
                "type": change.change_type,
                "value": float(change.value) if change.value is not None else None,
            }
        return changes or {}


class ModalOptionSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="field_name")
    type = serializers.CharField(source="field_type")
    valid_item_index = serializers.SerializerMethodField()
    check_disclosure = CheckDiscloureSerializer(many=True, read_only=True)

    class Meta:
        model = ModalOption
        fields = [
            "label",
            "name",
            "type",
            "value",
            "hidden",
            "footer_head",
            "footer_body",
            "required",
            "valid_item_index",
            "check_disclosure",
        ]

    def get_valid_item_index(self, obj):
        """
        Return an array of linked FormItem identifiers.
        If none are linked, return [] (applies to all).
        """
        items = obj.valid_for_items.values_list("identifier", flat=True)
        return list(items) if items else None

        
class ServiceFormSerializer(serializers.ModelSerializer):
    items = FormItemSerializer(many=True, read_only=True)
    submenu = serializers.SerializerMethodField()
    modalOption = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = ServiceForm
        fields = ["title", "description", "items", "options", "submenu", "modalOption"]

    def get_options(self, obj):
        # JS expects "options": {} always
        return {}

    def get_submenu(self, obj):
        submenus = obj.submenus.all()
        if not submenus.exists():
            return {}
        # JS expects single submenu structure, not a list
        first = submenus.first()
        return SubmenuSerializer(first).data

    def get_modalOption(self, obj):
        modals = obj.modal_options.all()
        if not modals.exists():
            return {}
        return {
            "eachItem": False,
            "validItem": [],
            "form": ModalOptionSerializer(modals, many=True).data,
        }

class DisclosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disclosure
        fields = ["type", "message"]

class IndividualServiceSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="service_id")
    subheader = serializers.CharField(source="subheader_html")
    form = ServiceFormSerializer(source="form_ref", read_only=True)
    disclosure = DisclosureSerializer(many=True, source="disclosures", read_only=True)

    class Meta:
        model = IndividualService
        fields = [
            "id",
            "title",
            "subtitle",
            "header",
            "subheader",
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

class DiscountLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscountLevel
        fields = [
            "id",
            "items",
            "percent",
            "active_flag",
            "created_at",
            "updated_at",
        ]
    
    def to_representation(self, instance):
        """
        Convert Decimal percent → float
        """
        data = super().to_representation(instance)
        data["percent"] = float(instance.percent)
        return data

    def validate_items(self, value):
        if value < 1:
            raise serializers.ValidationError("Items must be >= 1")
        return value

    def validate_percent(self, value):
        if value <= 0 or value > 100:
            raise serializers.ValidationError("Percent must be between 0 and 100")
        return value

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
    discount_levels = serializers.SerializerMethodField()



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
            "discount_levels"
        ]
    def get_discount_levels(self, obj):

        qs = DiscountLevel.objects.filter(active_flag=True).order_by("items")
        return DiscountLevelSerializer(qs, many=True).data
        
