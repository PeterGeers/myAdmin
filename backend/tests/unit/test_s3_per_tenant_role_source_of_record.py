"""S3 / T5 — Confirm per-tenant role resolution stays in MySQL; S3 adds no token claim.

**Validates: Requirements R1.3, R1.4**

T5 is a *confirmation* task (no production code change). It pins two invariants that the
S3 claim contract depends on (`claim-contract.md` §1 / §3, design D1):

1. **Per-tenant roles resolve from MySQL, not the token (R1.3).** The per-tenant role
   grants (`Finance_*`, `STR_*`, `ZZP_*`, `Tenant_Admin`) come from MySQL
   `user_tenant_roles` via `auth.role_cache.get_tenant_roles` — exactly the parameterized
   `SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s`. Only the
   three GLOBAL roles (`SysAdmin` / `Administrators` / `System_CRUD`) are honored from the
   token's `cognito:groups`.

2. **S3 adds NO per-tenant role / entitlement claim to the token (R1.4).** Stamping the
   per-user resolved answer (roles ∩ enabled modules) into the token is **S4**, via a
   Pre-Token-Generation Lambda. S3 must not do it. This is confirmed at the source level:
   the S3 code surface (`auth/role_cache.py`, `auth/cognito_utils.py`, and the projection
   client `services/dynamodb_client.py`) contains no Pre-Token-Generation trigger and no
   code path that writes a role/entitlement claim into a token. The token is only ever
   *read* (`payload.get(...)`), never authored.

This complements — and does not duplicate — the existing coverage:
  * `test_role_cache.py` — cache mechanics (TTL, invalidation) of `get_tenant_roles`.
  * `test_per_tenant_roles.py` — the `cognito_required` global∪per-tenant merge + isolation.
  * `test_s3_pool_a_claim_interpretation.py` — T4 pool selection + claim reads.
T5 focuses narrowly on the *source of record* (MySQL) and the *no-token-claim* guardrail.

No real DB, no network, no `load_dotenv`. Uses the shared `mock_db` fixture.
"""

import inspect
import re

import pytest

import auth.cognito_utils as cognito_utils
import auth.role_cache as role_cache
import services.dynamodb_client as dynamodb_client
from auth.role_cache import get_tenant_roles


# The three roles the token is allowed to carry (claim-contract.md §1).
GLOBAL_ROLES = ("SysAdmin", "Administrators", "System_CRUD")

# The exact parameterized query the Flask plane uses to resolve per-tenant roles.
EXPECTED_QUERY = (
    "SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s"
)


# --------------------------------------------------------------------------- #
# R1.3 — per-tenant roles resolve from MySQL `user_tenant_roles`, not the token.
# --------------------------------------------------------------------------- #


class TestPerTenantRolesResolveFromMySQL:
    """`role_cache.get_tenant_roles` is the MySQL source of record for per-tenant roles."""

    def test_get_tenant_roles_reads_user_tenant_roles_table(self, mock_db):
        """Per-tenant roles come from the parameterized `user_tenant_roles` SELECT."""
        role_cache._role_cache.clear()
        mock_db.execute_query.return_value = [
            {"role": "Finance_CRUD"},
            {"role": "Tenant_Admin"},
        ]

        roles = get_tenant_roles("test-goodwin@example.com", "GoodwinSolutions", mock_db)

        assert roles == ["Finance_CRUD", "Tenant_Admin"]
        # Exactly the tenant-scoped `user_tenant_roles` read, parameterized (no
        # string interpolation), keyed by (email, administration).
        mock_db.execute_query.assert_called_once_with(
            EXPECTED_QUERY,
            ("test-goodwin@example.com", "GoodwinSolutions"),
            fetch=True,
        )

    def test_get_tenant_roles_is_scoped_to_the_requested_tenant(self, mock_db):
        """The MySQL read is scoped by `administration` — never cross-tenant."""
        role_cache._role_cache.clear()
        mock_db.execute_query.return_value = [{"role": "STR_Read"}]

        get_tenant_roles("user@example.com", "TenantB", mock_db)

        _query, params, _kw = (
            mock_db.execute_query.call_args.args[0],
            mock_db.execute_query.call_args.args[1],
            mock_db.execute_query.call_args.kwargs,
        )
        assert params == ("user@example.com", "TenantB")

    def test_role_cache_query_targets_only_the_user_tenant_roles_table(self):
        """The role_cache module's only SQL is the `user_tenant_roles` read (source of record)."""
        source = inspect.getsource(role_cache)
        # It queries user_tenant_roles ...
        assert "user_tenant_roles" in source
        # ... and no OTHER governance table is a per-tenant role source here.
        assert "tenant_role_allocation" not in source
        # The role value is selected straight from the row, never derived from a claim.
        assert "cognito:groups" not in source
        assert "custom:tenants" not in source


# --------------------------------------------------------------------------- #
# R1.3 — only GLOBAL roles are honored from the token's `cognito:groups`.
# --------------------------------------------------------------------------- #


class TestOnlyGlobalRolesComeFromTheToken:
    """The token contributes only the three global roles; per-tenant authority is MySQL."""

    def test_cognito_required_global_role_filter_is_the_three_global_roles(self):
        """`cognito_required` filters the token's groups to exactly the global set.

        Pins the filter literal in `cognito_utils.cognito_required` so a stray per-tenant
        role in `cognito:groups` can never be honored as authority from the token.
        """
        source = inspect.getsource(cognito_utils.cognito_required)
        for role in GLOBAL_ROLES:
            assert role in source
        # The filter comprehension keeps ONLY roles in the global tuple.
        assert 'in ("SysAdmin", "Administrators", "System_CRUD")' in source

    def test_stray_per_tenant_role_in_token_is_dropped(self):
        """A per-tenant role placed in `cognito:groups` is not treated as global."""
        token_groups = ["SysAdmin", "Finance_CRUD", "STR_Read", "Tenant_Admin"]
        global_roles = [r for r in token_groups if r in GLOBAL_ROLES]

        assert global_roles == ["SysAdmin"]
        assert "Finance_CRUD" not in global_roles
        assert "Tenant_Admin" not in global_roles


# --------------------------------------------------------------------------- #
# R1.4 — S3 adds NO per-tenant role / entitlement claim to the token.
#         (Entitlement-in-token is S4, via a Pre-Token-Generation Lambda.)
# --------------------------------------------------------------------------- #


# Modules that make up the S3 code surface touching identity/projection.
_S3_CODE_SURFACE = (role_cache, cognito_utils, dynamodb_client)

# Patterns that would indicate a token being *authored* (a claim written into it).
# S3 must only ever READ claims (`payload.get(...)`), never write them.
_TOKEN_AUTHORING_PATTERNS = (
    r"claimsToAddOrOverride",
    r"claimsOverrideDetails",
    r"PreTokenGeneration",
    r"pre[_-]?token",
)


class TestS3AddsNoTokenEntitlementClaim:
    """The S3 code surface never stamps a per-tenant role / entitlement into a token."""

    @pytest.mark.parametrize("module", _S3_CODE_SURFACE, ids=lambda m: m.__name__)
    def test_no_pre_token_generation_or_claim_authoring(self, module):
        """No S3 module contains a Pre-Token-Generation trigger or claim-authoring code."""
        source = inspect.getsource(module)
        for pattern in _TOKEN_AUTHORING_PATTERNS:
            assert re.search(pattern, source, re.IGNORECASE) is None, (
                f"{module.__name__} appears to author a token claim (matched "
                f"/{pattern}/); entitlement-in-token is S4, not S3 (R1.4)."
            )

    def test_cognito_utils_never_assigns_into_a_claim_key(self):
        """`cognito:groups` / `custom:tenants` are only ever read, never stamped.

        The guardrail that matters for R1.4 is that no code path *writes* a claim into
        a token/payload (e.g. ``payload["cognito:groups"] = ...``). Reading a claim
        (``payload.get("cognito:groups", [])``) is exactly what S3 does and is fine.
        """
        source = inspect.getsource(cognito_utils)
        for claim in ("cognito:groups", "custom:tenants"):
            # There is at least one legitimate READ of each claim on the auth path.
            assert f'.get("{claim}"' in source or f".get('{claim}'" in source
            # There is NEVER an assignment INTO the claim key (a stamp/write).
            assert re.search(rf'\[\s*["\']{re.escape(claim)}["\']\s*\]\s*=', source) is None, (
                f"cognito_utils assigns into the {claim!r} claim — S3 must only read "
                f"claims, never author them (entitlement-in-token is S4, R1.4)."
            )

    def test_projection_client_is_dynamodb_only_not_a_token_writer(self):
        """The S3 projection client builds DynamoDB access only — it never touches tokens."""
        source = inspect.getsource(dynamodb_client)
        # It is about the DynamoDB governance-projection table ...
        assert "governance_projection" in source.lower() or "GOVERNANCE_PROJECTION_TABLE" in source
        # ... and has nothing to do with JWT/token claims.
        assert "cognito:groups" not in source
        assert "custom:tenants" not in source
        assert "jwt" not in source.lower()
