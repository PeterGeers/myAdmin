# Implementation Plan: Security Hardening

## Overview

This implementation plan addresses nine critical security vulnerabilities in the myAdmin Flask backend. The work is organized into independent, composable modules that integrate with the existing decorator-based authentication and middleware pipeline. Each task builds incrementally, starting with core infrastructure (JWT verification), then layering in tenant isolation, endpoint removal, AI sanitization, CORS, middleware hardening, rate limiting, log sanitization, and per-tenant encryption.

## Tasks

- [x] 1. Implement JWT Cryptographic Signature Verification
  - [x] 1.1 Create the JWTVerifier class in `backend/src/auth/jwt_verifier.py`
    - Implement `JWTVerifier.__init__` with user_pool_id, region, app_client_id, cache_ttl (default 3600s), fetch_timeout (default 5s)
    - Implement `_fetch_jwks()` to retrieve JWKS from `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json` with configured timeout
    - Implement `_get_signing_key(kid)` with cache lookup and single refresh-on-miss logic
    - Implement `verify_token(token)` that verifies RS256 signature, validates `iss`, `aud`/`client_id`, and `exp` (with 30s clock skew tolerance)
    - Implement JWKS cache with in-memory `JWKSCache` dataclass (keys dict, fetched_at timestamp, TTL)
    - Handle JWKS endpoint unreachable: use cached keys if available, else raise ServiceUnavailableError (HTTP 503)
    - Raise `InvalidTokenError` for signature/issuer/audience failures (HTTP 401), `TokenExpiredError` for expiration (HTTP 401)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x] 1.2 Integrate JWTVerifier into the `@cognito_required` decorator
    - Replace current `extract_user_credentials()` base64 payload decoding with `JWTVerifier.verify_token()` call
    - Instantiate JWTVerifier as a singleton using environment variables (`COGNITO_USER_POOL_ID`, `COGNITO_REGION`, `COGNITO_APP_CLIENT_ID`)
    - Map verification exceptions to proper HTTP error responses (401, 503)
    - Ensure backward compatibility: decoded payload still provides `sub`, `custom:tenants`, `cognito:groups` to downstream code
    - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.7, 1.9_

  - [x] 1.3 Write property tests for JWT verification (Properties 1–4)
    - **Property 1: JWT Signature Verification** — Generate random payloads + RSA keypairs, sign with RS256 and verify acceptance; sign with other algorithms (HS256, RS384) and verify rejection
    - **Validates: Requirements 1.2, 1.3**
    - **Property 2: JWT Issuer Validation** — Generate JWTs with varied `iss` claims, verify rejection when issuer doesn't match configured URL
    - **Validates: Requirements 1.5**
    - **Property 3: JWT Audience Validation** — Generate JWTs with varied `aud`/`client_id` claims, verify rejection when neither matches configured App Client ID
    - **Validates: Requirements 1.6**
    - **Property 4: JWT Expiration with Clock Skew** — Generate JWTs with varied `exp` claims around current_time ± 30s boundary, verify acceptance/rejection
    - **Validates: Requirements 1.7**

  - [x] 1.4 Write unit tests for JWT verification edge cases
    - Test kid refresh flow (unknown kid triggers single cache refresh)
    - Test JWKS endpoint timeout (returns cached keys or 503)
    - Test specific error messages for each rejection reason
    - Test cache TTL expiration and refresh
    - _Requirements: 1.4, 1.8, 1.9_

- [x] 2. Enforce Tenant Isolation on Unprotected Routes
  - [x] 2.1 Add `@tenant_required()` to PDF validation routes
    - Add decorator to `pdf_validate_urls_stream` and `pdf_validate_urls` in `pdf_validation_routes.py`
    - Validate `administration` query parameter against user's JWT `custom:tenants` claim
    - If `administration` param is missing/empty, default to user's current tenant from X-Tenant header or first JWT tenant value
    - _Requirements: 2.1, 2.2, 2.9_

  - [x] 2.2 Add tenant filtering to missing_invoices_routes
    - Add `@tenant_required()` to `get_transactions` endpoint
    - Add `administration = %s` filter to the SELECT query with tenant as bound parameter
    - Add `@tenant_required()` to `update-transaction-refs` endpoint
    - Add `administration = %s` filter to the UPDATE query with tenant as bound parameter
    - _Requirements: 2.3, 2.4_

  - [x] 2.3 Add tenant isolation to invoice and banking routes
    - Add `@tenant_required()` to `approve_transactions` in `invoice_routes.py`, pass tenant to service layer
    - Add `@tenant_required()` to `check_sequences` in `banking_routes.py`, scope sequence check to validated tenant
    - Add `@tenant_required()` to `check_sequence` in `banking_routes.py`, validate `administration` param against JWT tenants
    - If `administration` param is missing/empty on `check_sequence`, return HTTP 400 with error message
    - _Requirements: 2.5, 2.6, 2.7, 2.8, 2.10_

  - [x] 2.4 Write property tests for tenant isolation (Properties 5–6)
    - **Property 5: Tenant Access Validation** — Generate (administration_parameter, user_tenants_list) pairs, verify access granted iff administration ∈ user_tenants, else HTTP 403
    - **Validates: Requirements 2.1, 2.2, 2.7, 2.8**
    - **Property 6: Query-Level Tenant Filtering** — Generate tenant values, verify resulting SQL contains `administration = %s` WHERE/AND clause with tenant as bound parameter
    - **Validates: Requirements 2.3, 2.4, 2.6**

  - [x] 2.5 Write unit tests for tenant isolation endpoints
    - Test HTTP 403 response when user lacks access to requested tenant
    - Test HTTP 400 when `check_sequence` called without administration parameter
    - Test default tenant behavior when administration param is missing on PDF validation routes
    - _Requirements: 2.8, 2.9, 2.10_

- [x] 3. Remove Migration Endpoint
  - [x] 3.1 Delete migration route and blueprint registration
    - Delete `migration_routes.py` from the routes directory
    - Remove `migration_bp` registration from `app.py`
    - Remove any `ALLOW_MIGRATION` environment variable references from codebase
    - Verify that requests to `/api/migration/opening-balances/migrate` return HTTP 404
    - _Requirements: 3.1, 3.3_

  - [x] 3.2 Write unit tests for migration endpoint removal
    - Test that `/api/migration/opening-balances/migrate` returns 404
    - Test that no route matches the migration path pattern
    - _Requirements: 3.1, 3.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement AI Prompt Injection Prevention
  - [x] 5.1 Create the AISanitizer class in `backend/src/services/ai_sanitizer.py`
    - Define `INJECTION_PATTERNS` regex list (role reassignment, system delimiters, meta-instructions)
    - Implement `sanitize(text)` that strips injection patterns, truncates to MAX_TEXT_LENGTH (10000 chars), and checks rejection threshold (>50% removed)
    - Implement `build_extraction_prompt(sanitized_text, vendor_hint, previous_transactions)` with system/user role separation and anchoring system message
    - Implement `validate_response(response)` to check required fields (date, total_amount, vat_amount, description, vendor) and types (string/number)
    - Return `SanitizeResult` dataclass with text, was_truncated, patterns_removed, rejected fields
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 5.2 Integrate AISanitizer into AI extraction callers
    - Update `ai_extractor.py` (`AIExtractor.extract_invoice_data`) to sanitize PDF text through `AISanitizer.sanitize()` before prompt construction
    - Update `services/invoice_test_service.py` (`_call_ai_with_custom_prompt` and `rerun_with_custom_prompt`) to sanitize user-provided text
    - Replace single-user-role message pattern with system + user role separation via `build_extraction_prompt()`
    - Handle rejection (>50% stripped): return HTTP 422 with error message
    - Handle AI response validation failure: discard response, return HTTP 422
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [x] 5.3 Write property tests for AI sanitizer (Properties 7–10)
    - **Property 7: AI Injection Pattern Removal** — Generate text with embedded injection patterns at random positions, verify sanitized output matches none of the injection regexes
    - **Validates: Requirements 4.1**
    - **Property 8: AI Text Truncation** — Generate strings of length > 10000, verify sanitized output ≤ 10000 characters
    - **Validates: Requirements 4.4**
    - **Property 9: AI Response Validation** — Generate dicts with missing/wrong-typed fields, verify `validate_response` returns False for invalid responses and True for valid ones
    - **Validates: Requirements 4.5**
    - **Property 10: AI Rejection Threshold** — Generate text where >50% is injection patterns, verify sanitizer returns rejection result
    - **Validates: Requirements 4.6**

  - [x] 5.4 Write unit tests for AI sanitizer
    - Test specific injection pattern examples (role reassignment, system delimiters, meta-instructions)
    - Test system message anchoring structure
    - Test response validation with edge cases (null fields, wrong types, missing fields)
    - _Requirements: 4.1, 4.2, 4.5_

- [x] 6. Harden CORS Policy
  - [x] 6.1 Update CORS configuration in `backend/src/app.py`
    - Configure `ALLOWED_ORIGINS` from environment variable with explicit frontend domain (no wildcard, no "null")
    - Set `supports_credentials: True` only for allowlisted origins
    - Set `vary_header: True` to add `Vary: Origin` response header
    - Include development origins (`localhost:3000`, `localhost:3001`) only when `RAILWAY_ENVIRONMENT != 'production'`
    - Ensure preflight OPTIONS responses omit CORS headers for non-allowlisted origins
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 6.2 Write property test for CORS origin enforcement (Property 11)
    - **Property 11: CORS Origin Enforcement** — Generate random origin strings, verify: if origin not in allowlist → no Access-Control-Allow-Origin/Credentials headers; if origin in allowlist → both headers present
    - **Validates: Requirements 5.3, 5.4, 5.5**

  - [x] 6.3 Write unit tests for CORS policy
    - Test that "null" is not in allowed origins
    - Test that wildcard "\*" is not in allowed origins
    - Test preflight response for disallowed origin
    - Test Vary: Origin header presence
    - _Requirements: 5.1, 5.2, 5.6_

- [x] 7. Harden Security Middleware
  - [x] 7.1 Update `backend/src/security_audit.py` to enforce security regardless of environment
    - Remove all `FLASK_DEBUG` and `TEST_MODE` bypass logic from `create_security_middleware`
    - Remove host/IP-based bypass logic
    - Keep only health check endpoint whitelist (`/api/health`, `/api/status`)
    - Add warning log when `FLASK_DEBUG=true` AND `RAILWAY_ENVIRONMENT=production`
    - Ensure suspicious pattern detection runs on ALL requests (including API routes)
    - Apply security response headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy) to all responses
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.2 Write property test for security middleware (Property 12)
    - **Property 12: Security Middleware Environment Independence** — Generate combinations of FLASK_DEBUG, TEST_MODE, host, remote_addr values; verify pattern detection and security headers always applied (except health checks) when RAILWAY_ENVIRONMENT=production
    - **Validates: Requirements 6.1, 6.2, 6.4**

  - [x] 7.3 Write unit tests for security middleware
    - Test debug mode warning log when FLASK_DEBUG=true in production
    - Test security response headers present on all non-health-check responses
    - Test suspicious pattern detection (SQL injection, XSS, path traversal examples)
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Rate Limiting on Authentication Endpoints
  - [x] 9.1 Create the RateLimiter class in `backend/src/auth/rate_limiter.py`
    - Implement `__init__` with max_per_email (default 5), max_per_ip (default 10), window_seconds (default 900)
    - Implement sliding window store using `dict[str, list[float]]` with `threading.Lock` for thread safety
    - Implement `check_rate_limit(email, ip)` returning `RateLimitResult(allowed, retry_after_seconds, limit_type)`
    - Implement `record_request(email, ip)` to record timestamps for both email and IP windows
    - Implement `get_client_ip(request)` extracting leftmost IP from X-Forwarded-For or falling back to remote_addr
    - Clean expired timestamps on each check (timestamps older than window_seconds)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 9.2 Integrate RateLimiter into the password reset endpoint
    - Apply rate limiting check before processing password reset requests
    - Return HTTP 429 with `Retry-After` header when limit exceeded
    - Track by both email address and client IP independently
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 9.3 Write property tests for rate limiter (Properties 13–14)
    - **Property 13: Sliding Window Enforcement** — Generate request sequences with timestamps; verify rejection when >5 same-email or >10 same-IP requests within 900s window; verify both limits tracked independently
    - **Validates: Requirements 7.1, 7.3, 7.4**
    - **Property 14: IP Extraction** — Generate X-Forwarded-For header values with one or more comma-separated IPs; verify leftmost IP extracted
    - **Validates: Requirements 7.5**

  - [x] 9.4 Write unit tests for rate limiter
    - Test HTTP 429 response format with Retry-After header
    - Test Retry-After value calculation (seconds until earliest request expires)
    - Test concurrent access thread safety
    - _Requirements: 7.2, 7.3_

- [x] 10. Implement Sensitive Data Logging Prevention
  - [x] 10.1 Create log sanitizer utility and remove existing credential logging
    - Create `mask_sensitive_value(key, value)` utility function that returns `"[REDACTED]"` for known sensitive key patterns (API key, password, encryption key, OAuth secret, JWT key)
    - Remove `print(f"AI Extractor initialized with API key: {self.api_key[:20]}...")` from `ai_extractor.py`
    - Audit and fix all `print()` and `logger.*` calls at startup that log credential values
    - Ensure exception handlers in credential/key code do not include raw secret values in log entries
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 10.2 Write property test for sensitive value masking (Property 15)
    - **Property 15: Sensitive Value Masking** — Generate (key_name, secret_value) pairs where key matches sensitive patterns; verify return value is `"[REDACTED]"` and contains no substring of length ≥ 3 from original secret
    - **Validates: Requirements 8.2, 8.4**

  - [x] 10.3 Write unit tests for log sanitization
    - Test startup log capture contains no API key values
    - Test exception log capture for credential code contains no raw secrets
    - Test mask function for various sensitive key patterns
    - _Requirements: 8.1, 8.2, 8.4_

- [x] 11. Implement Per-Tenant Encryption Key Isolation
  - [x] 11.1 Add tenant-derived key logic to `backend/src/services/credential_service.py`
    - Implement `_derive_tenant_key(master_key, tenant)` using PBKDF2-SHA256 with 100,000 iterations, 32-byte output, tenant identifier as salt
    - Update `encrypt_credential()` to use tenant-derived key instead of master key
    - Update `get_credential()` / decrypt logic: try tenant-derived key first, fall back to master key on `InvalidToken`, re-encrypt with tenant-derived key on successful master-key decryption
    - Raise `CredentialDecryptionError` (without key material) when both keys fail
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 11.2 Write property tests for encryption (Properties 16–19)
    - **Property 16: Per-Tenant Key Uniqueness** — Generate pairs of distinct tenant identifiers with fixed master key; verify derived keys differ; verify same tenant+master produces deterministic key
    - **Validates: Requirements 9.1**
    - **Property 17: Encryption Round-Trip** — Generate (tenant, credential_value) pairs; verify encrypt then decrypt with same tenant-derived key returns original value
    - **Validates: Requirements 9.2, 9.3**
    - **Property 18: Fallback Decryption with Migration** — Generate credentials encrypted with master key; verify tenant-derived decryption fails then master-key fallback succeeds, and re-encrypted value is decryptable with tenant-derived key
    - **Validates: Requirements 9.5**
    - **Property 19: Error Messages Without Key Exposure** — Generate unrecoverable encrypted values; verify exception message contains no bytes from master key, derived key, or encrypted value
    - **Validates: Requirements 9.6**

  - [x] 11.3 Write unit tests for encryption key isolation
    - Test lazy migration example (master-key encrypted credential successfully migrated)
    - Test double-failure error format (CredentialDecryptionError with context, no key material)
    - Test deterministic key derivation
    - _Requirements: 9.4, 9.5, 9.6_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (19 total across Properties 1–19)
- Unit tests validate specific examples and edge cases
- All implementation targets the Flask backend exclusively (Python)
- The project uses pytest with Hypothesis for property-based testing (`.hypothesis/` already present)
- Each module is independently deployable per the design's "minimal blast radius" principle

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "5.1", "10.1"] },
    {
      "id": 1,
      "tasks": ["1.2", "1.3", "3.2", "5.2", "6.1", "7.1", "9.1", "11.1"]
    },
    {
      "id": 2,
      "tasks": [
        "1.4",
        "2.1",
        "2.2",
        "2.3",
        "5.3",
        "5.4",
        "6.2",
        "6.3",
        "7.2",
        "7.3",
        "9.2",
        "10.2",
        "10.3",
        "11.2",
        "11.3"
      ]
    },
    { "id": 3, "tasks": ["2.4", "2.5", "9.3", "9.4"] }
  ]
}
```
