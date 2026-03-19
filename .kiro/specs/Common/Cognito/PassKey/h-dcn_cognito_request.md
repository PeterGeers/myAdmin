# Cognito Passkey Implementation with Identity Linking — Best Practices

> Reference documentation based on the H-DCN Portal implementation.
> Use this as a blueprint when adding passkey + federated identity (Google) to your own project.

---

## Architecture Overview

The system implements passwordless authentication with three identity paths that all converge on a single Cognito User Pool:

1. **Passkey/WebAuthn** — primary auth for all users
2. **Google OAuth** — SSO for staff (`@h-dcn.nl`) and general Google accounts
3. **Email verification** — fallback recovery path

The key challenge: a user who signs up with a passkey and later logs in via Google (or vice versa) creates two separate Cognito identities. The **identity linking / prime ID resolution** pattern solves this.

---

## 1. Prime ID Resolution Pattern

### The Problem

When a user authenticates via Google OAuth, Cognito auto-creates a federated identity (`Google_123456`) separate from any existing email-based account. This means:

- The same person can have two Cognito users (email-based + Google-federated)
- Groups/roles assigned to one identity are invisible to the other
- The frontend receives different JWT tokens depending on login method

### The Solution: Post-Authentication Identity Resolution

The `cognito_post_authentication` Lambda trigger runs after every login (regardless of method) and resolves the user to a single "prime" identity:

```python
# backend/handler/cognito_post_authentication/app.py

def handle_user_authentication(user_pool_id, username, email, given_name, family_name):
    # 1. Get current groups for this identity
    current_groups = get_user_groups(user_pool_id, username)

    # 2. Filter out auto-generated federated groups (e.g. eu-west-1_xxx_Google)
    federated_groups = [g for g in current_groups if '_Google' in g or '_Facebook' in g or '_SAML' in g]
    meaningful_groups = [g for g in current_groups if g not in federated_groups]

    # 3. If user only has federated groups, resolve their real roles from the Members table
    if federated_groups and not meaningful_groups:
        member_status = check_member_status(email)  # DynamoDB lookup by email
        if member_status in ['active', 'approved']:
            add_user_to_group(user_pool_id, username, 'hdcnLeden')
```

### Best Practices

- **Email is the prime key.** Regardless of how a user authenticates, their email address is the canonical identifier. All DynamoDB lookups, role assignments, and audit logs use email.
- **Never trust federated groups alone.** Auto-generated groups like `eu-west-1_OAT3oPCIm_Google` carry no business meaning. Always check for meaningful groups (`hdcnLeden`, `Members_CRUD_All`, etc.).
- **Run identity resolution on every login.** The post-authentication trigger fires for both native and federated logins. This ensures roles stay in sync even if a user switches login methods.
- **Use DynamoDB as the source of truth for member status.** Cognito groups can drift. The Members table holds the authoritative status (`active`, `approved`, `pending`), and the post-auth trigger reconciles.

---

## 2. WebAuthn Challenge/Response Flow

### Registration Flow

```
Frontend                          Backend (Lambda)                    Cognito
   |                                  |                                 |
   |-- POST /auth/passkey/register -->|                                 |
   |                                  |-- admin_get_user (check exist) -|
   |                                  |<- generate challenge (32 bytes) |
   |<-- registration options ---------|                                 |
   |                                  |                                 |
   |-- navigator.credentials.create() |                                 |
   |-- POST /auth/passkey/register/complete -->|                        |
   |                                  |-- admin_update_user_attributes -|
   |                                  |   (custom:passkey_registered,   |
   |                                  |    custom:passkey_cred_ids,     |
   |                                  |    custom:passkey_date)         |
   |<-- { verified: true } -----------|                                 |
```

### Authentication Flow

```
Frontend                          Backend (Lambda)                    Cognito
   |                                  |                                 |
   |-- POST /auth/passkey/login ----->|                                 |
   |                                  |-- admin_get_user --------------->|
   |                                  |   (check passkey_registered,    |
   |                                  |    load passkey_cred_ids)       |
   |<-- authentication options -------|                                 |
   |   (challenge + allowCredentials) |                                 |
   |                                  |                                 |
   |-- navigator.credentials.get() ---|                                 |
   |-- POST /auth/passkey/login/complete -->|                           |
   |                                  |-- verify credential             |
   |                                  |-- admin_list_groups_for_user -->|
   |                                  |-- generate JWT (access + id) ---|
   |<-- { authenticationResult } -----|                                 |
```

### Best Practices

- **Store multiple credential IDs per user.** Users may register passkeys on multiple devices. Store them as a JSON array in `custom:passkey_cred_ids`:
  ```python
  existing_credentials.append(credential_id)
  cognito_client.admin_update_user_attributes(
      UserPoolId=USER_POOL_ID, Username=email,
      UserAttributes=[{
          'Name': 'custom:passkey_cred_ids',
          'Value': json.dumps(existing_credentials)
      }]
  )
  ```
- **Support legacy single-credential fallback.** If migrating from single-credential storage, check both `custom:passkey_credential_id` (legacy) and `custom:passkey_cred_ids` (current).
- **Dynamic RP ID based on environment.** The relying party ID must match the domain the user is on:
  ```python
  rp_id = 'portal.h-dcn.nl'  # production
  if 'localhost' in origin:
      rp_id = 'localhost'
  elif 'cloudfront.net' in origin:
      rp_id = urlparse(origin).hostname
  ```
- **Cross-device authentication.** Offer longer timeouts (5 min vs 1 min) for cross-device flows. Leave `allowCredentials` empty to allow any credential when doing cross-device auth.
- **Don't require `authenticatorAttachment`.** Removing this constraint allows both platform (biometrics) and cross-platform (security keys, phone-as-authenticator) to work.
- **Use `attestation: 'none'`** for broader device compatibility unless you need to verify the authenticator make/model.

---

## 3. Post-Login Identity Resolution Middleware

### Frontend: Enhanced Groups Header

The frontend resolves the user's effective roles and sends them as a custom header on every API call:

```typescript
// frontend/src/utils/authHeaders.ts
async function getAuthHeaders(): Promise<Record<string, string>> {
  const session = await fetchAuthSession();
  const token = session.tokens?.accessToken?.toString();
  const userGroups = getCurrentUserRoles(); // from JWT cognito:groups

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  if (userGroups.length > 0) {
    const validGroups = filterValidRoles(userGroups);
    headers['X-Enhanced-Groups'] = JSON.stringify(validGroups);
  }

  return headers;
}
```

### Backend: Credential Extraction with Enhanced Groups Priority

```python
# backend/layers/auth-layer/python/shared/auth_utils.py

def extract_user_credentials(event):
    # 1. Extract and decode JWT from Authorization header
    # 2. Check for X-Enhanced-Groups header (frontend-resolved roles)
    enhanced_groups_header = headers.get('X-Enhanced-Groups')
    if enhanced_groups_header:
        enhanced_groups = json.loads(enhanced_groups_header)
        if isinstance(enhanced_groups, list):
            return user_email, enhanced_groups, None  # Use frontend-resolved roles

    # 3. Fallback to JWT token groups
    user_roles = payload.get('cognito:groups', [])
    return user_email, user_roles, None
```

### Best Practices

- **Frontend resolves, backend trusts (with validation).** The frontend knows which identity provider was used and can combine roles from multiple sources. The backend validates the JWT signature but uses the enhanced groups for authorization.
- **Always allow CORS for the custom header.** Add `X-Enhanced-Groups` to your API Gateway CORS config:
  ```yaml
  AllowHeaders: "'Content-Type,Authorization,X-Enhanced-Groups'"
  ```
- **Filter invalid roles on the frontend.** Only send roles that match your known role schema. This prevents injection of arbitrary group names.
- **Graceful fallback.** If `X-Enhanced-Groups` is missing or malformed, fall back to JWT `cognito:groups`. Never fail the request because of a missing header.

---

## 4. Cognito Trigger Architecture

### Trigger Chain

| Trigger | When | Purpose |
|---|---|---|
| `PostConfirmation_ConfirmSignUp` | After email verification | Assign initial role based on Members table status |
| `PostAuthentication_Authentication` | Every login | Identity resolution, role sync for federated users |
| `CustomMessage_*` | Email events | Dutch-language branded email templates |
| Role Assignment (DynamoDB Stream) | Member status change | Auto-assign/revoke `hdcnLeden` when status changes |

### Best Practices

- **Never block authentication on trigger errors.** Always return the original event in catch blocks:
  ```python
  except Exception as e:
      logger.error(f"Error: {str(e)}")
      return event  # Don't block the user
  ```
- **Post-confirmation handles native signups, post-authentication handles everything.** Google SSO users bypass post-confirmation entirely, so post-authentication is your safety net for role assignment.
- **Use DynamoDB Streams for reactive role management.** When a member's status changes from `pending` to `active`, the stream trigger automatically assigns `hdcnLeden`. No manual intervention needed.
- **Audit every role decision.** Log the email, current groups, member status, and the decision made. This is invaluable for debugging "why can't I access X" issues.

---

## 5. Passkey Token Generation

Since passkey authentication bypasses Cognito's native auth flow, you generate custom JWTs that mirror Cognito's token structure:

```python
access_payload = {
    'sub': email,
    'email': email,
    'cognito:groups': groups,       # Same claim name as Cognito
    'token_use': 'access',
    'auth_method': 'passkey',       # Custom claim for audit
    'client_id': COGNITO_CLIENT_ID,
    'exp': current_time + 3600,
}

access_token = jwt.encode(access_payload, SECRET_KEY, algorithm='HS256')
```

### Best Practices

- **Mirror Cognito's JWT structure exactly.** Use the same claim names (`cognito:groups`, `token_use`, `sub`, `email`) so your backend auth middleware works identically for both Cognito-issued and passkey-issued tokens.
- **Add an `auth_method` claim.** This lets you distinguish passkey logins from Cognito logins in audit logs and analytics.
- **Use proper signing keys in production.** The example uses a symmetric secret; in production, use RSA/EC keys stored in AWS Secrets Manager or KMS. Consider using Cognito's own token endpoint if possible.
- **Match the token expiration to your Cognito config.** If Cognito tokens expire in 1 hour, your passkey tokens should too.
- **Include both access and ID tokens.** The frontend expects both, and different parts of your app may use different tokens.

---

## 6. Security Considerations

- **Challenge storage.** Store WebAuthn challenges server-side (DynamoDB/Redis with TTL) and validate them on completion. Don't rely on the client sending the challenge back.
- **Credential verification.** In production, verify the authenticator's signature against the stored public key. Don't skip this step.
- **Rate limiting.** Apply rate limits to passkey registration and authentication endpoints to prevent abuse.
- **Passkey revocation.** Provide an admin endpoint to remove specific credential IDs from a user's `custom:passkey_cred_ids` when a device is lost/stolen.
- **Token rotation.** Implement refresh token logic for passkey-issued tokens, similar to Cognito's refresh flow.

---

## 7. Key Custom Attributes in Cognito

| Attribute | Type | Purpose |
|---|---|---|
| `custom:passkey_registered` | String (`true`/`false`) | Quick check if user has any passkey |
| `custom:passkey_cred_ids` | String (JSON array) | All registered credential IDs |
| `custom:passkey_date` | String (ISO 8601) | Last passkey registration timestamp |
| `custom:passkey_credential_id` | String | Legacy single credential (backward compat) |
| `custom:member_id` | String | Links Cognito user to Members table |

---

## 8. Implementation Phases

If you're building this from scratch, here's the recommended order:

1. **Cognito User Pool** with email-based signup (no password required)
2. **WebAuthn registration/authentication** endpoints
3. **Custom JWT generation** for passkey auth
4. **Post-confirmation trigger** for native signup role assignment
5. **Post-authentication trigger** for login-time role sync
6. **Google OAuth identity provider** — this is where identity linking becomes critical
7. **Enhanced Groups middleware** for cross-provider role resolution
8. **DynamoDB Stream trigger** for reactive role management

Phase 6 is where the prime ID pattern matters most. Everything before that works with a single identity per user.

---

*Based on the H-DCN Portal codebase — a production Cognito implementation with passkeys, Google SSO, and role-based access control on AWS SAM.*
