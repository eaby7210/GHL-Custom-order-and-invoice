"""
Server-side order repricing.

FormSubmissionAPIView saves the client's *selections* (which items/options/
bundles were chosen, unit count, mobile flag, modal answers) into Order and
its related rows — that's real user input and stays trusted as-is. This
module throws away every *price* the client submitted alongside those
selections (bundle/item price, subtotal, priceAdd, protection amount, ...)
and recomputes them from the order_page catalog (DB, via catalog.py),
mirroring investbootz's src/lib/bundlePricing.js + orderPricingSync.js +
orderProtection.js pricing logic. Call this once, right after the order and
its related rows are saved, before any Stripe amount is computed.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from .catalog import get_service_variance_payload

logger = logging.getLogger(__name__)

BUNDLE_PROTECTION_RATE = Decimal("0.03")
MISMATCH_TOLERANCE = Decimal("0.01")


class PricingCatalogUnavailable(Exception):
    """No ServiceVariance could be resolved for the order's company_id."""


def _q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _unit_multiplier(is_mobile, mobile_allowed, is_multi_unit, multi_unit_allowed, num_units):
    mobile = bool(is_mobile) and mobile_allowed is not False
    multi = bool(is_multi_unit) and multi_unit_allowed is not False
    n = num_units if multi else 1
    mobile_factor = Decimal("0.85") if mobile else Decimal("1.0")
    return mobile_factor * (Decimal("1") + Decimal("0.5") * (Decimal(n) - 1))


def _multi_unit_context(unit_type, number_of_units):
    is_multi_unit = unit_type == "multiple" and (number_of_units or 0) > 1
    num_units = number_of_units if is_multi_unit else 1
    return is_multi_unit, num_units


# ---------------------------------------------------------------------------
# Bundles — mirrors src/lib/bundlePricing.js::recalculateBundlePrice
# ---------------------------------------------------------------------------
def recalc_bundle_price(catalog_bundle, is_mobile, is_multi_unit, num_units, selected_options):
    mult = _unit_multiplier(
        is_mobile,
        catalog_bundle.get("mobileHomeDiscountValid"),
        is_multi_unit,
        catalog_bundle.get("multiUnitValid"),
        num_units,
    )
    base = _q2(Decimal(str(catalog_bundle["basePrice"])) * mult)
    price = _q2(Decimal(str(catalog_bundle["price"])) * mult)

    options = catalog_bundle.get("options")
    items = options.get("items") if isinstance(options, dict) else None
    if items:
        for opt in items:
            val = selected_options.get(opt["id"])
            price_add = Decimal(str(opt.get("priceAdd") or 0))
            opt_type = opt.get("type")

            if opt_type in ("checkbox", "radio"):
                if val:
                    if base > 0:
                        base += price_add
                    price += price_add
            elif opt_type == "number":
                num_val = Decimal(str(val or 0))
                if num_val > 0 and price_add > 0:
                    add = num_val * price_add
                    if base > 0:
                        base += add
                    price += add

    return _q2(base), _q2(price)


# ---------------------------------------------------------------------------
# À la carte items — mirrors orderPricingSync.js::buildUnitAdjustedCatalog +
# recalculateServicePrices
# ---------------------------------------------------------------------------
def _unit_adjusted_item(catalog_item, is_mobile, is_multi_unit, num_units):
    mult = _unit_multiplier(
        is_mobile,
        catalog_item.get("mobileHomeDiscountValid"),
        is_multi_unit,
        catalog_item.get("multiUnitValid"),
        num_units,
    )
    base_price = catalog_item.get("basePrice")
    price = catalog_item.get("price")

    if mult == 1:
        return dict(catalog_item)

    adj_price = _q2(Decimal(str(price)) * mult)
    adj_base = _q2(Decimal(str(base_price)) * mult) if base_price is not None else adj_price
    adjusted = dict(catalog_item, price=adj_price, basePrice=adj_base)

    options = catalog_item.get("options") or {}
    items = options.get("items") or []
    if items:
        new_items = []
        for opt in items:
            if opt.get("priceChange"):
                new_items.append(dict(opt, priceChange=_q2(Decimal(str(opt["priceChange"])) * mult)))
            else:
                new_items.append(opt)
        adjusted["options"] = dict(options, items=new_items)

    return adjusted


def _recalc_item_price(adjusted_item, selected_option_ids, submenu_selections):
    base_price = adjusted_item.get("basePrice")
    base_price = Decimal(str(base_price if base_price is not None else (adjusted_item.get("price") or 0)))
    final_price = base_price

    options = (adjusted_item.get("options") or {}).get("items") or []
    if options:
        defaults = {opt["id"]: bool(opt.get("value")) for opt in options}
        current = {opt_id: bool(v) for opt_id, v in (selected_option_ids or {}).items()}
        same_as_defaults = bool(defaults) and all(
            current.get(opt_id, False) == default_val for opt_id, default_val in defaults.items()
        )
        if not same_as_defaults:
            for opt in options:
                if not current.get(opt["id"]):
                    continue
                if opt.get("priceChange") is not None:
                    final_price = Decimal(str(opt["priceChange"]))
                if opt.get("priceAdd") is not None:
                    add = Decimal(str(opt["priceAdd"]))
                    if add > 0:
                        final_price += add

    submenu_price_change = adjusted_item.get("submenuPriceChange") or {}
    if submenu_price_change:
        accumulated = Decimal("0")
        for opt_id, change in submenu_price_change.items():
            if not change:
                continue
            is_active = submenu_selections.get(opt_id)
            if not is_active and is_active != 0:
                continue
            if change.get("type") == "add":
                accumulated += Decimal(str(change.get("value") or 0))
            elif change.get("type") == "multiple" and isinstance(is_active, (int, float)) and not isinstance(is_active, bool):
                if change.get("value"):
                    accumulated += Decimal(str(change["value"])) * Decimal(str(is_active))
                else:
                    accumulated += base_price * (Decimal(str(is_active)) - 1)
        final_price += accumulated

    return final_price


# ---------------------------------------------------------------------------
# Stacking discount — catalog-driven (FormItem.discount_eligible /
# discount_requires_option + order_page.DiscountLevel), single source of
# truth shared with the frontend catalog payload.
# ---------------------------------------------------------------------------
def _build_selection_snapshot(a_la_carte_data):
    snapshot = {}
    for entry in a_la_carte_data or []:
        service_id = entry.get("id")
        items = {}
        options = {}
        for item in (entry.get("form", {}) or {}).get("items", []) or []:
            item_id = item.get("id")
            items[item_id] = True
            opt_items = (item.get("options") or {}).get("items") or []
            options[item_id] = {o["id"]: bool(o.get("value")) for o in opt_items}
        snapshot[service_id] = {"items": items, "options": options}
    return snapshot


def _discount_qualified_count(a_la_carte_data, catalog_services, selection):
    count = 0
    for entry in a_la_carte_data or []:
        service_id = entry.get("id")
        catalog_service = catalog_services.get(service_id)
        if not catalog_service:
            continue
        catalog_items = {i["id"]: i for i in (catalog_service.get("form", {}) or {}).get("items", []) or []}
        for item_id in selection.get(service_id, {}).get("items", {}):
            catalog_item = catalog_items.get(item_id)
            if not catalog_item or not catalog_item.get("discountEligible"):
                continue
            if catalog_item.get("discountRequiresOption"):
                opts = selection.get(service_id, {}).get("options", {}).get(item_id, {})
                if not any(opts.values()):
                    continue
            count += 1
    return count


def _discount_percent_for(catalog_item, qualified_count, discount_levels):
    if not catalog_item.get("discountEligible"):
        return Decimal("0")
    matching = [lvl for lvl in discount_levels if qualified_count >= lvl["items"]]
    if not matching:
        return Decimal("0")
    return Decimal(str(max(matching, key=lambda lvl: lvl["items"])["percent"]))


# ---------------------------------------------------------------------------
# Order protection — mirrors src/lib/orderProtection.js
# ---------------------------------------------------------------------------
def _has_protection_invalid(catalog_service, selected_item_ids):
    items = (catalog_service.get("form", {}) or {}).get("items", []) or []
    selected = set(selected_item_ids)
    return any(item.get("protectionInvalid") and item["id"] in selected for item in items)


def _resolve_service_protection(catalog_service, selected_item_ids, explicit_enabled):
    if _has_protection_invalid(catalog_service, selected_item_ids):
        return False
    if catalog_service.get("order_protection_disabled"):
        return False
    if isinstance(explicit_enabled, bool):
        return explicit_enabled
    return bool(catalog_service.get("order_protection")) and bool(catalog_service.get("order_protection_value"))


def _service_protection_amount(catalog_service, subtotal: Decimal) -> Decimal:
    if subtotal <= 0:
        return Decimal("0")
    # Mirrors orderPricingSync.js: only "percent" is ever applied — its
    # "flat" branch checks order_protection_type === "flat", a string this
    # catalog's OrderProtectionType choices ("percent"/"fixed") never
    # produce, so fixed-fee protection is already a no-op on the frontend
    # today. Replicated as-is to stay consistent with live charge behavior.
    if catalog_service.get("order_protection_type") == "percent":
        value = Decimal(str(catalog_service.get("order_protection_value") or 0))
        return _q2(subtotal * value / 100)
    return Decimal("0")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def reprice_order(order, data, company_id):
    payload = get_service_variance_payload(company_id)
    if not payload:
        raise PricingCatalogUnavailable(f"No catalog found for company_id={company_id!r}")

    catalog_services = {s["id"]: s for s in (payload.get("service_category") or {}).get("services", [])}
    catalog_bundles_by_name = {}
    for group in payload.get("bundle_group") or []:
        for b in group.get("bundles") or []:
            catalog_bundles_by_name.setdefault(b["name"], b)
    discount_levels = payload.get("discount_levels") or []

    is_mobile = bool(data.get("isMobileHome"))
    is_multi_unit, num_units = _multi_unit_context(order.unit_type, order.number_of_units)

    client_total = order.total_price
    client_protection = order.order_protection_price

    # ---- Bundles ----
    bundles_data = data.get("bundles") or []
    bundle_rows = list(order.bundles.all().order_by("id"))
    bundle_subtotal = Decimal("0.00")

    for row, submitted in zip(bundle_rows, bundles_data):
        catalog_bundle = catalog_bundles_by_name.get(submitted.get("name"))
        if not catalog_bundle:
            logger.error(
                "reprice_order: no catalog bundle matched order=%s name=%r",
                order.id, submitted.get("name"),
            )
            row.base_price = Decimal("0.00")
            row.price = Decimal("0.00")
            row.save(update_fields=["base_price", "price"])
            continue

        selected_options = submitted.get("selectedOptions") or {}
        base, price = recalc_bundle_price(catalog_bundle, is_mobile, is_multi_unit, num_units, selected_options)
        row.base_price = base
        row.price = price
        row.save(update_fields=["base_price", "price"])
        bundle_subtotal += price

    bundle_protection = Decimal("0.00")
    if bundles_data and data.get("bundleOrderProtectionCheck") and bundle_subtotal > 0:
        bundle_protection = _q2(bundle_subtotal * BUNDLE_PROTECTION_RATE)

    # ---- À la carte ----
    a_la_carte_data = data.get("a_la_carteOrder") or []
    selection = _build_selection_snapshot(a_la_carte_data)
    qualified_count = _discount_qualified_count(a_la_carte_data, catalog_services, selection)
    protection_overrides = data.get("orderProtection") or {}

    item_rows_by_key = {}
    for service_row in order.a_la_carte_services.prefetch_related("items").all():
        for item_row in service_row.items.all():
            item_rows_by_key[(service_row.service_id, item_row.item_id)] = item_row

    ala_subtotal = Decimal("0.00")
    ala_protection = Decimal("0.00")

    for entry in a_la_carte_data:
        service_id = entry.get("id")
        catalog_service = catalog_services.get(service_id)
        if not catalog_service:
            logger.error("reprice_order: no catalog service matched order=%s service=%r", order.id, service_id)
            continue

        catalog_items = {i["id"]: i for i in (catalog_service.get("form", {}) or {}).get("items", []) or []}
        selected_item_ids = list(selection.get(service_id, {}).get("items", {}).keys())
        submenu_selections = {
            s.get("id"): s.get("value")
            for s in ((entry.get("form", {}) or {}).get("submenu", {}) or {}).get("items", []) or []
        }

        service_subtotal = Decimal("0.00")
        for item in (entry.get("form", {}) or {}).get("items", []) or []:
            item_id = item.get("id")
            catalog_item = catalog_items.get(item_id)
            if not catalog_item:
                logger.error(
                    "reprice_order: no catalog item matched order=%s service=%r item=%r",
                    order.id, service_id, item_id,
                )
                continue

            adjusted = _unit_adjusted_item(catalog_item, is_mobile, is_multi_unit, num_units)
            selected_option_ids = selection.get(service_id, {}).get("options", {}).get(item_id, {})
            price = _recalc_item_price(adjusted, selected_option_ids, submenu_selections)

            discount_pct = _discount_percent_for(catalog_item, qualified_count, discount_levels)
            if discount_pct:
                price -= price * discount_pct / 100

            price = _q2(price)
            service_subtotal += price

            row = item_rows_by_key.get((service_id, item_id))
            if row is not None:
                row.price = price
                row.save(update_fields=["price"])

        override_entry = protection_overrides.get(service_id)
        explicit = override_entry.get("enabled") if isinstance(override_entry, dict) else None
        if _resolve_service_protection(catalog_service, selected_item_ids, explicit):
            ala_protection += _service_protection_amount(catalog_service, service_subtotal)

        ala_subtotal += service_subtotal

    total_price = _q2(bundle_subtotal + ala_subtotal)
    total_protection = _q2(bundle_protection + ala_protection)

    order.total_price = total_price
    order.order_protection_price = total_protection
    order.order_protection = total_protection > 0
    order.save(update_fields=["total_price", "order_protection_price", "order_protection"])

    if client_total is not None and abs(Decimal(str(client_total)) - total_price) > MISMATCH_TOLERANCE:
        logger.warning(
            "reprice_order: total mismatch order=%s client=%s server=%s",
            order.id, client_total, total_price,
        )
    if client_protection is not None and abs(Decimal(str(client_protection)) - total_protection) > MISMATCH_TOLERANCE:
        logger.warning(
            "reprice_order: protection mismatch order=%s client=%s server=%s",
            order.id, client_protection, total_protection,
        )

    return {"total_price": total_price, "order_protection_price": total_protection}
