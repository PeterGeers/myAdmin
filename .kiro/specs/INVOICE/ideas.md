# Invoice Module — Ideas & Architecture

## Starting Points

1. Should be a separate feature like FIN and STR
2. Like STR it should be an extension to FIN
3. STR invoices are just prints/hard copies of data already in the STR — no administration. They stay on their own.

## Core Insight

Invoices, Webshop, and ZZP all need the same foundation:

- **Products/Services** (what you sell)
- **Clients** (who you sell to)
- **Invoices** (the document that ties them together)

## Product Types

Not all products need the same handling:

- **Service** — no logistics (consulting, cleaning, maintenance)
- **Digital** — no logistics (licenses, subscriptions, downloads)
- **Physical** — CAN have logistics (goods needing stock, shipping, delivery)

The product type flag determines whether logistics features are available.

## Architecture: Shared Layer + Module-Specific Extensions

### Shared Layer (thin, focused)

```
products table        → id, name, type, price, vat_rate, description, tenant
clients table         → id, name, address, email, vat_number, tenant
invoices table        → id, number, client_id, date, due_date, status, tenant
invoice_lines table   → id, invoice_id, product_id, quantity, price, vat
```

Shared services: `ProductService`, `ClientService`, `InvoiceService`

### Module-Specific Extensions

Each module adds its own concerns on top of the shared layer:

#### INVOICE (base module)

- Products/Services catalog (with type flag)
- Client registry
- Invoice creation, numbering, PDF generation
- Invoice sending (email)
- Invoice status tracking (draft, sent, paid, overdue)

#### WEBSHOP (optional, depends on INVOICE)

- Uses Products and Clients from shared layer
- Adds: orders, cart, checkout, payment_status, shipping_address
- If selling physical products → uses LOGISTICS
- If selling services/digital → no logistics needed
- Auto-generates Invoices on purchase

#### ZZP (optional, depends on INVOICE)

- Uses Products/Services and Clients from shared layer
- Adds: time_entries, recurring_schedules, quotes (offertes)
- Hour registration / time tracking
- Recurring invoices
- Never needs logistics

#### LOGISTICS (optional add-on, only for physical products)

- Stock management (inventory levels)
- Shipping / delivery tracking
- Order fulfillment workflow
- Warehouse / location management

## Why Shared Layer

- One source of truth for Products and Clients — no sync issues, no duplicate data
- Invoice numbering and generation logic written once, used everywhere
- Bug fixes in the invoice engine benefit all modules
- Fits existing architecture pattern (tenant_required, service classes)

## Implementation Order

1. **INVOICE base module** — Products, Clients, Invoice creation (foundation)
2. **WEBSHOP** or **ZZP** — whichever is needed first (plugs into base)
3. **LOGISTICS** — only when physical product fulfillment is needed

## Open Questions

- Invoice numbering format per tenant? (e.g., INV-2026-0001)
--- When a client orders by different tenants the invoice numbers can be the same
- Payment integration needed? (Mollie, Stripe, etc.) 
--- Yes but optional
--- an option for a QR code 
--- Automatic debet
- Email sending for invoices? (SMTP, SES?)
--- Yes
- Credit notes / corrections workflow?
--- Yes
- Multi-currency support needed?
--- Yes
