# dj_investorbootz

Django backend powering Investorbootz's notary inspection ordering platform: a configurable service/bundle catalog, Stripe payments and invoicing, NotaryDash order fulfillment, and Tolt affiliate tracking.

## Tech Stack

- **Django 5.2** + **Django REST Framework**
- **PostgreSQL** (or SQLite for local dev)
- **Celery** + **Redis** for async tasks and scheduled jobs (django-celery-beat)
- **Stripe** for payments, invoicing, and saved payment methods
- **django-oauth-toolkit** for Machine-to-Machine (M2M) API auth
- **django-allauth** / **dj-rest-auth** for session/user auth
- External integrations: **NotaryDash**, **Tolt**, **Typeform**, **Framer**, **Google Places**

## Project Structure

| App | Purpose |
|---|---|
| [`core`](core) | Shared CSRF middleware |
| [`stripe_payment`](stripe_payment) | Orders, Stripe checkout/payments/invoices, NotaryDash company & user sync, M2M API |
| [`order_page`](order_page) | Public order-page catalog (services/bundles), Typeform & Framer intake, Google Places autocomplete |
| [`webhooks`](webhooks) | Outbound webhook event registry, dispatch, and delivery logs |
| [`tolt`](tolt) | Tolt.io affiliate/referral sync (partners, links, transactions) |

> See [Business Logic: Service Configuration & Ordering](#business-logic-service-configuration--ordering) below for how the catalog and pricing engine fit together.

## Getting Started

### Prerequisites

- Python 3.12
- Redis (Celery broker/result backend)
- PostgreSQL (or SQLite for local dev)

### Setup

```bash
# install dependencies (Pipfile or requirements.txt)
pipenv install
# or
pip install -r requirements.txt

# create a .env file in the project root (see Environment Variables below)

# apply migrations
python manage.py migrate

# create an admin user
python manage.py createsuperuser

# run the dev server
python manage.py runserver
```

### Background workers

```bash
celery -A dj_IBstripe worker -l info
celery -A dj_IBstripe beat -l info
```

The beat schedule (in `dj_IBstripe/settings.py`) runs daily client/contact sync tasks from `stripe_payment.tasks`.

## Environment Variables

Configured via `python-decouple` and read from a `.env` file in the project root.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DB`, `DB_ENGINE`, `DB_NAME`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` | Database connection (set `DB=psql` for PostgreSQL) |
| `STRIPE_LIVE` | `true` for live Stripe keys, otherwise test keys are used |
| `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY_TEST`, `STRIPE_SECRET_KEY_TEST`, `STRIPE_WEBHOOK_SECRET` | Stripe API + webhook signing keys |
| `NOTARY_LIVE_API_KEY`, `NOTARY_TEST_API_KEY` | NotaryDash API key (`NOTARY_TEST` flag in settings selects which is used) |
| `TYPEFORM_ACCESS_TOKEN` | Typeform API access for response/partner sync |
| `TOLT_KEY` | Tolt.io API key |
| `FRAMER_WEBHOOK_SECRET` | Shared secret for verifying inbound Framer webhooks |
| `GOOGLE_API_KEY` | Google Places autocomplete/details |
| `CORS_EXTRA_ORIGINS`, `CORS_EXTRA_ALLOW_HEADERS`, `CORS_ALLOW_ALL` | Additional CORS configuration for dev/preview origins |

> [!WARNING]
> Never commit a populated `.env` file. It is already excluded via `.gitignore`.

## API Overview

Root URL configuration ([`dj_IBstripe/urls.py`](dj_IBstripe/urls.py)):

| Path prefix | App | Notes |
|---|---|---|
| `/admin/` | Django admin | Site header: "IB Order Page Admin" |
| `/auth/` | `oauth2_provider` | OAuth2 token endpoint (M2M, Client Credentials grant) |
| `/summernote/` | `django_summernote` | Rich text editor widget (admin) |
| `/order_page/`, `/api/order_page/` | `order_page` | `/api/order_page/` is an alias for the nginx/frontend base path |
| `/twebs/` | `tolt` | Tolt webhook receiver |
| `/` (root) | `stripe_payment` | Orders, payments, M2M REST API |

### `stripe_payment` endpoints

- `submit-order/`, `submit-order/<stripe_session_id>/` — order submission and Stripe Checkout session lookup
- `stripe-webhook/` — Stripe event webhook (charges, invoices, payment methods)
- `notary-view/`, `stripe-coupon/<code>` — NotaryDash lookup, coupon validation
- `create-setup-intent/`, `save-payment-method/`, `set-default-card/` — saved card management
- `invoice/payment-intent/<payment_intent_id>/` — invoice retrieval by payment intent
- `company-admin/`, `company-users/`, `company-payment-methods/` — company account management
- M2M REST endpoints (router-based, OAuth2 protected): `orders/`, `companies/`, `users/`, `notary-users/query/`, `create-order/`

### `order_page` endpoints

- `tos/latest/` — latest Terms of Conditions
- `entry-response/` — Typeform webhook
- `framer/webhook/`, `framer/validate-email/`, `framer/register/` — Framer site intake
- `redirection/` — NotaryDash account creation redirect
- `services/<company_id>/` — resolves the service/bundle catalog (`ServiceVariance`) for a client company
- `places/autocomplete/`, `places/details/` — Google Places proxy endpoints

## Admin Panel Guide 

Log in at `/admin/` with your staff account ("IB Order Page Admin"). This is the main control panel for running the order page, viewing orders/customers, and managing affiliates — no coding needed.

### Order Page — managing what customers see and buy

Section: **Order_page**

- **Bundle Groups / Bundles** — the package deals shown on the order page. Edit name, description, price, "discounted price" (the savings shown to the customer), and which add-ons (Option Groups) are offered. Toggle **Is active** to show/hide a bundle without deleting it.
- **Bundle Option Groups / Bundle Option Items** — the add-ons a customer can tick when buying a bundle, and their extra cost.
- **Service Category / Individual Services / Service Forms / Form Items** — the "à la carte" menu (services bought one at a time), their prices, and the configuration screens shown for each.

  > [!IMPORTANT]
  > **Submenu Items (counters/radios) need setup in TWO places — easy to miss one.**
  >
  > A submenu item (e.g. "Number of Witnesses", "Page Count") has two separate jobs: (1) showing up on the order page, and (2) actually changing the price. Each job is configured in a different admin screen. If you only do step 1, the customer sees the selector but the price never changes. If you only do step 2, the price would change but the selector never appears.
  >
  > ```
  >  STEP 1 — Make it VISIBLE                STEP 2 — Make it AFFECT PRICE
  >  (Submenu admin)                         (Submenu Price Change admin)
  >
  >  Submenu Item                            Submenu Item ───► Form Item
  >  "Witness Count"                         "Witness Count"    "Notary In-Person"
  >        │                                       │
  >        ▼                                       ▼
  >  Submenu                                 change_type: "add" (flat $ per unit)
  >  "Signing Options"  ◄── added to               or
  >        │                                 change_type: "multiple" (× base price)
  >        ▼                                       │
  >  Service Form                                  ▼
  >  (shown to customer)                     value: e.g. 5.00
  > ```
  >
  > **Checklist when adding a new counter/radio:**
  > 1. **Submenu Item** admin — create the item (label, type = `counter` or `radio`, min/max).
  > 2. **Submenu** admin — add that item to the relevant Submenu (so it's grouped on screen), and make sure the Submenu is attached to the right **Service Form**.
  > 3. **Submenu Price Change** admin (or the inline list on the Submenu Item page) — link the same Submenu Item to the **Form Item** whose price it should affect, choose `add` (flat amount per unit) or `multiple` (multiplies the Form Item's base price), and set the value.
  >
  > Skipping step 3 = selector shows but price stays flat. Skipping steps 1–2 = price rule exists but customer never sees the option.

- **Discount Levels** — volume discount rules (e.g. order 2 items → 20% off). Edit the percentage or use the **activate/deactivate** bulk action to turn a discount on or off.
- **Check Disclosures** — the mandatory checkbox agreements shown at checkout (e.g. "I agree to..."). Edit the wording, mark required or not, turn on/off with **Active flag**.
- **Service Variances** — controls *which* catalog (which bundles + which à la carte menu) a specific client company sees. Each client can be assigned a custom variance under **Status & Control → Clients**; if none is assigned, they get the default one (`is_default` checked).
- **Terms of Conditions** — the legal text shown to customers, edited with a rich text editor (like Word).
- **Typeform** — forms synced from Typeform (lead intake). Use the **"Sync Definition from Typeform API"** action to pull the latest questions/answers from Typeform into the system. **Typeform Partner Mappings** link a question's answer choice (e.g. "How did you hear about us? → John's Referral") to an affiliate **Partner**.
- **Framer Registration Submissions** — a read-only log of sign-ups coming from the Framer marketing site (email, success/failure, timestamp). You can view these but not edit or delete them.

### Orders, Companies & Users — managing customers

Section: **Stripe_payment**

- **Orders** — every order placed, with company, price, order-protection fee, status (pending/processing/completed/failed), and the linked NotaryDash order ID. This list is **view-only** — staff cannot manually edit order fields.
  - If an order's payment went through in Stripe but it never created a job in NotaryDash (status stuck, no NotaryDash Order ID), select it and run the action **"Process Order (Create NotaryDash Order)"**. This re-runs the fulfillment step using the existing Stripe payment — use this to unstick failed orders instead of asking the customer to pay again.
  - Each order shows its bundles and à la carte items underneath (also view-only).
  - The order list also shows a running total of **Total Price** and **Order Protection** for whatever orders are currently filtered/searched — handy for quick revenue checks.
- **Notary Client Companies** — the notary companies that use the platform (your clients). Search by name, see their Stripe customer ID and payment info, and see all users belonging to that company listed underneath.
- **Notary Users** — individual people who log in under a client company. Search by name/email/company. The **"Is admin"** checkbox can be toggled directly from the list to promote/demote a user to a company admin.
- **Notary Company Groups** — lets you bundle several client companies into one named group (e.g. for shared pricing/catalogs via Service Variances).
- **Stripe Webhook Event Log** — a read-only audit trail of every payment event received from Stripe (succeeded charges, invoices, etc.), useful for investigating a payment issue.

### Affiliates / Referrals — Tolt

Section: **Tolt**

- **Partners** — affiliates/referral partners (name, email, company, payout method/email), synced from the Tolt platform.
- **Customers** — end customers who signed up through a partner's referral link, with their status and which partner referred them.
- **Links** — the tracking links/codes assigned to each partner.

This data is normally synced automatically; the admin views are mainly for searching and verifying who referred whom.

### Webhooks — sending data to other systems

Section: **Webhooks**

- **Webhook Events** — read-only catalog of the events this system can announce (e.g. "Order Completed", "New Notary User Created").
- **Webhook Endpoints** — register an external URL (another system) that should be notified when something happens. Pick which events it should receive, mark **Is active** on/off, and a secret key is generated automatically to let the receiving system verify the message is genuine.
- **Webhook Logs** — read-only delivery history: which event was sent, to which endpoint, whether it succeeded, and the response received. Use this to check whether a notification actually went out (and why it failed, if it did).

## Outbound Webhooks

The `webhooks` app dispatches events (defined in [`webhooks/constants.py`](webhooks/constants.py)) to registered `WebhookEndpoint`s and logs each delivery (`WebhookLog`). Events are fired via `webhook_event_signal` and include:

- `notary_dash.order_created`, `notary_dash.client_company_created/updated`, `notary_dash.user_created/updated`
- `order.created`, `order.pending`, `order.processing`, `order.completed`, `order.completed.v2_sync`, `order.failed`

`order.completed.v2_sync` is fired when a non-external order completes, formatted for the V2 Supabase `orders` table (see [V2 Webhook Sync](#v2-webhook-sync)).

## Notable Management Commands

| Command | App | Purpose |
|---|---|---|
| `pull_clients` / `pull_notary_company`, `pull_notary_users` | `stripe_payment` | Sync NotaryDash companies and users |
| `process_stripe_order`, `create_order_stripe_invoice` | `stripe_payment` | Process orders / generate Stripe invoices |
| `set_company_admins`, `cleanup_duplicate_cards` | `stripe_payment` | Admin maintenance tasks |
| `sync_typeform`, `import_typeform_partners` | `order_page` | Typeform response and partner sync |
| `json_bundles_services`, `json_individual_services` | `order_page` | Export catalog data to JSON |
| `pull_partners`, `pull_links`, `get_tolt_customers` | `tolt` | Sync Tolt affiliate data |
| `sync_webhook_events`, `test_webhooks` | `webhooks` | Replay/test webhook delivery |

---

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
