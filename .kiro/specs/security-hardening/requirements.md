# Requirements Document

## Introduction

This specification addresses critical security vulnerabilities identified during a comprehensive security assessment of the myAdmin platform. myAdmin is a multi-tenant SaaS platform handling financial administration and short-term rental management. The assessment revealed that JWT tokens lack cryptographic signature verification, several routes miss tenant isolation decorators, an unauthenticated migration endpoint exists, AI prompt injection risks are present, and various infrastructure security gaps need hardening. These findings are prioritized by risk score and organized into logical security domains.

## Glossary

- **JWT_Verifier**: The module responsible for cryptographic verification of JWT token signatures against the AWS Cognito JWKS (JSON Web Key Set) endpoint
- **Cognito_JWKS**: The publicly available JSON Web Key Set published by AWS Cognito, containing the public keys used to verify JWT token signatures
- **Tenant_Guard**: The `@tenant_required()` decorator that validates the requesting user has access to the specified tenant before serving tenant-scoped data
- **Auth_Decorator**: The `@cognito_required()` decorator that extracts and validates JWT credentials from the Authorization header
- **AI_Sanitizer**: The component responsible for sanitizing user-provided content before including it in prompts sent to external AI services
- **Rate_Limiter**: The middleware component that limits the number of requests a client can make to a specific endpoint within a time window
- **CORS_Policy**: The Cross-Origin Resource Sharing configuration that controls which origins may access the API
- **Security_Middleware**: The Flask middleware that detects suspicious request patterns (SQL injection, XSS, path traversal) and blocks malicious requests
- **Encryption_Service**: The service responsible for encrypting and decrypting sensitive credentials stored in the database using Fernet symmetric encryption
- **Migration_Endpoint**: The `/api/migration/opening-balances/migrate` route that allows unauthenticated access protected only by an environment variable gate and hardcoded secret

## Requirements

### Requirement 1: JWT Cryptographic Signature Verification

**User Story:** As a platform operator, I want JWT tokens to be cryptographically verified against the Cognito JWKS endpoint, so that attackers cannot fabricate tokens with arbitrary roles or tenant claims.

#### Acceptance Criteria

1. WHEN a request with a Bearer token arrives, THE JWT_Verifier SHALL fetch and cache the Cognito JWKS public keys from the configured Cognito User Pool endpoint
2. WHEN a JWT token is presented for authentication, THE JWT_Verifier SHALL verify the token signature using the matching public key from the Cognito JWKS, accepting only the RS256 algorithm
3. IF the JWT signature verification fails, THEN THE JWT_Verifier SHALL reject the request with HTTP 401 and a message indicating invalid token signature
4. IF the signing key identifier in the JWT header does not match any key in the cached JWKS, THEN THE JWT_Verifier SHALL refresh the JWKS cache once and retry verification before rejecting the request with HTTP 401
5. IF the `iss` (issuer) claim does not match the configured Cognito User Pool URL, THEN THE JWT_Verifier SHALL reject the request with HTTP 401 and a message indicating invalid token issuer
6. IF the `aud` or `client_id` claim does not match the configured Cognito App Client ID, THEN THE JWT_Verifier SHALL reject the request with HTTP 401 and a message indicating invalid token audience
7. IF the `exp` claim indicates the token has expired beyond a clock skew tolerance of 30 seconds, THEN THE JWT_Verifier SHALL reject the request with HTTP 401 and a message indicating token expiration
8. THE JWT_Verifier SHALL cache JWKS keys in memory with a configurable TTL defaulting to 3600 seconds, and SHALL use a fetch timeout of 5 seconds when retrieving keys from the Cognito JWKS endpoint
9. IF the Cognito JWKS endpoint is unreachable or returns a non-success response, THEN THE JWT_Verifier SHALL continue using previously cached keys if available, or reject the request with HTTP 503 and a message indicating authentication service unavailability if no cached keys exist

### Requirement 2: Tenant Isolation Enforcement on Unprotected Routes

**User Story:** As a platform operator, I want all routes serving tenant-scoped data to enforce tenant isolation, so that users from one tenant cannot access data belonging to another tenant.

#### Acceptance Criteria

1. WHEN the `pdf_validate_urls_stream` endpoint receives a request with an `administration` query parameter, THE Tenant_Guard SHALL validate that the `administration` value is present in the requesting user's JWT `custom:tenants` claim before executing the validation
2. WHEN the `pdf_validate_urls` endpoint receives a request with an `administration` query parameter, THE Tenant_Guard SHALL validate that the `administration` value is present in the requesting user's JWT `custom:tenants` claim before executing the validation
3. WHEN the `get_transactions` endpoint in missing_invoices_routes receives a request, THE Tenant_Guard SHALL extract the tenant from the `X-Tenant` header or JWT token and include an `administration = %s` filter in the database query so that only transactions belonging to the validated tenant are returned
4. WHEN the `update-transaction-refs` endpoint in missing_invoices_routes receives a request, THE Tenant_Guard SHALL include an `administration = %s` filter in the UPDATE query so that only transactions belonging to the validated tenant are modified
5. WHEN the `approve_transactions` endpoint in invoice_routes receives a request, THE Tenant_Guard SHALL extract the tenant from the `X-Tenant` header or JWT token and pass it to the service layer so that transactions are saved only under the validated tenant's administration
6. WHEN the `check_sequences` endpoint in banking_routes receives a request, THE Tenant_Guard SHALL extract the tenant from the `X-Tenant` header or JWT token and scope the sequence check to the validated tenant's data
7. WHEN the `check_sequence` endpoint in banking_routes receives a request with an `administration` query parameter, THE Tenant_Guard SHALL validate that the `administration` value is present in the requesting user's JWT `custom:tenants` claim before executing the sequence check
8. IF a request targets a tenant-scoped route and the user does not have access to the requested tenant, THEN THE Tenant_Guard SHALL reject the request with an HTTP 403 response containing an error message indicating access denial
9. IF the `pdf_validate_urls_stream` or `pdf_validate_urls` endpoint receives a request where the `administration` query parameter is missing or empty, THEN THE Tenant_Guard SHALL default to the user's current tenant from the `X-Tenant` header or first JWT `custom:tenants` value rather than querying across all administrations
10. IF the `check_sequence` endpoint receives a request where the `administration` query parameter is missing or empty, THEN THE Tenant_Guard SHALL reject the request with an HTTP 400 response containing an error message indicating that an administration parameter is required

### Requirement 3: Migration Endpoint Removal

**User Story:** As a platform operator, I want the unauthenticated migration endpoint removed from the production codebase, so that attackers cannot exploit it to manipulate financial data.

#### Acceptance Criteria

1. THE Backend SHALL NOT register the `/api/migration/opening-balances/migrate` route or its enclosing Blueprint in the production codebase, such that any request to that path returns HTTP 404
2. IF the migration endpoint functionality is retained for future migrations, THEN THE Backend SHALL protect it with both `@cognito_required(required_permissions=['admin_manage'])` and `@tenant_required()` decorators, enforcing JWT validation and tenant isolation before granting access
3. THE Backend SHALL NOT rely on hardcoded secrets or environment variable gates (e.g., `ALLOW_MIGRATION`) as the sole protection for any data-modifying endpoint; all such endpoints SHALL require token-based authentication via `@cognito_required`
4. IF an unauthenticated request is made to a retained and protected migration endpoint, THEN THE Backend SHALL return HTTP 401 without executing any migration logic or database operations

### Requirement 4: AI Prompt Injection Prevention

**User Story:** As a platform operator, I want user-provided content sanitized before inclusion in AI prompts, so that malicious PDF content cannot manipulate the AI model's behavior or exfiltrate data.

#### Acceptance Criteria

1. WHEN user-uploaded PDF text is included in an AI extraction prompt, THE AI_Sanitizer SHALL strip or escape instruction-override patterns — including role reassignment phrases (e.g., "you are now", "act as"), system message delimiters (e.g., "###", "[SYSTEM]"), and meta-instructions (e.g., "ignore previous instructions", "disregard above") — from the text content before prompt construction
2. THE AI_Sanitizer SHALL use a system message that anchors the AI model's role and explicitly instructs the model to ignore any instructions embedded in the user-provided text
3. WHEN constructing a prompt for invoice extraction, THE AI_Sanitizer SHALL separate the system instructions from user-provided content using distinct message roles (system vs user)
4. IF user-provided text exceeds 10000 characters, THEN THE AI_Sanitizer SHALL truncate the text to the first 10000 characters before inclusion in the prompt
5. IF the AI model response does not contain all required fields (date, total_amount, vat_amount, description, vendor) or any field value does not match its expected type (string for date/description/vendor, number for total_amount/vat_amount), THEN THE AI_Sanitizer SHALL discard the response and return a parsing failure rather than passing potentially manipulated data downstream
6. IF sanitization removes more than 50% of the original text content, THEN THE AI_Sanitizer SHALL reject the extraction request and return an error indicating the document content could not be safely processed

### Requirement 5: CORS Policy Hardening

**User Story:** As a platform operator, I want the CORS policy to reject requests from unexpected origins including "null", so that cross-origin attacks from iframes and file:// URIs are blocked.

#### Acceptance Criteria

1. THE CORS_Policy SHALL NOT include "null" in the list of allowed origins
2. THE CORS_Policy SHALL explicitly enumerate the allowed origins using the configured frontend domain and SHALL NOT use a wildcard ("\*") as an allowed origin value
3. WHILE the application is running in production mode, THE CORS_Policy SHALL reject requests from origins not in the configured allowlist by omitting the `Access-Control-Allow-Origin` response header
4. THE CORS_Policy SHALL set `Access-Control-Allow-Credentials` to "true" only when the request origin matches the configured allowlist; WHEN the origin does not match, THE CORS_Policy SHALL omit the `Access-Control-Allow-Credentials` header from the response
5. WHEN a preflight OPTIONS request arrives with an `Origin` header not in the configured allowlist, THE CORS_Policy SHALL respond without `Access-Control-Allow-Origin` or `Access-Control-Allow-Methods` headers
6. THE CORS_Policy SHALL include a `Vary: Origin` response header on all responses to prevent intermediate caches from serving CORS headers granted to one origin to a different origin

### Requirement 6: Security Middleware Production Enforcement

**User Story:** As a platform operator, I want security middleware to remain active regardless of debug mode settings, so that an accidental debug mode activation in production does not disable security protections.

#### Acceptance Criteria

1. THE Security_Middleware SHALL execute suspicious pattern detection (SQL injection, XSS, path traversal) on all incoming requests regardless of the `FLASK_DEBUG` or `TEST_MODE` environment variable values, with the sole exception of health check endpoints (`/api/health`, `/api/status`)
2. THE Security_Middleware SHALL apply security response headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy) to all responses regardless of the `FLASK_DEBUG` or `TEST_MODE` environment variable values
3. IF the `FLASK_DEBUG` environment variable is set to "true" while the `RAILWAY_ENVIRONMENT` environment variable is set to "production", THEN THE Security_Middleware SHALL log a warning message indicating debug mode misconfiguration but continue enforcing all security checks
4. WHILE the `RAILWAY_ENVIRONMENT` environment variable is set to "production", THE Security_Middleware SHALL NOT bypass security checks based on request host or remote address values

### Requirement 7: Rate Limiting on Authentication Endpoints

**User Story:** As a platform operator, I want rate limiting applied to the password reset endpoint, so that attackers cannot brute-force reset codes or flood the endpoint.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL limit password reset requests to a maximum of 5 requests per email address per 15-minute sliding window
2. IF a client exceeds the rate limit on the password reset endpoint, THEN THE Rate_Limiter SHALL respond with HTTP 429 and a Retry-After header indicating the number of seconds remaining until the earliest request in the window expires
3. THE Rate_Limiter SHALL track rate limits by both client IP address and target email address independently, so that exceeding either limit triggers rejection
4. THE Rate_Limiter SHALL limit password reset requests to a maximum of 10 requests per client IP address per 15-minute sliding window regardless of target email address
5. IF the request includes an X-Forwarded-For header, THEN THE Rate_Limiter SHALL use the leftmost IP address in the X-Forwarded-For chain as the client IP for rate limiting purposes

### Requirement 8: Sensitive Data Logging Prevention

**User Story:** As a platform operator, I want API keys and secrets excluded from application logs, so that credential exposure through log aggregation systems is prevented.

#### Acceptance Criteria

1. THE Backend SHALL NOT log API key values (full or partial) to stdout, stderr, or any configured log handler during application startup or runtime
2. WHEN logging configuration details at startup, THE Backend SHALL mask sensitive values (API keys, database passwords, encryption keys, OAuth client secrets, and JWT signing keys) showing only a redacted indicator instead of any portion of the actual value
3. THE Backend SHALL NOT include JWT tokens, encryption keys, API credentials, or stack traces containing secret values in HTTP response bodies returned to clients
4. IF an exception occurs in code that handles credentials or API keys, THEN THE Backend SHALL log the error type and context description without including the raw secret value in the log entry

### Requirement 9: Per-Tenant Encryption Key Isolation

**User Story:** As a platform operator, I want tenant credentials encrypted with tenant-specific derived keys, so that a single key compromise does not expose all tenants' Google Drive credentials.

#### Acceptance Criteria

1. THE Encryption_Service SHALL derive a unique encryption key per tenant by applying PBKDF2-SHA256 with a minimum of 100,000 iterations and a 32-byte output length to the master `CREDENTIALS_ENCRYPTION_KEY`, using the tenant's administration identifier as the tenant-specific salt
2. WHEN encrypting credentials for a tenant, THE Encryption_Service SHALL use the tenant-derived key rather than the master key directly
3. WHEN decrypting credentials for a tenant, THE Encryption_Service SHALL use the same tenant-derived key that was used during encryption
4. THE Encryption_Service SHALL perform migration of existing credentials from the single master key to tenant-derived keys at decryption time without requiring application restart or scheduled downtime
5. IF decryption with the tenant-derived key fails, THEN THE Encryption_Service SHALL attempt decryption with the master key for backward compatibility, and re-encrypt the credential with the tenant-derived key upon successful master-key decryption
6. IF decryption fails with both the tenant-derived key and the master key, THEN THE Encryption_Service SHALL raise an error indicating the credential is unrecoverable for the specified tenant and credential type, without exposing key material in the error message
