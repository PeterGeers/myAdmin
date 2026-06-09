# AWS Accounts Strategy

## Context & Decisions

### Questions & Answers

| Question                                      | Answer                                                                   |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| Is this nonprofit version a separate product? | No — same features/branding                                              |
| Expected scale?                               | Still not clear                                                          |
| Stay with Flask + MySQL or go serverless?     | Already have Lambda/DynamoDB platform (h-dcn project). Not multi-tenant. |
| Applied for AWS nonprofit credits?            | Yes — $1K/year                                                           |

### Strategic Decision

**Three separate concerns, three separate paths:**

| #   | Concern                    | Action                                                    | Account   |
| --- | -------------------------- | --------------------------------------------------------- | --------- |
| 1   | h-dcn application          | Migrate from personal AWS account → nonprofit AWS account | Nonprofit |
| 2   | Webshop (product-approach) | Upgrade to new requirements + S3 support                  | Nonprofit |
| 3   | myAdmin                    | Leave as-is — no changes                                  | Personal  |

---

## Account Layout

```
┌─────────────────────────────────────┐
│  Personal AWS Account               │
│  ├── myAdmin (Flask + MySQL)        │
│  │   └── stays here, unchanged     │
│  └── h-dcn (Lambda + DynamoDB)      │
│       └── TO BE MIGRATED ──────────────┐
└─────────────────────────────────────┘   │
                                          ▼
┌─────────────────────────────────────┐
│  Nonprofit AWS Account ($1K/yr)     │
│  ├── h-dcn (migrated)              │
│  │   └── Lambda + DynamoDB         │
│  └── Webshop (upgraded)            │
│       └── Lambda + DynamoDB + S3   │
└─────────────────────────────────────┘
```

---

## Phase 1: Migrate h-dcn to Nonprofit Account

### What Needs to Move

| Resource Type            | Migration Approach                            |
| ------------------------ | --------------------------------------------- |
| Lambda functions         | Re-deploy via IaC (SAM/CDK/Terraform)         |
| DynamoDB tables          | Export → S3 → Import (or AWS Backup)          |
| API Gateway              | Re-create (not transferable between accounts) |
| Cognito user pool        | Re-create + migrate users (if any)            |
| S3 buckets               | Cross-account copy (`aws s3 sync`)            |
| IAM roles/policies       | Re-create in new account                      |
| CloudFront distributions | Re-create                                     |
| Route 53 / DNS           | Update to point to new resources              |
| Secrets / SSM parameters | Re-create in new account                      |
| CloudWatch logs/alarms   | Re-create                                     |

### Migration Steps

1. **Inventory** — Document all h-dcn resources in personal account (use AWS Resource Explorer or tag-based search)
2. **IaC audit** — Confirm h-dcn has complete IaC (SAM/CDK/Terraform). If not, reverse-engineer it first.
3. **Data export** — Export DynamoDB tables to S3, copy S3 assets cross-account
4. **Deploy to nonprofit** — Run IaC against the nonprofit account
5. **Data import** — Load DynamoDB data into new tables
6. **DNS cutover** — Point domain(s) to new account resources
7. **Verify** — End-to-end testing in new account
8. **Decommission** — Remove h-dcn resources from personal account

### Risks & Mitigations

| Risk                      | Mitigation                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------ |
| Downtime during migration | Run both in parallel, DNS switch at the end                                          |
| Data loss                 | Export + verify row counts before decommission                                       |
| Hardcoded account IDs     | Search codebase for old account ID, replace                                          |
| Cross-account permissions | Use resource policies or assume-role during migration                                |
| Cognito user migration    | Export users, re-create with forced password reset (or use migration Lambda trigger) |

---

## Phase 2: Upgrade Webshop

### Current State

The webshop (documented in `product-approach.md`) defines:

- Product catalog with variants, rules, dependencies
- Order lifecycle (draft → submitted → paid → locked)
- Schema-driven forms
- Multi-tenancy via `tenant_id`

### Target State (on Nonprofit Account)

| Layer        | Technology                   | Notes                                   |
| ------------ | ---------------------------- | --------------------------------------- |
| Frontend     | React SPA on S3 + CloudFront | Same as product-approach design         |
| API          | API Gateway + Lambda         | Aligns with h-dcn pattern               |
| Database     | DynamoDB                     | Single-table design or table-per-entity |
| File storage | S3                           | Product media, order documents, uploads |
| Auth         | Cognito                      | Shared with h-dcn (same user pool)      |
| Email        | SES                          | Order confirmations, notifications      |

### Key Upgrades from product-approach.md

1. **S3 integration** — Product media, order attachments, pre-signed uploads (Section 4 of product-approach)
2. **DynamoDB data model** — Translate the relational schema to DynamoDB access patterns
3. **Serverless backend** — Lambda handlers instead of Flask routes
4. **CloudFront CDN** — For both frontend hosting and media delivery

### DynamoDB Considerations

The product-approach doc uses a relational model (products, orders, order_lines, variants). For DynamoDB:

| Relational Pattern | DynamoDB Approach                                                               |
| ------------------ | ------------------------------------------------------------------------------- |
| Products table     | PK: `TENANT#<id>`, SK: `PRODUCT#<id>`                                           |
| Order + lines      | PK: `TENANT#<id>`, SK: `ORDER#<id>` with lines as nested list or separate items |
| Variants           | PK: `TENANT#<id>`, SK: `VARIANT#<product_id>#<variant_id>`                      |
| Product rules      | PK: `TENANT#<id>`, SK: `RULE#<product_id>#<rule_id>`                            |
| Queries by status  | GSI: `tenant_id-status-index`                                                   |

### S3 Bucket Structure (from product-approach.md)

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
│   └── tmp/
│       └── {upload_id}/
```

---

## Phase 3: myAdmin — No Changes

myAdmin stays on the personal AWS account with its current architecture:

- Flask + MySQL (Docker)
- AWS Cognito (personal account pool)
- Google Drive integration
- No migration, no changes

---

## Budget Estimate (Nonprofit Account)

### Monthly Costs at Low Scale

| Service      | Estimated Cost | Notes                                         |
| ------------ | -------------- | --------------------------------------------- |
| Lambda       | $0             | Free tier: 1M requests/month                  |
| DynamoDB     | $0             | Free tier: 25 GB + 25 WCU/RCU                 |
| S3 (storage) | $0–2           | First 5 GB free, then $0.023/GB               |
| CloudFront   | $0             | First 1 TB/month free                         |
| API Gateway  | $0–3           | First 1M calls free, then $3.50/M             |
| Cognito      | $0             | First 50K MAU free                            |
| SES          | $0–1           | First 62K emails/month free (from EC2/Lambda) |
| **Total**    | **$0–6/month** | Well within $1K/year budget                   |

### When Costs Increase

- DynamoDB: > 25 GB storage or > 25 RCU/WCU sustained
- Lambda: > 1M requests or > 400K GB-seconds/month
- S3: Significant media storage (> 50 GB)
- CloudFront: > 1 TB transfer/month

At nonprofit scale, you'll likely stay within free tier for a long time.

---

## Open Questions

| #   | Question                                                                | Status |
| --- | ----------------------------------------------------------------------- | ------ |
| 1   | Does h-dcn have complete IaC, or is it manually provisioned?            | TBD    |
| 2   | Are there existing users in h-dcn's Cognito pool that need migration?   | TBD    |
| 3   | Should the webshop share h-dcn's Cognito user pool or have its own?     | TBD    |
| 4   | What domain(s) will be used for the nonprofit services?                 | TBD    |
| 5   | Is there any data in h-dcn DynamoDB tables that needs to be preserved?  | TBD    |
| 6   | What's the timeline priority — migrate h-dcn first, then build webshop? | TBD    |

---

## Next Steps

1. **Inventory h-dcn resources** — List all AWS resources in personal account
2. **Verify IaC completeness** — Can h-dcn be fully deployed from code?
3. **Set up nonprofit account** — Organizations, IAM, billing alerts
4. **Execute Phase 1** — Migrate h-dcn
5. **Design DynamoDB model** — Translate product-approach schema for webshop
6. **Execute Phase 2** — Build/upgrade webshop on nonprofit account
