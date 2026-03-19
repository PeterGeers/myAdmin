# Tasks: Passkey Authentication — Refactor Cognito Login

**Status:** Not Started
**Spec:** [passkey-implementation.md](./passkey-implementation.md)
**Effort:** ~3.5 days (without identity linking) / ~4.5 days (with)
**Prerequisites:** Current Cognito auth working (Hosted UI + `@cognito_required`)

## Phase 1: MFA Decision & Infrastructure (0.5 day)

### 1.1 MFA Strategy Decision

- [x] Decide: disable MFA or keep MFA and accept passkeys won't coexist

**Decision: Disable MFA (`mfa_configuration = "OFF"`)**

Cognito does not support conditional MFA (e.g. "skip MFA if passkey, require MFA if password"). When MFA is `OPTIONAL` or `ON` at the pool level, it applies to all auth flows including `USER_AUTH` — which blocks passkeys from working. There is no native "if login method = passkey, skip MFA" setting.

Rationale:

- Passkeys are inherently multi-factor (device possession + biometric/PIN) — stronger than password + TOTP
- This is the same approach used in h-dcn and recommended by AWS for choice-based auth
- Users who want stronger security register a passkey; password-only remains as fallback
- No known myAdmin users currently rely on TOTP MFA, so no migration impact

- [x] If disabling MFA: notify any users currently using TOTP that it will be removed → N/A, no active TOTP users
- [x] Document decision in this file → documented above

### 1.2 Terraform — Update Cognito User Pool

- [x] Update `infrastructure/cognito.tf` — change `mfa_configuration`:

  ```hcl
  # Disable MFA to enable passkeys (Decision 1.1)
  mfa_configuration = "OFF"
  # Remove software_token_mfa_configuration block
  ```

- [x] Update `infrastructure/cognito.tf` — set advanced security to ENFORCED (required for choice-based auth):
  ```hcl
  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }
  ```

### 1.3 Terraform — Update App Client for USER_AUTH Flow

- [x] Update `infrastructure/cognito.tf` — add explicit auth flows to app client:
  ```hcl
  resource "aws_cognito_user_pool_client" "myadmin_client" {
    # ... existing config ...
    explicit_auth_flows = [
      "ALLOW_USER_AUTH",           # Choice-based (passkey + password)
      "ALLOW_USER_SRP_AUTH",       # Password with SRP (existing)
      "ALLOW_REFRESH_TOKEN_AUTH"   # Token refresh
    ]
  }
  ```

### 1.4 Terraform — Deploy

- [x] Run `terraform plan` — review changes, confirm no destructive operations
- [x] Run `terraform apply` — deploy to Cognito
- [x] Verify in AWS Console: user pool shows "Choice-based sign-in" enabled
- [x] Verify app client shows `ALLOW_USER_AUTH` in auth flows

### 1.5 Git Commit

- [x] `git add infrastructure/cognito.tf`
- [x] `git commit -m "infra: enable choice-based auth (USER_AUTH) for passkey support"`
- [x] `git push`

## Phase 2: Frontend — Custom Login UI (1.5 days)

The current `Login.tsx` uses `signInWithRedirect()` (Cognito Hosted UI). This needs to become a custom login form that supports both password and passkey authentication.

### 2.1 Update authService.ts — Add Passkey Auth Functions

- [x] Add `signInWithPasskey(email: string)` function:

  ```typescript
  import { signIn, confirmSignIn } from "aws-amplify/auth";

  export async function signInWithPasskey(email: string) {
    // Step 1: Initiate auth with USER_AUTH flow (preferring passkey)
    const result = await signIn({
      username: email,
      options: { authFlowType: "USER_AUTH" },
    });
    // Step 2: Handle WEB_AUTHN challenge
    // result.nextStep.signInStep === 'CONTINUE_SIGN_IN_WITH_FIRST_FACTOR_SELECTION'
    // Select WEB_AUTHN, then handle navigator.credentials.get()
    return result;
  }
  ```

- [x] Add `signInWithPassword(email: string, password: string)` function:
  ```typescript
  export async function signInWithPassword(email: string, password: string) {
    const result = await signIn({
      username: email,
      password: password,
      options: { authFlowType: "USER_SRP_AUTH" },
    });
    return result;
  }
  ```
- [x] Add `handleWebAuthnChallenge(challengeResponse)` — wrapper around `confirmSignIn` for WebAuthn
- [x] Add `isPasskeySupported()` — check `window.PublicKeyCredential` availability
- [x] Verify existing `getCurrentAuthTokens()`, `getCurrentUserRoles()` still work (JWT format is identical regardless of auth method)

### 2.2 Rewrite Login.tsx — Custom Auth Form

- [x] Replace single `signInWithRedirect()` button with custom login form:
  - Email input field
  - Password input field
  - "Sign In" button (email/password)
  - Divider with "or"
  - "Sign in with Passkey" button (only shown if `isPasskeySupported()`)
  - Forgot password link (keep existing `handleForgotPassword`)
- [x] Keep the JaBaKi logo, dark theme, orange accent styling
- [x] Keep the i18n translations (add new keys for passkey button text)
- [x] Handle loading states for both auth methods
- [x] Error handling: show toast for invalid credentials, passkey failures, etc.

### 2.3 Login.tsx — Password Sign-In Flow

- [x] On "Sign In" click: call `signInWithPassword(email, password)`
- [x] Handle success: `signInResult.isSignedIn === true` → call `onLoginSuccess()` or navigate to dashboard
- [x] Handle MFA challenge (if MFA is kept): show TOTP input
- [x] Handle `NotAuthorizedException` → "Incorrect email or password" toast
- [x] Handle `UserNotFoundException` → same generic error (don't reveal user existence)

### 2.4 Login.tsx — Passkey Sign-In Flow

- [x] On "Sign in with Passkey" click: prompt for email first (or use last-used email from localStorage)
- [x] Call `signInWithPasskey(email)`
- [x] Amplify v6 handles the WebAuthn challenge internally via `confirmSignIn`:
  - Browser shows biometric prompt (Face ID / Touch ID / Windows Hello)
  - User authenticates
  - Amplify completes the challenge and returns tokens
- [x] Handle success: same as password flow → navigate to dashboard
- [x] Handle `NotAuthorizedException` → "No passkey registered for this account"
- [x] Handle user cancellation of biometric prompt → "Passkey authentication cancelled"

### 2.5 Update aws-exports.ts (if needed)

- [x] Verify Amplify config works with custom `signIn()` calls (not just `signInWithRedirect`)
- [x] The OAuth config may still be needed for `signOut()` redirect — keep it

### 2.6 Update Callback.tsx

- [x] Verify `Callback.tsx` still works for any remaining OAuth redirect flows
- [x] Custom `signIn()` doesn't use redirects, so Callback may become unused — keep for backward compatibility

### 2.7 Update AuthContext.tsx

- [x] `checkAuthState()` should work unchanged — it calls `getCurrentUser()` and `fetchAuthSession()` which work regardless of auth method
- [x] Verify `logout()` still works — `signOut()` should clear tokens from both auth methods

### 2.8 Add i18n Translation Keys

- [x] Add to `frontend/src/locales/en/auth.json`:
  ```json
  "login.emailLabel": "Email",
  "login.passwordLabel": "Password",
  "login.signInWithPassword": "Sign In",
  "login.signInWithPasskey": "Sign in with Passkey",
  "login.passkeyNotSupported": "Passkeys are not supported in this browser",
  "login.passkeyFailed": "Passkey authentication failed",
  "login.passkeyCancelled": "Passkey authentication was cancelled",
  "login.noPasskeyRegistered": "No passkey registered for this account",
  "login.or": "or"
  ```
- [x] Add Dutch translations to `frontend/src/locales/nl/auth.json`

### 2.9 Regression Testing

- [x] Test password login still works end-to-end
- [x] Test logout still works
- [x] Test token refresh still works
- [x] Test `@cognito_required` backend decorator still validates tokens from custom login
- [x] Test AuthContext still populates user/roles/tenants correctly

### 2.10 Git Commit

- [x] `git add frontend/src/pages/Login.tsx frontend/src/services/authService.ts frontend/src/aws-exports.ts frontend/src/locales/`
- [x] `git commit -m "feat: custom login UI with password and passkey support"`
- [x] `git push`

## Phase 3: Frontend — Passkey Registration (0.5 day)

Users need a way to register passkeys from their profile/settings.

### 3.1 Add Passkey Registration Functions to authService.ts

- [x] Add `registerPasskey()`:

  ```typescript
  import { associateWebAuthnCredential } from "aws-amplify/auth";

  export async function registerPasskey() {
    // Amplify v6 handles the full WebAuthn registration flow:
    // 1. Gets credential creation options from Cognito
    // 2. Calls navigator.credentials.create()
    // 3. Sends attestation back to Cognito
    await associateWebAuthnCredential();
  }
  ```

- [x] Add `listPasskeys()`:

  ```typescript
  import { listWebAuthnCredentials } from "aws-amplify/auth";

  export async function listPasskeys() {
    const result = await listWebAuthnCredentials();
    return result.credentials;
  }
  ```

- [x] Add `deletePasskey(credentialId: string)`:

  ```typescript
  import { deleteWebAuthnCredential } from "aws-amplify/auth";

  export async function deletePasskey(credentialId: string) {
    await deleteWebAuthnCredential({ credentialId });
  }
  ```

### 3.2 Create PasskeySettings.tsx Component

- [x] Create `frontend/src/components/settings/PasskeySettings.tsx`
- [x] List registered passkeys (friendly name, created date, last used)
- [x] "Register new passkey" button → calls `registerPasskey()` → browser biometric prompt
- [x] "Remove" button per passkey → calls `deletePasskey(id)` with confirmation dialog
- [x] Show "Your browser doesn't support passkeys" if `!isPasskeySupported()`
- [x] Success/error toasts for registration and deletion
- [x] Dark theme styling consistent with rest of app (gray.800 bg, orange accents)

### 3.3 Add PasskeySettings to User Profile/Settings

- [x] Find or create a user settings/profile page
- [x] Add PasskeySettings component as a section
- [x] Only show if user is authenticated

### 3.4 Post-Login Passkey Prompt

- [x] After successful password login, check if user has any passkeys registered
- [x] If no passkeys and browser supports WebAuthn: show a dismissible banner/toast:
      "Register a passkey for faster, more secure login"
- [x] Store dismissal in localStorage so it doesn't show every time
- [x] Link to PasskeySettings page

### 3.5 Git Commit

- [x] `git add frontend/src/components/settings/PasskeySettings.tsx frontend/src/services/authService.ts`
- [x] `git commit -m "feat: passkey registration and management in user settings"`
- [x] `git push`

## Phase 4: Testing (0.5 day)

### 4.1 Password Login Regression

- [x] Test email/password login → success → dashboard loads with correct user/roles/tenants
- [x] Test wrong password → error toast, no crash
Sign in with your email and password, or use a passkey for faster, more secure access.
Protected by AWS Cognito
Login Failed
Incorrect email or password. Please try again.
- [x] Test non-existent email → generic error (no user enumeration)
This gives an error.  Login Failed  Incorrect email or password. Please try again.  
- [x] Test forgot password flow still works
Mail received with reset ciode and password reset worked

### 4.2 Passkey Registration

- [x] Test register passkey on Chrome (Windows Hello) → success
- [x] Test register passkey on Safari (Touch ID) → success
- [x] Test register passkey on Firefox → success or graceful unsupported message
- [x] Test list passkeys → shows registered passkey
- [x] Test delete passkey → removed from list

### 4.3 Passkey Login

- [x] Test passkey login on Chrome → biometric prompt → success → dashboard
- [x] Test passkey login on Safari → biometric prompt → success → dashboard
- [x] Test passkey login with cancelled biometric → error message, can retry
- [x] Test passkey login for user without passkey → appropriate error
- [x] Test passkey login on mobile (iOS Safari, Android Chrome) if possible

### 4.4 Cross-Auth Verification

- [x] Login with password → JWT contains correct `cognito:groups` and `custom:tenants`
- [x] Login with passkey → JWT contains correct `cognito:groups` and `custom:tenants`
- [x] Backend `@cognito_required` accepts tokens from both auth methods
- [x] Tenant context resolves correctly regardless of auth method

### 4.5 Edge Cases

- [x] Browser without WebAuthn support → passkey button hidden, password login works
- [x] User registers passkey, then admin disables their account → passkey login fails gracefully
- [x] Token expiry → refresh works for both auth methods
- [x] Multiple passkeys registered → any of them works for login

### 4.6 Update Existing Auth Tests

- [ ] Update `frontend/src/__tests__/authentication.integration.test.tsx` — add passkey login test cases
- [ ] Update `frontend/src/context/AuthContext.test.tsx` — verify context works with custom signIn
- [ ] Run full test suite: `npm test` — all pass

## Phase 5: Deploy & Production Testing (0.5 day)

### 5.1 Pre-Deploy Checklist

- [x] All tests passing locally
- [x] Password login works locally
- [x] Passkey registration + login works locally
- [x] No console errors

### 5.2 Deploy

- [x] `git add -A && git commit -m "feat: passkey authentication support"` (if not already committed per phase)
- [x] `git push`
- [x] Verify Railway auto-deploys (or trigger manual deploy)
- [x] Verify Terraform changes already applied (Phase 1.4)

### 5.3 Production Testing

- [x] Test password login in production
- [x] Register a passkey in production
- [x] Test passkey login in production
- [x] Test on mobile device in production
- [x] Verify all existing functionality still works (FIN module, STR module, reports, etc.)

## Phase 6: Identity Linking (ONLY if Google/social login is added later)

> Skip this phase for now. Only implement when adding Google or other federated login providers.

### 6.1 Database — Create identity_links Table

- [ ] Create migration: `backend/src/migrations/20260320_create_identity_links.sql`
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
- [ ] Run migration on Railway and local Docker

### 6.2 Backend — Prime ID Resolution

- [ ] Port prime ID resolution logic from h-dcn (`C:\Users\peter\aws\h-dcn`)
- [ ] Add post-login middleware in `cognito_utils.py`:
  - After JWT decode, look up `sub` in `identity_links`
  - If found, replace with `prime_sub` for all downstream lookups
  - If not found and auth method is federated, auto-link by email match
- [ ] Update `tenant_context.py` to use resolved prime ID

### 6.3 Frontend — Link Accounts UI

- [ ] Show linked identities in user settings
- [ ] "Link Google account" button
- [ ] Auto-link prompt on first federated login if email matches

### 6.4 Testing

- [ ] Test Google login creates separate sub
- [ ] Test prime ID resolution maps to correct tenant
- [ ] Test auto-linking by email
- [ ] Test unlinking an identity

## Dependencies

```
Phase 1 (Terraform) ──────> Phase 2 (Custom Login UI)
Phase 2 (Login UI) ───────> Phase 3 (Passkey Registration)
Phase 2 (Login UI) ───────> Phase 4 (Testing)
Phase 3 (Registration) ───> Phase 4 (Testing)
Phase 4 (Testing) ────────> Phase 5 (Deploy)
Phase 6 (Identity Linking) → only when Google login is added
```

## Git Commit Strategy

| When          | Commit Message                                                    |
| ------------- | ----------------------------------------------------------------- |
| After Phase 1 | `infra: enable choice-based auth (USER_AUTH) for passkey support` |
| After Phase 2 | `feat: custom login UI with password and passkey support`         |
| After Phase 3 | `feat: passkey registration and management in user settings`      |
| After Phase 4 | `test: update auth tests for passkey support`                     |
| After Phase 5 | Final deploy verification (no commit needed)                      |

## Estimated Timeline

| Phase                              | Effort        | Depends On              |
| ---------------------------------- | ------------- | ----------------------- |
| Phase 1: Infrastructure            | 0.5 day       | Nothing                 |
| Phase 2: Custom Login UI           | 1.5 days      | Phase 1                 |
| Phase 3: Passkey Registration      | 0.5 day       | Phase 2                 |
| Phase 4: Testing                   | 0.5 day       | Phase 2-3               |
| Phase 5: Deploy                    | 0.5 day       | Phase 4                 |
| **Total**                          | **~3.5 days** |                         |
| Phase 6: Identity Linking (future) | +1 day        | When Google login added |

## Key Files Changed

| File                                                         | Change                                                      |
| ------------------------------------------------------------ | ----------------------------------------------------------- |
| `infrastructure/cognito.tf`                                  | MFA config, USER_AUTH flow, advanced security               |
| `frontend/src/pages/Login.tsx`                               | Full rewrite: custom form with password + passkey           |
| `frontend/src/services/authService.ts`                       | Add passkey auth, registration, listing, deletion functions |
| `frontend/src/aws-exports.ts`                                | Possibly minor config updates                               |
| `frontend/src/context/AuthContext.tsx`                       | Verify unchanged (should work as-is)                        |
| `frontend/src/pages/Callback.tsx`                            | Verify still works (may become unused)                      |
| New: `frontend/src/components/settings/PasskeySettings.tsx`  | Passkey management UI                                       |
| `frontend/src/locales/en/auth.json`                          | New translation keys                                        |
| `frontend/src/locales/nl/auth.json`                          | New Dutch translation keys                                  |
| `frontend/src/__tests__/authentication.integration.test.tsx` | Updated test cases                                          |

## Reference

- **h-dcn implementation:** `C:\Users\peter\aws\h-dcn` — identity linking, prime ID resolution
- **h-dcn best practices doc:** [h-dcn_cognito_request.md](./h-dcn_cognito_request.md) — detailed patterns for prime ID resolution, WebAuthn flows, enhanced groups middleware, custom JWT generation
- **AWS docs:** [Cognito WebAuthn/Passkey authentication](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html)
- **Amplify v6 passkey API:** `associateWebAuthnCredential`, `listWebAuthnCredentials`, `deleteWebAuthnCredential`
- **AWS blog:** [Passwordless auth with Cognito and WebAuthn](https://aws.amazon.com/blogs/security/how-to-implement-password-less-authentication-with-amazon-cognito-and-webauthn/)
