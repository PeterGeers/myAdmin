# Product & Order Architecture Analysis

## Purpose

This document analyzes a product/booking model and provides architecture recommendations for building it as a modern multi tenant webshop SPA with a generic, extensible product catalog.

---

## 1. Current Product Catalog

### Orderable Items

| #   | Product                 | Unit                 | Price   | VAT | Behaviour                   |
| --- | ----------------------- | -------------------- | ------- | --- | --------------------------- |
| 1   | Meeting attendance      | per delegate         | €50.00  | 21% | Mandatory per delegate      |
| 2   | Saturday dinner & party | per person           | €99.50  | 21% | Optional per delegate/guest |
| 3   | T-shirt                 | per person           | €25.00  | 21% | Optional per delegate/guest |
| 4   | Single room             | per night            | €175.00 | 9%  | Optional                    |
| 5   | Twin/Double room        | per night            | €185.00 | 9%  | Optional                    |
| 6   | Triple room             | per night            | €285.00 | 9%  | Optional                    |
| 7   | Airport transfer        | per person per trip  | €5.00   | 21% | Optional, requires room     |
| 8   | Tourist tax             | per person per night | €2.30   | 0%  | Auto-calculated from rooms  |

### Product Categories

| Category        | Items                      | Custom data per line                               |
| --------------- | -------------------------- | -------------------------------------------------- |
| People          | Delegates, Guests          | Name, position, shirt size, party Y/N              |
| Accommodation   | Single, Twin, Triple rooms | Arrival/departure dates, guest names, location     |
| Transport       | Airport transfers          | Direction, airport, flight no, date, time, persons |
| Auto-calculated | Tourist tax                | Derived from room occupancy × nights               |

### Quantity Limits

| Category  | Min | Max (default) | Override              |
| --------- | --- | ------------- | --------------------- |
| Delegates | 1   | 3             | Per-customer by admin |
| Guests    | 0   | 10            | Per-customer by admin |
| Rooms     | 0   | 6             | Per-customer by admin |
| Travels   | 0   | 4             | Per-customer by admin |

### Charge Calculation

```
Total = Meeting + Party + T-shirts + Rooms + Tourist Tax + Transfers

Meeting     = num_delegates × €50.00
Party       = num_party_attendees × €99.50
T-shirts    = num_shirts × €25.00
Rooms       = Σ (nights × room_type_price) for each room
Tourist Tax = Σ (guests_in_room × nights × €2.30) for each room
Transfers   = (arrival_persons + departure_persons) × €5.00
```

---

## 2. Recommended Data Architecture

### Multi-Tenancy Model

All tables include a `tenant_id` column for data isolation. This follows the same shared-database, tenant-per-row pattern used in myAdmin.

| Aspect             | Approach                                                               |
| ------------------ | ---------------------------------------------------------------------- |
| Isolation          | Row-level via `tenant_id` on every table                               |
| Enforcement        | Middleware injects `tenant_id` from JWT; all queries filter by it      |
| Unique constraints | Scoped to tenant (e.g. `UNIQUE(tenant_id, reference)`)                 |
| Indexes            | Composite indexes with `tenant_id` as leading column                   |
| Admin access       | Super-admin can query across tenants; regular users see only their own |

### Core Schema (Hybrid Approach)

A generic product catalog with JSON metadata for item-specific data. This gives flexibility without requiring a new table per product type.

```sql
-- Product catalog
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    name VARCHAR(100) NOT NULL,
    category VARCHAR(30),
    base_price NUMERIC(10,2),
    vat DECIMAL(3,2),
    has_variants BOOLEAN DEFAULT FALSE,
    metadata_schema JSON,               -- defines custom fields for this product
    min_quantity INTEGER DEFAULT 0,
    max_quantity INTEGER DEFAULT 0,     -- 0 = unlimited
    global_stock INTEGER DEFAULT 0,     -- 0 = unlimited
    available_from TIMESTAMP,
    available_until TIMESTAMP,
    early_bird_price NUMERIC(10,2),
    early_bird_until TIMESTAMP,
    active BOOLEAN DEFAULT TRUE,
    INDEX idx_products_tenant (tenant_id),
    INDEX idx_products_tenant_category (tenant_id, category)
);

-- Orders
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'draft',
    reference VARCHAR(20),
    total NUMERIC(10,2) DEFAULT 0,
    version INTEGER DEFAULT 0,          -- optimistic locking
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP,
    submitted_at TIMESTAMP,
    locked_at TIMESTAMP,
    UNIQUE(tenant_id, reference),       -- reference unique per tenant
    INDEX idx_orders_tenant (tenant_id),
    INDEX idx_orders_tenant_user (tenant_id, user_id),
    INDEX idx_orders_tenant_status (tenant_id, status)
);

-- Order lines with flexible metadata
CREATE TABLE order_lines (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation (denormalized for query performance)
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    variant_id INTEGER REFERENCES product_variants(id),
    quantity INTEGER DEFAULT 1,
    unit_price NUMERIC(10,2),
    metadata JSON,                       -- item-specific data (name, dates, etc.)
    INDEX idx_order_lines_tenant_order (tenant_id, order_id),
    INDEX idx_order_lines_product (tenant_id, product_id)
);
```

### Why This Approach

| Concern                         | Solution                                           |
| ------------------------------- | -------------------------------------------------- |
| Different data per product type | JSON metadata on order lines                       |
| Queryability                    | Database views per category                        |
| Schema evolution                | Add fields to metadata_schema, no migrations       |
| Type safety                     | Validated at API/frontend level via schema         |
| Simplicity                      | One `order_lines` table for everything             |
| Tenant isolation                | `tenant_id` on every table, enforced by middleware |
| Concurrency                     | `version` column for optimistic locking            |

---

## 3. Product Variants (Size, Colour)

For products with options that affect stock or price (like t-shirts):

```sql
CREATE TABLE product_options (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    product_id INTEGER REFERENCES products(id),
    name VARCHAR(50) NOT NULL,         -- "Size", "Colour"
    position INTEGER DEFAULT 0,
    INDEX idx_product_options_tenant (tenant_id, product_id)
);

CREATE TABLE option_values (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    option_id INTEGER REFERENCES product_options(id),
    value VARCHAR(50) NOT NULL,         -- "Male XL", "Black"
    position INTEGER DEFAULT 0
);

CREATE TABLE product_variants (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    product_id INTEGER REFERENCES products(id),
    sku VARCHAR(50),
    price_override NUMERIC(10,2),       -- NULL = use base_price
    stock INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    UNIQUE(tenant_id, sku),             -- SKU unique per tenant
    INDEX idx_product_variants_tenant (tenant_id, product_id)
);

CREATE TABLE variant_option_values (
    variant_id INTEGER REFERENCES product_variants(id),
    option_value_id INTEGER REFERENCES option_values(id),
    PRIMARY KEY (variant_id, option_value_id)
);
```

**When to use variants vs metadata:**

| Situation                         | Use                                  |
| --------------------------------- | ------------------------------------ |
| Same price, no stock tracking     | Store options in order_line metadata |
| Price varies by option            | Variant model                        |
| Need stock per combination        | Variant model                        |
| Few options (just size)           | Metadata is fine                     |
| Many axes (size × colour × print) | Variant model                        |

---

## 4. Product Media & File Storage

### Default Storage: Amazon S3

The webshop uses **S3 as its primary data store** for all file assets (product images, order attachments, generated documents). This is independent of myAdmin's Google Drive integration.

| Concern        | Approach                                                                     |
| -------------- | ---------------------------------------------------------------------------- |
| Storage        | S3 bucket per environment, tenant-prefixed paths                             |
| Delivery       | CloudFront CDN for public assets (product images)                            |
| Access control | Pre-signed URLs for private assets (order documents)                         |
| Upload         | Direct-to-S3 via pre-signed POST (bypasses backend for large files)          |
| Lifecycle      | S3 lifecycle rules for temp uploads (auto-delete after 24h if not confirmed) |

### Bucket Structure

```
s3://webshop-assets-{env}/
├── {tenant_id}/
│   ├── products/{product_id}/
│   │   ├── hero.jpg
│   │   ├── gallery/
│   │   └── variants/{variant-sku}.jpg
│   ├── orders/{order_id}/
│   │   ├── confirmation.pdf
│   │   └── attachments/
│   └── tmp/                            -- pre-signed upload landing zone
│       └── {upload_id}/
```

### Media Table

```sql
CREATE TABLE product_media (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    product_id INTEGER REFERENCES products(id),
    variant_id INTEGER REFERENCES product_variants(id),  -- NULL = product-level
    type VARCHAR(10) NOT NULL,          -- 'image', 'video'
    s3_key VARCHAR(500) NOT NULL,       -- S3 object key (not full URL)
    alt_text VARCHAR(200),
    position INTEGER DEFAULT 0,         -- 0 = hero image
    is_thumbnail BOOLEAN DEFAULT FALSE,
    INDEX idx_product_media_tenant (tenant_id, product_id)
);
```

### CDN & URL Resolution

```
Public URL:  https://cdn.webshop.example.com/{tenant_id}/products/{id}/hero.jpg
Private URL: Generated via pre-signed S3 URL (expires in 15 min)
```

**Fallback logic:** If a variant has no media, display the product-level images.

---

## 5. Product Dependencies & Rules

```sql
CREATE TABLE product_rules (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    product_id INTEGER REFERENCES products(id),
    rule_type VARCHAR(30) NOT NULL,     -- 'requires', 'excludes', 'auto_add', 'auto_calculate'
    target_product_id INTEGER REFERENCES products(id),
    condition JSON,
    message VARCHAR(200),
    INDEX idx_product_rules_tenant (tenant_id, product_id)
);
```

**Rule types in the PM app:**

| Rule             | Example                                  | Effect                                         |
| ---------------- | ---------------------------------------- | ---------------------------------------------- |
| `requires`       | Transfer requires Room                   | Can't add transfer without a room in the order |
| `auto_add`       | Meeting fee per Delegate                 | Automatically added when delegate is added     |
| `auto_calculate` | Tourist tax from rooms                   | Computed from room occupancy × nights × rate   |
| `excludes`       | Single OR Twin (not both for same dates) | Prevents conflicting selections                |

---

## 6. Time-Based Availability

Built into the `products` table:

| Field              | Purpose             | PM App equivalent                    |
| ------------------ | ------------------- | ------------------------------------ |
| `available_from`   | Product launch date | Site goes live                       |
| `available_until`  | Product end date    | `REGISTRATION_CLOSE_DATE`            |
| `early_bird_price` | Discounted price    | Not used yet, but available          |
| `early_bird_until` | Early bird deadline | Could incentivize early registration |

Additional order-level deadlines:

| Deadline              | Purpose                                                 |
| --------------------- | ------------------------------------------------------- |
| Modification deadline | Last date to edit submitted orders (`LAST_CHANGE_DATE`) |
| Payment deadline      | Last date to pay (`PAYMENT_DATE`)                       |

---

## 7. Discounts & Bundles (Optional)

```sql
CREATE TABLE discounts (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,     -- tenant isolation
    name VARCHAR(100),
    type VARCHAR(20),               -- 'percentage', 'fixed', 'free_product'
    value NUMERIC(10,2),
    code VARCHAR(30),               -- NULL = automatic
    min_order_total NUMERIC(10,2),
    product_id INTEGER REFERENCES products(id),
    available_from TIMESTAMP,
    available_until TIMESTAMP,
    max_uses INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    UNIQUE(tenant_id, code),        -- code unique per tenant
    INDEX idx_discounts_tenant (tenant_id)
);
```

Not needed for the PM app, but available for future use (early-bird discounts, group rates, etc.).

---

## 8. Order Lifecycle

### State Machine

```
DRAFT → SAVED → SUBMITTED → PAID → LOCKED
                    ↑
                    └── (re-submit after edit)
```

### API Endpoints

```
POST   /api/orders              → create draft (tenant_id from JWT)
PUT    /api/orders/:id          → save/update (tenant-scoped)
POST   /api/orders/:id/submit   → finalize + send confirmation email
POST   /api/orders/:id/pay      → record payment (admin, tenant-scoped)
POST   /api/orders/:id/lock     → lock order (admin, tenant-scoped)
DELETE /api/orders/:id          → cancel (draft/saved only, tenant-scoped)
```

### Permissions Matrix

| Action         | Draft | Saved | Submitted           | Paid      | Locked |
| -------------- | ----- | ----- | ------------------- | --------- | ------ |
| View           | ✓     | ✓     | ✓                   | ✓         | ✓      |
| Edit           | ✓     | ✓     | ✓ (before deadline) | ✗         | ✗      |
| Submit         | ✗     | ✓     | ✓ (re-submit)       | ✗         | ✗      |
| Cancel         | ✓     | ✓     | ✗                   | ✗         | ✗      |
| Record payment | ✗     | ✗     | ✓ (admin)           | ✓ (admin) | ✗      |

---

## 9. Schema-Driven Forms

Products define their own form fields via `metadata_schema`:

```json
{
  "fields": [
    { "name": "first_name", "type": "text", "required": true },
    { "name": "last_name", "type": "text", "required": true },
    { "name": "position", "type": "text", "required": false },
    {
      "name": "shirt_size",
      "type": "select",
      "options": ["Male S", "Male M", "Male L", "Male XL"]
    },
    { "name": "party", "type": "boolean", "label": "Attending party?" }
  ]
}
```

The SPA renders form fields dynamically from this schema. Adding a new product type requires no frontend code changes — just define the schema in the database.

---

## 10. Feature Optionality

All features are modular — implement only what you need:

| Feature                                 | Required for PM app? | Add when...                                   |
| --------------------------------------- | -------------------- | --------------------------------------------- |
| Multi-tenancy (`tenant_id` isolation)   | ✅ Yes               | Always — shared infrastructure, isolated data |
| Core schema (products + orders + lines) | ✅ Yes               | Always                                        |
| S3 file storage (media, documents)      | ✅ Yes               | Always — default data store for all assets    |
| JSON metadata on order lines            | ✅ Yes               | Products need custom data                     |
| Order lifecycle states                  | ✅ Yes               | Always                                        |
| Optimistic locking (`version` column)   | ✅ Yes               | Always — prevents concurrent edit conflicts   |
| Quantity rules (min/max)                | ✅ Yes               | Products have limits                          |
| Time-based availability                 | ✅ Yes               | Registration has open/close dates             |
| Product dependencies                    | ✅ Yes               | Products have logical relationships           |
| Schema-driven forms                     | ✅ Yes               | Multiple product types with different fields  |
| Product variants                        | ⚡ Optional          | Options affect stock or price                 |
| Product media                           | ⚡ Optional          | Visual product catalog needed                 |
| Discounts & bundles                     | ⚡ Optional          | Promotions or coupon codes needed             |
| Per-customer overrides                  | ⚡ Optional          | Admin needs to adjust limits per user         |

### Minimum Viable Implementation

1. Products table with `metadata_schema`
2. Orders + order_lines with JSONB metadata
3. Order lifecycle (draft → submitted → paid)
4. Quantity rules (min/max per product)
5. Time-based availability (open/close dates)
6. Basic dependency rules (requires/excludes)

Everything else layers on top without schema changes.

---

## 11. Review Notes & Open Questions

### Must Address

| #   | Topic                         | Issue                                                                                            | Recommendation                                                                                                     |
| --- | ----------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| 1   | ~~**Multi-tenancy**~~         | ✅ Resolved — `tenant_id` added to all tables with tenant-scoped indexes and unique constraints. | —                                                                                                                  |
| 2   | **Database dialect**          | Schema uses PostgreSQL syntax (`SERIAL`, `JSONB`, `NUMERIC`) but the stack is MySQL 8.0.         | Rewrite DDL for MySQL: `INT AUTO_INCREMENT`, `JSON`, `DECIMAL(10,2)`. If intentionally Postgres, state explicitly. |
| 3   | ~~**Concurrency / locking**~~ | ✅ Resolved — `version` column added to `orders` table for optimistic locking.                   | —                                                                                                                  |

### Should Address

| #   | Topic                          | Issue                                                                                                                       | Recommendation                                                                                                           |
| --- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 4   | **Tourist tax calculation**    | `product_rules` stores a `condition` JSONB but no description of how the calculation engine evaluates auto-calculate rules. | Document the calculation DSL or note it's handled in application code with specific logic.                               |
| 5   | **Order reference generation** | `reference VARCHAR(20) UNIQUE` — no generation strategy defined.                                                            | Define format (e.g. `PM-2026-0042`) and generation approach (sequential, UUID-based, etc.).                              |
| 6   | **Audit trail**                | Existing myAdmin has audit logging but this doc doesn't mention it.                                                         | Clarify whether order changes are audited, and whether to reuse the existing audit infrastructure.                       |
| 7   | **Payment integration**        | Lifecycle shows `PAID` state but no payment provider is mentioned.                                                          | Add a note — even "manual admin marking for now, payment provider TBD" clarifies scope.                                  |
| 8   | **Soft deletes**               | No `deleted_at` on orders or products. Deactivated products may still be referenced by historical order lines.              | The `active` flag handles catalog visibility; confirm historical order lines remain valid when a product is deactivated. |

### Nice to Have

| #   | Topic                       | Issue                                                                                                  | Recommendation                                                                                                                           |
| --- | --------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 9   | **Index strategy**          | No indexes defined beyond primary keys.                                                                | Document key indexes: `order_lines.order_id`, `order_lines.product_id`, JSON path indexes for metadata queries.                          |
| 10  | ~~**Storage divergence**~~  | ✅ Resolved — S3 is the default data store for the webshop, independent of myAdmin's Google Drive.     | —                                                                                                                                        |
| 11  | **Discount race condition** | `used_count` column on `discounts` table is vulnerable to race conditions under concurrent redemption. | Consider a separate `discount_redemptions` table or use atomic `UPDATE ... SET used_count = used_count + 1 WHERE used_count < max_uses`. |

---

## 12. Database Strategy: Single vs Separate

### Options

| Approach            | Description                                     |
| ------------------- | ----------------------------------------------- |
| **Single DB**       | Add webshop tables to existing MySQL instance   |
| **Separate schema** | Own schema (`webshop.*`) in same MySQL instance |
| **Separate DB**     | Independent database (potentially PostgreSQL)   |

### Trade-offs Summary

| Factor                 | Single DB                     | Separate DB                       |
| ---------------------- | ----------------------------- | --------------------------------- |
| Operational complexity | Low — one backup, one monitor | Higher — two of everything        |
| Cross-domain queries   | Direct JOINs                  | API calls or data replication     |
| Scaling independence   | No — shared resources         | Yes — independent scaling         |
| Technology freedom     | Locked to MySQL 8.0           | Can use PostgreSQL (better JSONB) |
| Schema coupling        | Risk of accidental coupling   | Clean domain boundary             |
| Transactions           | ACID across domains           | Eventual consistency              |
| Local dev setup        | Simple                        | More complex                      |

### Recommendation

**Start with a separate schema in the same MySQL instance** (`webshop.*` alongside `myadmin.*`).

Rationale:

- Logical separation without operational overhead
- No cross-schema JOINs from day one — enforces clean boundaries
- Shared data (tenants, auth) accessed via API/JWT, not direct table access
- Easy to migrate to a separate instance (or PostgreSQL) later if needed
- Webshop is mostly self-contained; main integration point is "push completed orders into myAdmin as invoices" — an event/API call regardless of DB choice

### When to split to a separate database

- Webshop traffic becomes public-facing with spiky load while myAdmin stays internal
- JSON query ergonomics in MySQL become a bottleneck (complex metadata queries, frequent schema-driven form validation at DB level)
- The webshop needs to scale or deploy independently
- Team ownership splits (separate team owns the webshop)
