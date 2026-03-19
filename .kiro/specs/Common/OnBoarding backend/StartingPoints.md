# Backend Starting Points: Trial Signup API

**Status:** Ready for Implementation
**Date:** March 18, 2026
**Context:** The myAdmin website (Next.js on Amplify, separate repo) needs these API endpoints on the existing Flask backend (Railway) to complete its signup page.

## Architecture Overview

```
myAdmin Website (Next.js/Amplify)     myAdmin Backend (Flask/Railway)
  https://myadmin.jabaki.nl     →     POST /api/signup
                                      POST /api/signup/verify
                                      POST /api/signup/resend
                                            ↓
                                      AWS Cognito (eu-west-1, existing user pool)
                                        └── Separate app client for signup flow
                                      Railway MySQL (EU-West Amsterdam)
                                        ├── finance DB        (existing — mutaties, rekeningschema, tenants, etc.)
                                        └── myadmin_promo DB  (new — pending_signups, onboarding data)
                                      AWS SES/SNS (notifications)
```

All three endpoints are public (no JWT auth required). Protection via rate limiting, honeypot field, and CSRF token validation.

## Cognito Strategy: Same Pool, Separate App Client

Uses the existing myAdmin Cognito user pool (eu-west-1) — not a separate pool.

**Why same pool:**

- The signup creates a user who will eventually use the myAdmin app — same user, same pool
- After provisioning, the user logs in with the same credentials. No migration needed.
- One pool = one source of truth for "does this email exist?" — prevents duplicate accounts
- Existing password policies, email verification, and custom attributes (`custom:administration`, roles) are reused

**Separate app client:** Create a new app client in the same pool for the signup flow. This app client:

- Has no client secret (required for public signup from the website)
- Only allows `sign_up`, `confirm_sign_up`, `resend_confirmation_code` flows
- Does NOT allow `initiate_auth` (users can't log in via the promo app client — they use the main app client for that)

**Signup → App flow:**

1. Website calls `/api/signup` → backend creates user in existing pool (unverified, no `custom:administration` yet)
2. User verifies email → `pending_signups.status = 'verified'`
3. Admin provisions tenant → adds `custom:administration` attribute to the Cognito user
4. User logs into the myAdmin app with the same email/password — Cognito already knows them

## Endpoint Specifications

### 1. POST /api/signup

Create a new trial signup.

**Request:**

```json
{
  "firstName": "string (required, 1-50 chars)",
  "lastName": "string (required, 1-50 chars)",
  "email": "string (required, valid email)",
  "password": "string (required, min 8 chars, 1 upper, 1 lower, 1 digit, 1 special)",
  "companyName": "string (optional, max 100 chars)",
  "propertyRange": "string (optional, e.g. '1-5', '6-20', '21-50', '50+')",
  "referralSource": "string (optional, e.g. 'google', 'friend', 'social')",
  "acceptedTerms": "boolean (required, must be true)",
  "locale": "string (required, 'nl' or 'en')",
  "honeypot": "string (optional, must be empty — bot detection)",
  "csrfToken": "string (required)"
}
```

**Response 201:**

```json
{
  "success": true,
  "userId": "cognito-sub-uuid",
  "message": "Verification email sent"
}
```

**Error Responses:**

- `409` — Email already exists in Cognito
- `422` — Validation error (details in `errors` array)
- `429` — Rate limited (max 5 signups per IP per hour)

**Logic:**

1. Validate honeypot field (reject if filled → bot)
2. Validate CSRF token
3. Validate all input fields
4. Create user in Cognito user pool (eu-west-1) with email as username
5. Insert row into `pending_signups` table
6. Cognito auto-sends verification email
7. Send admin notification to peter@jabaki.nl via SES/SNS
8. Return 201 with Cognito `sub` as userId

### 2. POST /api/signup/verify

Verify email after user clicks the Cognito verification link.

**Request:**

```json
{
  "email": "string (required)",
  "code": "string (required, Cognito confirmation code)"
}
```

**Response 200:**

```json
{
  "success": true,
  "redirectUrl": "https://app.myadmin.jabaki.nl/welcome"
}
```

**Error Responses:**

- `400` — Invalid or expired code
- `404` — Email not found in pending_signups
- `410` — Already verified

**Logic:**

1. Call Cognito `confirm_sign_up` with email + code
2. Update `pending_signups` set `verified_at = NOW()`, `status = 'verified'`
3. Send admin notification: "New verified signup — ready for tenant provisioning"
4. Return redirect URL to the app

### 3. POST /api/signup/resend

Resend the Cognito verification email.

**Request:**

```json
{
  "email": "string (required)"
}
```

**Response 200:**

```json
{
  "success": true,
  "message": "Verification email resent"
}
```

**Error Responses:**

- `404` — Email not found
- `410` — Already verified
- `429` — Rate limited (1 per 60 seconds per email)

**Logic:**

1. Check `pending_signups` for email, reject if not found or already verified
2. Check rate limit (last resend < 60s ago → 429)
3. Call Cognito `resend_confirmation_code`
4. Update `pending_signups.last_resend_at = NOW()`

## Database: Separate myadmin_promo Database

Signup/onboarding data lives in a separate database (`myadmin_promo`) on the same Railway MySQL server, keeping it isolated from the financial data in the existing `finance` database.

**Why separate?**

- Security isolation: signup endpoints are public, finance endpoints require auth
- Clean separation of concerns (promo/onboarding vs financial transactions)
- Independent cleanup/reset without touching finance data

**Create the database on Railway MySQL:**

```sql
CREATE DATABASE myadmin_promo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE myadmin_promo;
```

**Local Docker dev:** Add an init script so the MySQL container creates `myadmin_promo` on first startup. Create `backend/docker-init/01_create_promo_db.sql`:

```sql
CREATE DATABASE IF NOT EXISTS myadmin_promo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON myadmin_promo.* TO 'peter'@'%';
FLUSH PRIVILEGES;
```

Mount it in `docker-compose.yml`:

```yaml
mysql:
  volumes:
    - ./mysql_data:/var/lib/mysql
    - ./backend/docker-init:/docker-entrypoint-initdb.d
```

> Note: MySQL init scripts only run on first container startup (empty data dir). For existing containers, run the SQL manually: `docker exec -i <mysql_container> mysql -u peter -p < backend/docker-init/01_create_promo_db.sql`

**Environment variable:** `PROMO_DB_NAME=myadmin_promo` (alongside existing `DB_NAME` for finance)

**Connection:** `signup_service.py` uses a dedicated `DatabaseManager` instance pointing to `myadmin_promo`:

```python
# In signup_service.py — uses existing pool, separate app client
cognito_client.sign_up(
    ClientId=SIGNUP_COGNITO_APP_CLIENT_ID,  # Separate app client (no secret, signup-only)
    Username=email,
    Password=password,
    UserAttributes=[...]
)
```

### pending_signups Table

Run on Railway MySQL in the `myadmin_promo` database:

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
    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    UNIQUE KEY uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## Security

| Measure            | Implementation                                                                       |
| ------------------ | ------------------------------------------------------------------------------------ |
| Rate limiting      | `flask-limiter` with Redis or in-memory store. 5 signups/IP/hour, 1 resend/email/60s |
| Honeypot           | Hidden form field `honeypot` — reject if non-empty                                   |
| CSRF               | Token generated by website, validated by backend (shared secret or session-based)    |
| CORS               | Allow only `https://myadmin.jabaki.nl`                                               |
| Input sanitization | Strip HTML, validate lengths, regex for email                                        |
| Password           | Cognito enforces policy (8+ chars, upper, lower, digit, special)                     |
| No auth required   | These are public endpoints — protection is rate limiting + honeypot + CSRF           |

## CORS Configuration

Add to `app.py` or a dedicated CORS config:

```python
from flask_cors import CORS

# Existing CORS setup — add the website origin
CORS(app, resources={
    r"/api/signup*": {
        "origins": ["https://myadmin.jabaki.nl"],
        "methods": ["POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-CSRF-Token"]
    }
})
```

## Dependencies

Add to `requirements.txt`:

```
flask-limiter>=3.5.0      # Rate limiting
```

Already available in the project:

- `boto3` — AWS Cognito, SES/SNS calls
- `flask-cors` — CORS handling
- `PyJWT` / `python-jose` — JWT if needed later

## File Structure

```
backend/src/
├── routes/
│   └── signup_routes.py          # Blueprint: signup_bp (all 3 endpoints)
├── services/
│   └── signup_service.py         # Business logic: Cognito calls, DB ops (uses myadmin_promo DB)
├── migrations/
│   └── 20260319_create_myadmin_promo_db.sql  # Database + table creation script
```

## Recommended Implementation Order

1. **Database first** — Run the `CREATE TABLE pending_signups` migration on Railway
2. **signup_routes.py** — Create blueprint with the 3 route stubs, register in `app.py`
3. **signup_service.py** — Implement Cognito integration (`sign_up`, `confirm_sign_up`, `resend_confirmation_code`)
4. **POST /api/signup** — Full implementation with validation, honeypot, Cognito create, DB insert, admin notification
5. **POST /api/signup/verify** — Cognito confirm + DB update + admin notification
6. **POST /api/signup/resend** — Cognito resend + rate check
7. **CORS** — Add website origin to allowed origins
8. **Rate limiting** — Add `flask-limiter` decorators to all 3 endpoints
9. **Test with website** — End-to-end flow from signup form to verification

## Phase 1: Manual Tenant Provisioning

After a signup is verified, admin receives email notification and manually provisions:

| Step | What                                            | Where                         |
| ---- | ----------------------------------------------- | ----------------------------- |
| 1    | Create Cognito user attributes (administration) | AWS Cognito console or script |
| 2    | Insert `tenant_config` row                      | Railway MySQL                 |
| 3    | Insert `tenant_credentials` row                 | Railway MySQL                 |
| 4    | Insert `tenant_modules` rows (FIN, STR)         | Railway MySQL                 |
| 5    | Insert `tenant_template_config` rows            | Railway MySQL                 |
| 6    | Import general ledger template                  | Chart of Accounts import      |
| 7    | Set purpose definitions                         | Year End Settings             |
| 8    | Upload example template files                   | Template management           |
| 9    | Send welcome email with user manual link        | Manual or SES                 |

## Phase 2: Automated Provisioning (Post-Launch)

1. Build tenant provisioning service/script that automates steps 1-9 above
2. Trigger automatically after email verification (background job or Cognito post-confirmation Lambda)
3. Build `pending_signups` → `tenants` promotion flow
4. Set trial plan with 2-month expiry
5. Send automated welcome/onboarding email

## API Contract Reference

Full request/response specs defined in the website repo:
`myAdminPromo/.kiro/specs/Website/wireframes/trial-signup.md`

## Future: Passkey Authentication

**Status:** Post-launch enhancement
**Reference implementation:** `C:\Users\peter\aws\h-dcn` (already implemented in h-dcn project)

Cognito supports passkeys (WebAuthn/FIDO2) natively since November 2024 via the choice-based auth flow.

**Key lesson from h-dcn:** Cognito creates separate user records (different `sub` IDs) when the same email is used with different auth methods (e.g. Google federated login vs passkey). After login, you must resolve which Cognito `sub` was used and map it back to a "prime ID" to retrieve the correct credentials and tenant context.

**What to port from h-dcn:**

- Post-login identity resolution logic (login `sub` → prime ID lookup)
- Credential/tenant mapping keyed on prime ID, not raw Cognito `sub`
- Google federated login + passkey coexistence handling

**Cognito gotcha:** If MFA is enabled at the pool level, it overrides passkeys — they can't coexist. Choose one or the other.

**Effort estimate:** ~2-3 days to port from h-dcn, plus testing.
