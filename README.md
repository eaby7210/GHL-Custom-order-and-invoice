# Project Documentation

## API Authentication (Machine-to-Machine)

Moving from session-based authentication to API token authentication allows external services or scripts to interact securely with the API without user intervention. This project uses `django-oauth-toolkit` to implement the OAuth2 **Client Credentials** grant type, which is the standard for Machine-to-Machine (M2M) authentication.

### Prerequisites

Before you can make API requests, an administrator must create an Application in the Django Admin interface to generate a Client ID and Client Secret.

#### 1. Create an OAuth Application

1.  Log in to the Django Admin panel (e.g., `http://localhost:8000/admin/`).
2.  Navigate to **Django OAuth Toolkit** > **Applications**.
3.  Click **Add application**.
4.  Fill in the form:
    *   **User**: Select an administrative user (optional but recommended for tracking).
    *   **Client type**: `Confidential` (Required for keeping the client secret secure).
    *   **Authorization grant type**: `Client credentials`.
    *   **Name**: A descriptive name for the consuming service (e.g., "External Script", "Mobile App Backend").
5.  Click **Save**.

You will now see a **Client ID** and a **Client Secret**. Keep these credentials secure.

### Authentication Flow

#### 2. Obtain an Access Token

To get an access token, make a `POST` request to the token endpoint using your Client ID and Client Secret.

**Endpoint:** `/auth/token/`

##### Request

`POST /auth/token/`

**Headers:**
`Content-Type: application/x-www-form-urlencoded`

**Body:**
```
grant_type=client_credentials
client_id=<your_client_id>
client_secret=<your_client_secret>
```

##### Example (cURL)

```bash
curl -X POST http://localhost:8000/auth/token/ \
     -d "grant_type=client_credentials" \
     -d "client_id=YOUR_CLIENT_ID" \
     -d "client_secret=YOUR_CLIENT_SECRET"
```

##### Response

You will receive a JSON response containing the access token:

```json
{
    "access_token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5",
    "expires_in": 36000,
    "token_type": "Bearer",
}
```

#### 3. Make Authenticated Requests

Once you have the `access_token`, include it in the `Authorization` header of your API requests.

**Header Format:**
`Authorization: Bearer <access_token>`

##### Example Request

```bash
curl -H "Authorization: Bearer a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5" \
     http://localhost:8000/api/some-endpoint/
```

### Configuration Details

This setup is enabled by the following configuration in the codebase:

*   **Installed App**: `oauth2_provider` is added to `INSTALLED_APPS` in `settings.py`.
*   **Middleware**: `oauth2_provider.middleware.OAuth2TokenMiddleware` is added to `MIDDLEWARE` in `settings.py` to process the token.
*   **Authentication Classes**: `REST_FRAMEWORK` is configured with `oauth2_provider.contrib.rest_framework.OAuth2Authentication` as a default authentication class.
*   **URLs**: The OAuth2 provider URLs are included at `path('auth/', ...)` in `urls.py`.

### Notes

*   **Token Expiry**: Access tokens have an expiration time (default is 10 hours or 36000 seconds). You will need to request a new token using the Client Credentials flow when it expires. Refresh tokens are generally not issued for the Client Credentials grant type.

---

## Business Logic: Service Configuration & Ordering

### Overview

The system is a **configurable product catalog** for property inspection services. Clients (notary companies) place orders choosing from **bundles** (package deals) or **individual à la carte services**. The catalog is versioned per-client so different companies can see different menus and pricing.

### Menu Resolution — ServiceVariance

Every client company sees a specific **variance** (version) of the service catalog:

1. The system first looks for an **active variance assigned to the specific client** (`ServiceVariance.clients` M2M)
2. If none found, it falls back to the **active default variance** (`is_default=True`)
3. Only variances with `is_active=True` are served

Each variance contains:
- **One** `ServiceCategory` (FK) → the à la carte menu
- **Many** `BundleGroup` objects (M2M) → the bundle packages
- **Bundle order protection** settings (type + value)

### Bundle Path (Package Deals)

```
BundleGroup → Bundle → BundleOptionGroup → BundleOptionItem
                    └→ BundleModalForm → BundleModalField
                                     └→ CheckDisclosure
```

| Model | Purpose |
|---|---|
| **BundleGroup** | Visual grouping with header/subheader |
| **Bundle** | Package with `base_price` (original) and `discounted_price` (savings), plus `min_lead_time` |
| **BundleOptionGroup** | Add-on selection groups with `minimum_required` |
| **BundleOptionItem** | Individual add-ons with `price_change` (additional cost) |
| **BundleModalForm** | Popup form for extra details (signer name, dates, etc.) |
| **CheckDisclosure** | Mandatory checkbox agreements |

### À La Carte Path (Individual Services)

```
ServiceCategory → IndividualService → ServiceForm → FormItem → OptionGroup → OptionItem
                                                 └→ Submenu → SubmenuItem
                                                 └→ ModalOption → ModalOptionToggle
```

| Model | Purpose |
|---|---|
| **ServiceCategory** | Groups multiple individual services |
| **IndividualService** | Single service with order protection settings and `service_id` (used in NotaryDash product name) |
| **ServiceForm** | Configuration screen containing form items, submenus, and modal options |
| **FormItem** | Selectable item with `price`, `base_price`, `min_lead_time`, and `protection_invalid` flag |
| **OptionGroup → OptionItem** | Checkbox sub-selections; each item has `price_type` (`priceAdd` or `priceChange`) and `price_value` |
| **Submenu → SubmenuItem** | Quantity selectors (`counter`) or radio buttons (`radio`) with min/max constraints |
| **SubmenuPriceChange** | Links a FormItem to a SubmenuItem with `change_type`: `"add"` (flat per unit) or `"multiple"` (multiplier) |
| **ModalOption** | Pop-up input fields (text/email/number/date), scoped by `valid_for_items` and `check_disclosure` |
| **ModalOptionToggle** | Checkbox/radio that controls when a modal option is visible |

### Pricing Rules

| Rule | Mechanism |
|---|---|
| Bundle savings | `base_price - discounted_price` (pre-calculated) |
| Add-on pricing | `BundleOptionItem.price_change` added to bundle total |
| Option item pricing | `OptionItem.price_type`: `priceAdd` (adds) or `priceChange` (replaces) |
| Dynamic counter/radio pricing | `SubmenuPriceChange`: `add` (flat per unit) or `multiple` (multiplier on base) |
| Volume discounts | `DiscountLevel` slabs (e.g., 2 items → 20%, 3 items → 30%) |
| Order protection | Percent or fixed surcharge, configured at variance level (bundles) or service level (à la carte). Items with `protection_invalid=True` are exempt |

### Ordering Flow

1. **Identify client** → resolve `ServiceVariance` (client-specific or default)
2. **Display menu** → bundles and/or à la carte services
3. **Configure selections** → options, submenus, modal fields, disclosures
4. **Calculate pricing** → base + options + submenu modifiers − volume discount + order protection
5. **Submit order** → create product + order in NotaryDash

### V2 Webhook Sync

When a non-external order's `processing_status` changes to `completed`, a webhook (`order.completed.v2_sync`) dispatches the order data formatted for the V2 Supabase `orders` table. Key mappings:
- `notary_order_id` → `external_id` (deduplication key)
- `company_id` / `user_id` → resolved via `users.nd_user_id` / `users.nd_company_id` in Supabase

