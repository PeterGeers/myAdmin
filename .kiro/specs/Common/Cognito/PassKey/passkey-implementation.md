# Passkey (WebAuthn/FIDO2) Implementation for myAdmin

**Status:** Planned (post-launch enhancement)
**Priority:** Medium
**Effort:** ~3-4 days
**Reference implementation:** `C:\Users\peter\aws\h-dcn`
**Date:** March 19, 2026

## Summary

Add passkey authentication to myAdmin so users can sign in with Face ID, Touch ID, Windows Hello, or device PIN instead of (or alongside) email/password.

## Current Authentication Setup

### What exists today

- Cognito user pool `myAdmin` in eu-west-1
- Login via `signInWithRedirect()` → Cognito Hosted UI → OAuth code flow
- JWT tokens with `cognito:groups` for RBAC
- `@cognito_required` decorator on Flask routes
- Amplify v6 on frontend (`fetchAuthSession`, `getCurrentUser`)
- MFA: OPTIONAL with software TOTP enabled

### Terraform config (cognito.tf)

- `mfa_configuration = "OPTIONAL"` with `software_token_mfa_configuration` enabled
- App client: `allowed_oauth_flows = ["code"]`, `generate_secret = false`
- Auth flow: Hosted UI redirect (not custom UI auth)

## The MFA vs Passkey Problem

**Critical constraint:** Cognito does not support conditional MFA per auth method. When `mfa_configuration` is `OPTIONAL` or `ON` at the pool level, it applies to all auth flows including `USER_AUTH` — which blocks passkeys from working. There is no native "if login method = passkey, skip MFA" setting.

**Options considered:**

1. **Disable MFA, enable passkeys** — Passkeys are inherently multi-factor (device possession + biometric), so this is arguably more secure than TOTP MFA
2. **Keep MFA, skip passkeys** — If TOTP MFA is a hard requirement
3. **Conditional MFA (passkey = skip, password = require TOTP)** — Not supported by Cognito natively. Would require complex custom Lambda triggers with limited control over the WebAuthn flow.

**Decision: Option 1 — Disable MFA (`mfa_configuration = "OFF"`), enable passkeys**

- Passkeys are inherently multi-factor (device possession + biometric/PIN) — stronger than password + TOTP
- Same approach used in h-dcn and recommended by AWS for choice-based auth
- Users who want stronger security register a passkey; password-only remains as fallback
- No known myAdmin users currently rely on TOTP MFA, so no migration impact

## The Identity Linking Problem (Solved in h-dcn)

**Problem:** When the same email is used with different auth methods (e.g., Google federated login + passkey), Cognito creates separate user records with different `sub` IDs. This means:

- User signs up with email/password → `sub: aaa-111`
- Same user registers a passkey → `sub: aaa-111` (same, passkey is linked to existing user)
- Same user signs in via Google → `sub: bbb-222` (different, federated identity)

After login, the backend receives a JWT with one `sub` but the tenant config, roles, and data are associated with the "prime" identity.

**Solution from h-dcn:**

- After login, resolve the Cognito `sub` to a prime ID
- Store a mapping table: `identity_links(cognito_sub, prime_sub, auth_method, email)`
- All tenant/credential lookups use the prime `sub`, not the login `sub`
- On first federated login, auto-link if email matches an existing user

**For myAdmin Phase 1:** No Google login planned, so identity linking is not needed yet. Passkeys are linked to the existing Cognito user (same `sub`). Identity linking becomes relevant only if/when Google or other social logins are added.

## Architecture

### Auth Flow with Passkeys

```
User clicks "Sign in with passkey"
    ↓
Frontend calls Cognito InitiateAuth (USER_AUTH flow)
    ↓
Cognito returns WebAuthn challenge
    ↓
Browser calls navigator.credentials.get() → biometric prompt
    ↓
Frontend sends signed challenge back to Cognito (RespondToAuthChallenge)
    ↓
Cognito validates → returns JWT tokens (same format as password login)
    ↓
Frontend stores tokens → same flow as today
    ↓
Backend validates JWT → @cognito_required works unchanged
```

### Passkey Registration Flow

```
User goes to Profile/Settings → "Register passkey"
    ↓
Frontend calls Cognito StartWebAuthnRegistration
    ↓
Cognito returns credential creation options
    ↓
Browser calls navigator.credentials.create() → biometric prompt
    ↓
Frontend sends attestation to Cognito (CompleteWebAuthnRegistration)
    ↓
Passkey stored in Cognito, linked to user's sub
```

## What Changes

### Infrastructure (Terraform)

| File                        | Change                                                                                                    |
| --------------------------- | --------------------------------------------------------------------------------------------------------- |
| `infrastructure/cognito.tf` | Change `mfa_configuration` from `"OPTIONAL"` to `"OFF"` (or keep and accept passkeys won't work with MFA) |
| `infrastructure/cognito.tf` | Add `user_pool_add_ons.advanced_security_mode = "ENFORCED"` (required for choice-based auth)              |
| `infrastructure/cognito.tf` | Update app client: add `ALLOW_USER_AUTH` to explicit auth flows                                           |

### Backend (minimal changes)

| File                                 | Change                                                                                                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/src/auth/cognito_utils.py`  | **No changes needed** — JWT tokens from passkey auth have the same structure (`cognito:groups`, `sub`, `email`). The `@cognito_required` decorator works unchanged. |
| `backend/src/auth/tenant_context.py` | **No changes needed** — tenant resolution uses email/groups from JWT, not auth method                                                                               |

### Frontend (main effort)

| File                                               | Change                                                                                          |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `frontend/src/pages/Login.tsx`                     | Add "Sign in with passkey" button alongside Hosted UI redirect                                  |
| `frontend/src/services/authService.ts`             | Add `signInWithPasskey()`, `registerPasskey()`, `listPasskeys()` functions                      |
| `frontend/src/pages/Login.tsx`                     | Switch from `signInWithRedirect()` to custom auth UI (Amplify `signIn()` with `USER_AUTH` flow) |
| New: `frontend/src/components/PasskeySettings.tsx` | Passkey registration/management in user profile                                                 |
| `frontend/src/aws-exports.ts`                      | May need auth flow config updates                                                               |

### Key insight: Login page changes from redirect to custom UI

Currently the login page just calls `signInWithRedirect()` which sends the user to Cognito's Hosted UI. For passkeys, you need a custom login UI that:

1. Offers "Sign in with passkey" (calls `signIn()` with `authFlowType: 'USER_AUTH'`)
2. Offers "Sign in with email/password" (calls `signIn()` with username/password)
3. Handles the WebAuthn challenge/response in the browser

This is the biggest frontend change — moving from Hosted UI to custom auth UI.

## Tasks

### Phase 1: Infrastructure (0.5 day)

- [ ] 1.1 Decide on MFA strategy: disable MFA or accept passkeys won't coexist
- [ ] 1.2 Update `cognito.tf`: change `mfa_configuration` if needed
- [ ] 1.3 Update `cognito.tf`: enable `ALLOW_USER_AUTH` flow on app client
- [ ] 1.4 Run `terraform plan` to review changes
- [ ] 1.5 Run `terraform apply` to deploy
- [ ] 1.6 Verify user pool settings in AWS Console

### Phase 2: Frontend — Custom Login UI (1.5 days)

- [ ] 2.1 Update `authService.ts`: add `signInWithPasskey()` using Amplify `signIn({ authFlowType: 'USER_AUTH' })`
- [ ] 2.2 Update `authService.ts`: add WebAuthn challenge handler (`navigator.credentials.get()`)
- [ ] 2.3 Update `authService.ts`: add `respondToAuthChallenge()` for WebAuthn response
- [ ] 2.4 Rewrite `Login.tsx`: replace `signInWithRedirect()` with custom login form
  - Email/password fields
  - "Sign in with passkey" button
  - Conditional: show passkey option only if browser supports WebAuthn (`window.PublicKeyCredential`)
- [ ] 2.5 Handle auth challenge flow: `InitiateAuth` → challenge → `RespondToAuthChallenge` → tokens
- [ ] 2.6 Ensure `Callback.tsx` still works for any remaining OAuth flows
- [ ] 2.7 Test login with email/password (regression — must still work)

### Phase 3: Frontend — Passkey Registration (0.5 day)

- [ ] 3.1 Create `PasskeySettings.tsx` component
  - List registered passkeys (name, created date)
  - "Register new passkey" button
  - "Remove passkey" button
- [ ] 3.2 Add `registerPasskey()` to `authService.ts`:
  - Call Cognito `StartWebAuthnRegistration`
  - Call `navigator.credentials.create()` with returned options
  - Call Cognito `CompleteWebAuthnRegistration` with attestation
- [ ] 3.3 Add `listPasskeys()` and `deletePasskey()` to `authService.ts`
- [ ] 3.4 Add PasskeySettings to user profile/settings page
- [ ] 3.5 Show "Register a passkey for faster login" prompt after successful password login

### Phase 4: Identity Linking (only if Google login is added) (1 day)

- [ ] 4.1 Create `identity_links` table in database:
  ```sql
  CREATE TABLE identity_links (
      id INT AUTO_INCREMENT PRIMARY KEY,
      cognito_sub VARCHAR(128) NOT NULL,
      prime_sub VARCHAR(128) NOT NULL,
      auth_method ENUM('password', 'passkey', 'google') NOT NULL,
      email VARCHAR(255) NOT NULL,
      linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uk_sub (cognito_sub),
      INDEX idx_prime (prime_sub),
      INDEX idx_email (email)
  );
  ```
- [ ] 4.2 Port prime ID resolution logic from h-dcn
- [ ] 4.3 Add post-login identity resolution middleware
- [ ] 4.4 Update `cognito_utils.py`: after JWT decode, resolve `sub` to prime ID
- [ ] 4.5 Update tenant context to use prime ID for lookups
- [ ] 4.6 Auto-link on first federated login if email matches existing user

### Phase 5: Testing (0.5 day)

- [ ] 5.1 Test passkey registration on Chrome (Windows Hello)
- [ ] 5.2 Test passkey registration on Safari (Touch ID / Face ID)
- [ ] 5.3 Test passkey login on Chrome
- [ ] 5.4 Test passkey login on Safari
- [ ] 5.5 Test password login still works (regression)
- [ ] 5.6 Test passkey on mobile (iOS Safari, Android Chrome)
- [ ] 5.7 Test browser without WebAuthn support → graceful fallback to password
- [ ] 5.8 Test removing a passkey and re-registering
- [ ] 5.9 Verify JWT tokens from passkey auth contain correct `cognito:groups` and tenant attributes

### Phase 6: Git & Deploy

- [ ] 6.1 `git commit -m "feat: add passkey (WebAuthn) authentication support"`
- [ ] 6.2 `git push`
- [ ] 6.3 Deploy to Railway
- [ ] 6.4 Run `terraform apply` on production (if not already done)
- [ ] 6.5 Test passkey flow in production

## Dependencies

```
1.1-1.2 (MFA decision) ──> 1.3-1.6 (Terraform)
1.3-1.6 (Terraform) ──────> 2.1-2.7 (Custom login UI)
2.1-2.7 (Login UI) ───────> 3.1-3.5 (Passkey registration)
3.1-3.5 (Registration) ───> 5.1-5.9 (Testing)
4.1-4.6 (Identity linking) → only if Google login added
5.1-5.9 (Testing) ────────> 6.1-6.5 (Deploy)
```

## Estimated Timeline

| Phase                         | Effort        | Notes                                            |
| ----------------------------- | ------------- | ------------------------------------------------ |
| Phase 1: Infrastructure       | 0.5 day       | Terraform changes, MFA decision                  |
| Phase 2: Custom Login UI      | 1.5 days      | Biggest change — moving from Hosted UI to custom |
| Phase 3: Passkey Registration | 0.5 day       | Settings component + Cognito API calls           |
| Phase 4: Identity Linking     | 1 day         | Only needed if Google login is added later       |
| Phase 5: Testing              | 0.5 day       | Cross-browser, cross-device                      |
| Phase 6: Deploy               | 0.5 day       | Railway + Terraform                              |
| **Total (without Phase 4)**   | **~3.5 days** |                                                  |
| **Total (with Phase 4)**      | **~4.5 days** |                                                  |

## Reference: h-dcn Implementation

**Location:** `C:\Users\peter\aws\h-dcn`

Key files to reference when implementing:

- Identity linking / prime ID resolution logic
- WebAuthn challenge/response handling
- Post-login identity resolution middleware
- Google federated login + passkey coexistence

## Risks

- **MFA removal:** If MFA is disabled to enable passkeys, users currently using TOTP will lose that option. Communicate this change.
- **Browser support:** WebAuthn is supported in all modern browsers but not in older ones. Always provide password fallback.
- **Hosted UI → Custom UI:** Moving away from Cognito Hosted UI means maintaining the login UI yourself. More control but more maintenance.
- **Cognito limitations:** Passkey support is relatively new in Cognito (Nov 2024). Edge cases may exist.
