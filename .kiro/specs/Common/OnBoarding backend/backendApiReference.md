# Backend API Reference: Trial Signup & Provisioning

**Status:** ✅ Complete (Implemented & Tested)
**Date:** March 19, 2026
**Backend:** Flask on Railway — `backend/src/routes/signup_routes.py`, `backend/src/services/signup_service.py`
**Provisioning:** `backend/scripts/provision_tenant.py`

## Architecture

```
Promo App (Next.js/Amplify)           myAdmin Backend (Flask/Railway)
  https://myadmin.jabaki.nl     →     POST /api/signup          (create account)
                                      POST /api/signup/verify   (verify email)
                                      POST /api/signup/resend   (resend code)
                                            ↓
                                      AWS Cognito (eu-west-1_Hdp40eWmu)
                                        └── App client: myAdmin-signup (sl5e75tq75ne1urcajvn0v930)
                                      Railway MySQL (EU-West Amsterdam)
                                        ├── finance DB        (tenants, rekeningschema, tenant_modules)
                                        └── myadmin_promo DB  (pending_signups)
                                      AWS SNS (admin notifications → peter@jabaki.nl)
```

## Endpoints for the Promo App

All endpoints are public (no JWT). Protected by rate limiting, honeypot, and CSRF token.

Base URL: `https://<railway-backend-domain>/api/signup`
CORS: Only `https://myadmin.jabaki.nl` is allowed.

---

### POST /api/signup

Creates a Cognito user and pending signup record. Cognito sends the verification email automatically.

**Request Headers:**

- `Content-Type: application/json`
- `X-CSRF-Token: <csrf_token>` (must match backend `CSRF_SECRET` env var)

**Request Body:**

```json
{
  "firstName": "string (required, 1-50 chars)",
  "lastName": "string (required, 1-50 chars)",
  "email": "string (required, valid email format)",
  "password": "string (required, min 8 chars — Cognito enforces upper/lower/digit/special)",
  "companyName": "string (optional, max 100 chars)",
  "propertyRange": "string (optional, one of: '1-5', '6-20', '21-50', '50+')",
  "referralSource": "string (optional, max 50 chars)",
  "acceptedTerms": true,
  "locale": "string (required, 'nl' or 'en')",
  "honeypot": ""
}
```

**Responses:**

| Status | Meaning                     | Body                                                                                      |
| ------ | --------------------------- | ----------------------------------------------------------------------------------------- |
| `201`  | Success                     | `{ "success": true, "userId": "cognito-sub-uuid", "message": "Verification email sent" }` |
| `200`  | Honeypot triggered (silent) | `{ "success": true, "userId": "ok", "message": "Verification email sent" }`               |
| `403`  | Invalid CSRF token          | `{ "error": "Invalid CSRF token" }`                                                       |
| `409`  | Email already registered    | `{ "error": "Email already registered" }`                                                 |
| `422`  | Validation failed           | `{ "error": "Validation failed", "errors": { "field": "message", ... } }`                 |
| `429`  | Rate limited                | `Too Many Requests` (max 5 per hour per IP)                                               |
| `500`  | Server error                | `{ "error": "Signup failed. Please try again." }`                                         |

**Validation errors returned (all at once, not one-by-one):**

- `firstName`: required, max 50 chars
- `lastName`: required, max 50 chars
- `email`: required, valid format
- `password`: required, min 8 chars
- `acceptedTerms`: must be `true`
- `locale`: must be `nl` or `en`
- `propertyRange`: if provided, must be one of `1-5`, `6-20`, `21-50`, `50+`
- `companyName`: if provided, max 100 chars

**Promo app notes:**

- The `honeypot` field should be a hidden input. If a bot fills it, the backend returns 200 (fake success) without creating anything.
- The CSRF token is a shared secret. The promo app must send it in the `X-CSRF-Token` header or as `csrfToken` in the body.
- After 201, show the user a "check your email" screen with the verification code input.

---

### POST /api/signup/verify

Verifies the email using the 6-digit code from the Cognito verification email.

**Request Body:**

```json
{
  "email": "string (required)",
  "code": "string (required, 6-digit Cognito confirmation code)"
}
```

**Responses:**

| Status | Meaning              | Body                                                                                         |
| ------ | -------------------- | -------------------------------------------------------------------------------------------- |
| `200`  | Verified             | `{ "success": true, "redirectUrl": "https://app.myadmin.jabaki.nl/welcome" }`                |
| `400`  | Invalid/expired code | `{ "error": "Invalid verification code" }` or `{ "error": "Verification code has expired" }` |
| `404`  | Email not found      | `{ "error": "Signup not found" }`                                                            |
| `410`  | Already verified     | `{ "error": "Already verified" }`                                                            |
| `422`  | Missing fields       | `{ "error": "Email and code are required" }`                                                 |
| `429`  | Rate limited         | `Too Many Requests` (max 10 per hour per IP)                                                 |

**Promo app notes:**

- On 200, redirect the user to the `redirectUrl` or show a success page.
- On 400 (invalid code), let the user retry. On 400 (expired), offer the resend option.
- On 410, the user already verified — redirect to login or show "already verified" message.
- No CSRF token required for this endpoint.

---

### POST /api/signup/resend

Resends the Cognito verification email.

**Request Body:**

```json
{
  "email": "string (required)"
}
```

**Responses:**

| Status | Meaning          | Body                                                                    |
| ------ | ---------------- | ----------------------------------------------------------------------- |
| `200`  | Resent           | `{ "success": true, "message": "Verification email resent" }`           |
| `404`  | Email not found  | `{ "error": "Signup not found" }`                                       |
| `410`  | Already verified | `{ "error": "Already verified" }`                                       |
| `422`  | Missing email    | `{ "error": "Email is required" }`                                      |
| `429`  | Rate limited     | `Too Many Requests` (max 1 per minute per IP, also 60s per email in DB) |

**Promo app notes:**

- Show a "resend" link/button on the verification screen.
- Disable the button for 60 seconds after a successful resend.
- No CSRF token required for this endpoint.

---

## Signup Flow for the Promo App

```
┌─────────────────────────────────────────────────────────────────┐
│  PROMO APP (frontend)                                           │
│                                                                 │
│  1. Signup Form                                                 │
│     ├── firstName, lastName, email, password                    │
│     ├── companyName (optional)                                  │
│     ├── propertyRange (optional dropdown)                       │
│     ├── referralSource (optional)                               │
│     ├── acceptedTerms (checkbox, required)                      │
│     ├── locale (nl/en, from browser or selector)                │
│     └── honeypot (hidden field, must be empty)                  │
│                                                                 │
│  2. POST /api/signup → 201                                      │
│     └── Show "Check your email" screen                          │
│                                                                 │
│  3. Verification Screen                                         │
│     ├── 6-digit code input                                      │
│     ├── POST /api/signup/verify → 200                           │
│     │   └── Redirect to redirectUrl or show success             │
│     └── "Resend code" link                                      │
│         └── POST /api/signup/resend → 200                       │
│                                                                 │
│  4. Success Screen                                              │
│     └── "Your account is being set up. We'll email you          │
│          when it's ready."                                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  BACKEND (automatic)                                            │
│                                                                 │
│  On signup: SNS notification → admin                            │
│  On verify: SNS notification → admin ("ready for provisioning") │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ADMIN (manual, via provision_tenant.py)                        │
│                                                                 │
│  python scripts/provision_tenant.py user@example.com            │
│    --name "CompanyName"                                         │
│    --modules "FIN,STR,TENADMIN"                                 │
│                                                                 │
│  What it does:                                                  │
│  1. Looks up pending_signups (myadmin_promo DB)                 │
│  2. Creates tenant in tenants table (finance DB)                │
│  3. Inserts tenant_modules (FIN, STR, TENADMIN)                 │
│  4. Copies chart of accounts from GoodwinSolutions template     │
│  5. Updates Cognito user: custom:tenants = ["CompanyName"]      │
│  6. Marks pending_signups.status = 'provisioned'                │
│  7. Sends SNS notification to admin                             │
│                                                                 │
│  Flags:                                                         │
│    --name       Override administration name (auto-generated    │
│                 from company name or email if not provided)      │
│    --modules    Override modules (default: FIN,STR,TENADMIN)    │
│    --dry-run    Preview without making changes                  │
│    --test-mode  Use testfinance DB                              │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

### myadmin_promo.pending_signups

```sql
CREATE TABLE pending_signups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cognito_user_id VARCHAR(128) NULL,
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    company_name VARCHAR(100) NULL,
    property_range VARCHAR(20) NULL,
    referral_source VARCHAR(50) NULL,
    locale VARCHAR(5) NOT NULL DEFAULT 'nl',
    status ENUM('pending', 'verified', 'provisioned', 'expired') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP NULL,
    provisioned_at TIMESTAMP NULL,
    last_resend_at TIMESTAMP NULL,
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    UNIQUE KEY uk_email (email)
);
```

**Status flow:** `pending` → `verified` → `provisioned`

## Security

| Measure            | Implementation                                                     |
| ------------------ | ------------------------------------------------------------------ |
| Rate limiting      | `flask-limiter`: 5/hour (signup), 10/hour (verify), 1/min (resend) |
| Honeypot           | Hidden `honeypot` field — if filled, returns fake 200              |
| CSRF               | `X-CSRF-Token` header must match `CSRF_SECRET` env var             |
| CORS               | Only `https://myadmin.jabaki.nl` allowed                           |
| Input sanitization | HTML stripped, lengths validated, email regex checked              |
| Password           | Cognito enforces policy (8+ chars, upper, lower, digit, special)   |

## Environment Variables (Backend)

```
PROMO_DB_NAME=myadmin_promo
SIGNUP_COGNITO_USER_POOL_ID=eu-west-1_Hdp40eWmu
SIGNUP_COGNITO_APP_CLIENT_ID=sl5e75tq75ne1urcajvn0v930
SIGNUP_ADMIN_EMAIL=peter@jabaki.nl
CSRF_SECRET=<shared secret between promo app and backend>
SIGNUP_REDIRECT_URL=https://app.myadmin.jabaki.nl/welcome
```

## Cognito Setup

- User pool: `eu-west-1_Hdp40eWmu` (existing myAdmin pool)
- App client: `myAdmin-signup` (`sl5e75tq75ne1urcajvn0v930`) — no client secret, public
- Allowed flows: `sign_up`, `confirm_sign_up`, `resend_confirmation_code` only
- Auto-verified attributes: `email`
- Verification: Cognito sends email with 6-digit code

## Implementation Files

| File                                                          | Purpose                                           |
| ------------------------------------------------------------- | ------------------------------------------------- |
| `backend/src/routes/signup_routes.py`                         | Blueprint with 3 endpoints, rate limiting         |
| `backend/src/services/signup_service.py`                      | Business logic, Cognito calls, DB ops, validation |
| `backend/src/shared_limiter.py`                               | Shared flask-limiter instance                     |
| `backend/scripts/provision_tenant.py`                         | Manual tenant provisioning script                 |
| `backend/src/migrations/20260319_create_myadmin_promo_db.sql` | DB migration                                      |
| `backend/docker-init/01_create_promo_db.sql`                  | Docker init script                                |
| `backend/tests/api/test_signup_routes.py`                     | 20 API tests                                      |
| `backend/tests/unit/test_signup_service.py`                   | 24 unit tests                                     |

## Future: Automated Provisioning (Phase 2)

Currently provisioning is manual via `provision_tenant.py`. Future automation:

1. Build a provisioning API endpoint (POST `/api/admin/provision`) callable from an admin dashboard
2. Accept `administration_name` and `modules` from the frontend
3. Trigger automatically after email verification (background job or Cognito post-confirmation Lambda)
4. Set trial plan with expiry (e.g. 2 months)
5. Send automated welcome email with user manual link

## Future: Passkey Authentication

**Reference:** `C:\Users\peter\aws\h-dcn` (already implemented)

Cognito supports passkeys (WebAuthn/FIDO2) natively. Key lesson from h-dcn: Cognito creates separate user records for different auth methods — need prime ID resolution after login.

**Cognito gotcha:** MFA and passkeys can't coexist at pool level. Choose one.
