"""
Backend environment/health report (Req 6) — pure report-builder.

Task 8 (`.kiro/specs/Common/test-environment/first-draft/tasks.md`): the backend
environment/health report names the active environment, pool labels, MySQL target,
DynamoDB prefix, and SAM compute surface, so a developer can confirm the environment
without reading source, `.env`, or SAM templates.

Design contract (design.md §11 "Health report (Req 6)"):

> A backend endpoint/command (`GET /api/environment` and/or the `check` command)
> returns the active `APP_ENV` (6.1), the Pool_Registry pool label and identity-block
> pool label (6.2), the resolved MySQL target named by resolved identity (6.3), and
> the DynamoDB prefix plus observable SAM API base URL and stack label (6.4). All
> values derive from the resolver (6.5). Secrets are omitted — only non-secret labels/
> identifiers (6.6).

Design decisions that keep this safe and non-drifting:

- **Derived, not independently read (Req 6.5 / Property 9 non-drift).** The report is
  built *purely* from a :class:`~environment.resolver.ResolvedConfig`. Every value in
  the payload equals the corresponding field of that same resolved config — the one
  the planes consume. The builder never re-reads `APP_ENV`, the definition, `.env`, or
  the hostname, so the report cannot drift from the active configuration.

- **Secrets omitted, not masked (Req 6.6 / Property 9 secret-omission).** The payload
  carries only non-secret labels and public identifiers: the environment name, Cognito
  pool *label* and *public* pool/client ids, the MySQL *target label* and schema, the
  DynamoDB prefix, and the SAM api base url / stack label / authorizer pool id. It
  NEVER includes a secret value or a secret-shaped reference — specifically never the
  Cognito ``client_secret_ref`` nor the MySQL ``*_ref`` connection references (host/
  port/user/password env-var names), which are deliberately excluded so a secret value
  injected into any secret field of the definition can never appear in the payload.

The Cognito ``pool_id``/``client_id`` and the SAM ``authorizer_pool_id`` ARE included
because they are non-secret public identifiers (they already live in the committed
Environment_Definition as public ids, per Req 8.5).
"""

from typing import Any, Dict

from .resolver import ResolvedConfig


def build_environment_report(resolved: ResolvedConfig) -> Dict[str, Any]:
    """Build the non-secret environment/health report from a resolved config.

    Pure function: the returned dict is derived entirely from ``resolved`` (Req 6.5),
    so it cannot drift from the configuration the planes actually use (Property 9
    non-drift). No secret value or secret-shaped reference is included (Req 6.6 /
    Property 9 secret-omission).

    Args:
        resolved: The single :class:`ResolvedConfig` produced by the
            Environment_Resolver and consumed by every plane.

    Returns:
        A JSON-serializable dict of non-secret labels/identifiers:

        - ``app_env`` — the active APP_ENV value (Req 6.1)
        - ``cognito_pool_label`` / ``cognito_pool_id`` / ``cognito_client_id`` —
          the Pool_Registry / identity-block pool label and public ids (Req 6.2)
        - ``identity_block_pool_label`` — alias of the active pool label used by the
          identity block (Req 6.2); equals ``cognito_pool_label`` because both the
          registry and the identity block resolve from the same APP_ENV.
        - ``mysql_target_label`` / ``mysql_schema`` — the resolved MySQL target named
          by its resolved identity (Req 6.3)
        - ``dynamodb_prefix`` — the resolved DynamoDB table prefix (Req 6.4)
        - ``sam_api_base_url`` / ``sam_stack_label`` / ``sam_authorizer_pool_id`` —
          the observable SAM compute surface (Req 6.4)
    """
    return {
        # Active environment (Req 6.1)
        "app_env": resolved.app_env.value,
        # Cognito identity — pool labels + public identifiers only (Req 6.2).
        # client_secret_ref is intentionally NOT included (Req 6.6).
        "cognito_pool_label": resolved.cognito.pool_label,
        "cognito_pool_id": resolved.cognito.pool_id,
        "cognito_client_id": resolved.cognito.client_id,
        "identity_block_pool_label": resolved.cognito.pool_label,
        # MySQL target named by resolved identity (Req 6.3). Only the non-secret
        # target label and schema — never the host/port/user/password *_ref values.
        "mysql_target_label": resolved.mysql.target_label,
        "mysql_schema": resolved.mysql.schema,
        # SAM compute surface + DynamoDB prefix (Req 6.4).
        "dynamodb_prefix": resolved.dynamodb_prefix,
        "sam_api_base_url": resolved.sam_api_base_url,
        "sam_stack_label": resolved.sam_stack_label,
        "sam_authorizer_pool_id": resolved.sam_authorizer_pool_id,
    }
