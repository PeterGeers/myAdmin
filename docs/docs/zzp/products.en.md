# Products & Services

> Manage your product and service catalog.

## Overview

The product catalog is where you manage all products and services you can place on invoices. Each product has a price, VAT code, and type. When creating an invoice, you can quickly add line items from your catalog.

## What You'll Need

- Access to the ZZP module (`zzp_crud` permissions)
- A product name and product code for each item

## Step by Step

### 1. Create a product

1. Go to **ZZP** → **Products**
2. Click **New product**
3. Fill in the fields:

| Field              | Required | Description                                                |
| ------------------ | -------- | ---------------------------------------------------------- |
| Product code       | Yes      | Unique code (e.g., "CONSULT", "DEV-HOUR")                  |
| Name               | Yes      | Name of the product or service                             |
| Type               | Yes      | Product type (e.g., service, product, hours, subscription) |
| Unit price         | Yes      | Default price per unit (excl. VAT)                         |
| VAT code           | Yes      | High (21%), low (9%), or zero (0%)                         |
| Description        | No       | Detailed description                                       |
| Unit of measure    | No       | Unit of measurement (e.g., hour, piece, month)             |
| External reference | No       | Reference to external system                               |

4. Click **Save**

!!! tip
Use clear product codes that you can quickly recognize on invoices. For example, "CONSULT-HOUR" for consultancy hours or "HOSTING-MTH" for monthly hosting.

### 2. Set the VAT code

Each product must have a VAT code. The available codes are:

| VAT code | Rate | When to use                                         |
| -------- | ---- | --------------------------------------------------- |
| High     | 21%  | Standard for most services and products             |
| Low      | 9%   | Reduced rate (e.g., certain food items)             |
| Zero     | 0%   | Exempt or reverse-charged (e.g., export outside EU) |

!!! info
VAT rates are automatically determined based on the invoice date using the tax rates in your administration.

### 3. Edit a product

1. Go to **ZZP** → **Products**
2. Click the product you want to edit
3. Adjust the desired fields
4. Click **Save**

### 4. Delete a product

1. Go to **ZZP** → **Products**
2. Click the product you want to delete
3. Click **Delete**

!!! warning
Products linked to existing invoice lines cannot be deleted. Deactivate the product instead so it's no longer available for new invoices.

## Product types

The available product types are configurable per tenant. By default, the following types are available:

| Type         | Description                  |
| ------------ | ---------------------------- |
| Service      | Delivered services           |
| Product      | Physical or digital product  |
| Hours        | Hourly rate-based service    |
| Subscription | Recurring service or license |

!!! info
Your Tenant Admin can add additional product types via settings without requiring technical changes.

## Tips

!!! tip
Create a product for each service you invoice regularly. This way, when creating an invoice, you only need to select the product and enter the quantity.

- Keep your product codes short and consistent
- Use the "Hours" type for products you link to time tracking
- The unit price is the default price — you can override it per invoice line

## Troubleshooting

| Problem                       | Cause                                         | Solution                                      |
| ----------------------------- | --------------------------------------------- | --------------------------------------------- |
| "Product code already exists" | Product code is not unique within your tenant | Choose a different product code               |
| Product cannot be deleted     | Product is linked to invoice lines            | Deactivate the product instead of deleting    |
| VAT code not available        | Tax rates not configured                      | Ask your Tenant Admin to set up the VAT rates |
