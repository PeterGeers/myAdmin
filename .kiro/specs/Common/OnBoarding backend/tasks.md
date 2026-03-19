# Tasks: Trial Signup API Backend

**Status:** Complete
**Spec:** [StartingPoints.md](./StartingPoints.md)

## Phase 1: Foundation (Day 1)

### 1.1 Database Setup

- [x] Create `myadmin_promo` database on Railway MySQL (via MySQL Workbench):
  ```sql
  CREATE DATABASE myadmin_promo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  ```
- [x] Create Docker init script `backend/docker-init/01_create_promo_db.sql`:
  ```sql
  CREATE DATABASE IF NOT EXISTS myadmin_promo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  GRANT ALL PRIVILEGES ON myadmin_promo.* TO 'peter'@'%';
  FLUSH PRIVILEGES;
  ```
- [x] Add init script volume mount to `docker-compose.yml` mysql service:
  ```yaml
  volumes:
    - ./mysql_data:/var/lib/mysql
    - ./backend/docker-init:/docker-entrypoint-initdb.d
  ```
- [x] For existing local container, run manually:
      `docker exec -i <mysql_container> mysql -u peter -p < backend/docker-init/01_create_promo_db.sql`
- [x] Create migration file `backend/src/migrations/20260319_create_myadmin_promo_db.sql` (CREATE DATABASE + CREATE TABLE)
- [x] Run `CREATE TABLE pending_signups` in `myadmin_promo` on both Railway and local Docker
- [x] Verify both environments: `USE myadmin_promo; DESCRIBE pending_signups;`

### 1.2 Dependencies

- [x] Add `flask-limiter>=3.5.0` to `backend/requirements.txt`
- [x] Install: `pip install flask-limiter`

### 1.3 Blueprint Scaffold

- [x] Create `backend/src/routes/signup_routes.py` with `signup_bp` blueprint
- [x] Three route stubs: `/api/signup`, `/api/signup/verify`, `/api/signup/resend` (all POST, return 501 for now)
- [x] Register blueprint in `backend/src/app.py`:
  ```python
  from routes.signup_routes import signup_bp
  app.register_blueprint(signup_bp)
  ```

### 1.4 Service Layer Scaffold

- [x] Create `backend/src/services/signup_service.py`
- [x] Stub methods: `create_signup()`, `verify_signup()`, `resend_verification()`
- [x] Add Cognito client initialization (boto3, region `eu-west-1`)
- [x] Add dedicated `DatabaseManager` instance for `myadmin_promo` DB:
  ```python
  promo_db = DatabaseManager(test_mode=test_mode, db_name=os.getenv('PROMO_DB_NAME', 'myadmin_promo'))
  ```

### 1.5 CORS Update

- [x] Add `https://myadmin.jabaki.nl` to CORS origins in `app.py` (line ~237)
- [x] Add `X-CSRF-Token` to `allow_headers`
- [x] Verify OPTIONS preflight works for `/api/signup`

## Phase 2: Core Implementation (Day 2-3)

### 2.1 Input Validation

- [x] Create validation helper in `signup_service.py`:
  - firstName: required, 1-50 chars, strip HTML
  - lastName: required, 1-50 chars, strip HTML
  - email: required, valid format (regex)
  - password: required, min 8 chars (Cognito enforces policy)
  - companyName: optional, max 100 chars
  - propertyRange: optional, one of `['1-5', '6-20', '21-50', '50+']`
  - referralSource: optional, max 50 chars
  - acceptedTerms: required, must be `true`
  - locale: required, one of `['nl', 'en']`
- [x] Honeypot check: reject if `honeypot` field is non-empty (return 200 silently to not tip off bots)
- [x] CSRF token validation

### 2.2 POST /api/signup — Full Implementation

- [x] Validate all input fields (call validation helper)
- [x] Call Cognito `sign_up`:
  ```python
  cognito_client.sign_up(
      ClientId=COGNITO_APP_CLIENT_ID,
      Username=email,
      Password=password,
      UserAttributes=[
          {'Name': 'email', 'Value': email},
          {'Name': 'given_name', 'Value': first_name},
          {'Name': 'family_name', 'Value': last_name}
      ]
  )
  ```
- [x] Insert into `pending_signups` table (promo_db DatabaseManager → myadmin_promo DB)
- [x] Send admin notification to peter@jabaki.nl via SNS (use existing `aws_notifications.py` pattern)
- [x] Return 201 with `userId` (Cognito `UserSub`)
- [x] Handle errors: `UsernameExistsException` → 409, validation → 422

### 2.3 POST /api/signup/verify — Full Implementation

- [x] Look up email in `pending_signups` (404 if not found, 410 if already verified)
- [x] Call Cognito `confirm_sign_up`:
  ```python
  cognito_client.confirm_sign_up(
      ClientId=COGNITO_APP_CLIENT_ID,
      Username=email,
      ConfirmationCode=code
  )
  ```
- [x] Update `pending_signups`: `status='verified'`, `verified_at=NOW()`
- [x] Send admin notification: "New verified signup ready for provisioning"
- [x] Return 200 with `redirectUrl`
- [x] Handle errors: `CodeMismatchException` → 400, `ExpiredCodeException` → 400

### 2.4 POST /api/signup/resend — Full Implementation

- [x] Look up email in `pending_signups` (404 if not found, 410 if already verified)
- [x] Rate limit check: `last_resend_at` < 60 seconds ago → 429
- [x] Call Cognito `resend_confirmation_code`:
  ```python
  cognito_client.resend_confirmation_code(
      ClientId=COGNITO_APP_CLIENT_ID,
      Username=email
  )
  ```
- [x] Update `pending_signups.last_resend_at = NOW()`
- [x] Return 200

## Phase 3: Security & Rate Limiting (Day 3)

### 3.1 Rate Limiting Setup

- [x] Initialize `flask-limiter` in `app.py`:
  ```python
  from flask_limiter import Limiter
  from flask_limiter.util import get_remote_address
  limiter = Limiter(get_remote_address, app=app, default_limits=[])
  ```
- [x] Export `limiter` or pass to signup blueprint
- [x] Add decorators to signup routes:
  - `/api/signup`: `@limiter.limit("5 per hour")`
  - `/api/signup/verify`: `@limiter.limit("10 per hour")`
  - `/api/signup/resend`: `@limiter.limit("1 per minute")` (also enforced in DB check)

### 3.2 CSRF Token Validation

- [x] Define CSRF approach: shared secret between website and backend (env var `CSRF_SECRET`)
- [x] Validate `X-CSRF-Token` header or `csrfToken` body field in signup routes
- [x] Add `CSRF_SECRET` to `.env.example`

### 3.3 Honeypot Field

- [x] Check `honeypot` field in `/api/signup` — if non-empty, return 200 with fake success (don't reveal detection)

## Phase 4: Environment & Config (Day 3-4)

### 4.1 Environment Variables

- [x] Add to `backend/.env.example`:
  ```
  # Signup API (same Cognito pool, separate app client)
  PROMO_DB_NAME=myadmin_promo
  SIGNUP_COGNITO_USER_POOL_ID=eu-west-1_XXXXXXX        # Same as existing pool
  SIGNUP_COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx  # New app client (no secret)
  SIGNUP_ADMIN_EMAIL=peter@jabaki.nl
  CSRF_SECRET=your-csrf-secret-here
  SIGNUP_REDIRECT_URL=https://app.myadmin.jabaki.nl/welcome
  ```
- [x] Add actual values to Railway environment variables
- [x] Add actual values to local `backend/.env`

### 4.2 Cognito App Client Setup

- [x] Create a new app client in the existing myAdmin Cognito user pool (eu-west-1)
  - Name: `myAdmin-signup` (or similar)
  - No client secret (public client for website signup)
  - Allowed auth flows: only what's needed for `sign_up`, `confirm_sign_up`, `resend_confirmation_code`
  - Do NOT enable `initiate_auth` — users log in via the main app client
- [x] Note the new app client ID → set as `SIGNUP_COGNITO_APP_CLIENT_ID` in env
- [x] `SIGNUP_COGNITO_USER_POOL_ID` is the same as the existing pool ID
- [ ] Verify email verification flow works with the new app client
- [ ] Customize verification email template if needed (Dutch + English based on locale)

## Phase 5: Testing (Day 4)

### 5.1 Manual Testing

- [x] Test `/api/signup` with valid payload (curl or Postman)
- [x] Test `/api/signup` with duplicate email → 409
- [x] Test `/api/signup` with invalid input → 422
- [x] Test `/api/signup` with honeypot filled → silent 200
- [x] Test `/api/signup/verify` with valid code
- [x] Test `/api/signup/verify` with invalid code → 400
- [x] Test `/api/signup/resend` → success
- [x] Test `/api/signup/resend` within 60s → 429
- [x] Test rate limiting: 6th signup in 1 hour → 429
- [x] Test CORS: request from `https://myadmin.jabaki.nl` → allowed
- [x] Test CORS: request from other origin → blocked

### 5.2 Postman Collection

- [x] Create Postman collection "myAdmin Signup API" with all 3 endpoints
- [x] Add test scripts for response validation
- [x] Add environment variables for base URL, test email

### 5.3 Integration Test with Website

- [x] Deploy to Railway
- [ ] Test full flow from website signup form → verification email → verify click → redirect

## Phase 6: Unit & Integration Tests (Day 5)

### 6.1 Test Fixtures

- [x] Create `backend/tests/api/test_signup_routes.py`
- [x] Add pytest fixtures: mock Cognito client, mock DatabaseManager, test app client
- [x] Add `@pytest.mark.api` markers to all signup tests

### 6.2 POST /api/signup Tests

- [x] Test valid signup → 201, userId returned
- [x] Test missing required fields (firstName, lastName, email, password, acceptedTerms) → 422
- [x] Test invalid email format → 422
- [x] Test acceptedTerms=false → 422
- [x] Test duplicate email (mock `UsernameExistsException`) → 409
- [x] Test honeypot filled → 200 (silent fake success)
- [x] Test invalid CSRF token → 403
- [x] Test propertyRange with invalid value → 422
- [x] Test field length limits (firstName > 50 chars, companyName > 100 chars) → 422

### 6.3 POST /api/signup/verify Tests

- [x] Test valid verification → 200, redirectUrl returned
- [x] Test email not found in pending_signups → 404
- [x] Test already verified signup → 410
- [x] Test invalid code (mock `CodeMismatchException`) → 400
- [x] Test expired code (mock `ExpiredCodeException`) → 400

### 6.4 POST /api/signup/resend Tests

- [x] Test valid resend → 200
- [x] Test email not found → 404
- [x] Test already verified → 410
- [x] Test resend within 60 seconds → 429

### 6.5 Service Layer Tests

- [x] Create `backend/tests/unit/test_signup_service.py`
- [x] Add `@pytest.mark.unit` markers
- [x] Test `create_signup()` calls Cognito and inserts DB row
- [x] Test `verify_signup()` calls Cognito confirm and updates DB status
- [x] Test `resend_verification()` rate limit logic (last_resend_at check)
- [x] Test input validation helper: valid input passes, invalid input raises

### 6.6 Run Tests & Verify

- [x] Run `pytest tests/api/test_signup_routes.py -v` — all pass
- [x] Run `pytest tests/unit/test_signup_service.py -v` — all pass
- [x] Run `pytest tests/ --cov=src/routes/signup_routes --cov=src/services/signup_service` — check coverage

### 6.7 Git Commit

- [x] `git add -A && git commit -m "feat: signup API with tests (Phase 1-6)"`
- [x] `git push`

## Phase 7: Admin Notification & Provisioning Script (Day 6)

### 7.1 Admin Notification Email

- [x] Format notification email with signup details (name, email, company, property range)
- [x] Send on new signup (Phase 1 — informational)
- [x] Send on verification (Phase 1 — action required: provision tenant)

### 7.2 Manual Provisioning Script (Phase 1)

- [x] Create `backend/scripts/provision_tenant.py`:
  - Accept email as input
  - Look up `pending_signups` row (myadmin_promo DB)
  - Insert `tenant_config` row (finance DB)
  - Insert `tenant_credentials` row (finance DB)
  - Insert `tenant_modules` rows — FIN, STR based on property range (finance DB)
  - Insert `tenant_template_config` rows (finance DB)
  - Import default general ledger template (finance DB)
  - Set default purpose definitions (finance DB)
  - Update Cognito user attributes (add administration)
  - Update `pending_signups.status = 'provisioned'`, `provisioned_at = NOW()` (myadmin_promo DB)
  - Send welcome email to user
- [x] Test script on Railway with a test signup

## Git Commit Strategy

| When          | Commit Message                                              | What's Included                                                         |
| ------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| After Phase 1 | `feat(signup): scaffold blueprint, service, migration`      | Routes stub, service stub, migration SQL, CORS update, requirements.txt |
| After Phase 3 | `feat(signup): core endpoints with security`                | Full signup/verify/resend implementation, rate limiting, CSRF, honeypot |
| After Phase 6 | `test(signup): unit and API tests for signup flow`          | All test files, coverage verified                                       |
| After Phase 7 | `feat(signup): admin notifications and provisioning script` | Notification emails, provision_tenant.py                                |

## Dependencies Between Tasks

```
1.1 (DB migration)
1.2 (deps)
1.3 (blueprint) ──────> 2.2, 2.3, 2.4
1.4 (service) ────────> 2.1, 2.2, 2.3, 2.4
1.5 (CORS) ───────────> 5.3
2.1 (validation) ─────> 2.2
2.2 (signup) ─────────> 5.1, 6.2
2.3 (verify) ─────────> 5.1, 6.3
2.4 (resend) ─────────> 5.1, 6.4
3.1 (rate limit) ─────> 5.1
3.2 (CSRF) ───────────> 5.1
4.1 (env vars) ───────> 2.2, 2.3, 2.4
4.2 (Cognito) ────────> 2.2, 2.3, 2.4
5.1 (manual test) ────> 5.3
5.3 (integration) ────> 7.1
6.1-6.6 (tests) ──────> 6.7 (commit & push)
7.1 (notification) ───> 7.2
```

## Estimated Timeline

| Phase                             | Effort      | Depends On                |
| --------------------------------- | ----------- | ------------------------- |
| Phase 1: Foundation               | 0.5 day     | Nothing                   |
| Phase 2: Core Implementation      | 1.5 days    | Phase 1                   |
| Phase 3: Security                 | 0.5 day     | Phase 2                   |
| Phase 4: Environment              | 0.5 day     | Can parallel with Phase 2 |
| Phase 5: Manual Testing           | 0.5 day     | Phase 2-4                 |
| Phase 6: Unit & Integration Tests | 1 day       | Phase 2-4                 |
| Phase 7: Provisioning             | 1 day       | Phase 5-6                 |
| **Total**                         | **~6 days** |                           |
