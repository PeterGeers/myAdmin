"""
S5 Task 6.0 — the Members **parity / walkthrough harness** (design "Testing Strategy",
migration-plan Step 6, R7.1 / R7.2).

WHAT THIS IS (and is NOT)
-------------------------
This is a **hands-on walkthrough harness**, run in the test pool / locally — **NOT** a
live-traffic soak and **NOT** a production comparison against the existing h-dcn app.
h-dcn Members is demo-only (real data lives in a Google Sheet) and the existing h-dcn app
is a separate codebase that is not in this repo, so there is no live traffic to
parity-compare against. Instead the harness WALKS the migrated module end-to-end for the
pilot tenant ``h-dcn`` and asserts its behaviour matches h-dcn's **known behavioural
contract** — the contract that ``routes.py`` deliberately encodes (the route names mirror
h-dcn's ~18 handler behaviours "so parity is auditable at the Go/No-Go") plus the h-dcn
config/hooks/catalog that are already wired into the module **as data**.

It exercises the module over the SAME in-memory ``FakeDynamoTable`` +
``DynamoDbMembersRepository`` the repository/dispatch tests use, wired with h-dcn's
scope/lifecycle config, hook registry, and seeded catalog — so it touches **no** live AWS,
**no** Google, and has **no** dependency on the external h-dcn app. This is the
test-pool/local validation R7.1 mandates BEFORE any hands-on review (task 6.2).

THE FOUR PARITY DIMENSIONS (R7.1)
---------------------------------
The harness walks all four dimensions the requirement names and records an outcome per
check:

1. **authz** (incl. scope) — 401 unauthenticated, 403 unentitled, region-scoped callers
   see/act only within their region (Property 4), admin/``Regio_All`` tenant-wide, and
   verify-before-trust (no header/body tenant trust).
2. **data** — the fixed base ⊕ h-dcn overlay resolves, ``scope_values.region`` is present,
   the Lidmaatschap Beheer dropdown lists only ACTIVE types, and a backfilled member (via
   the 4.1 transform on a fixture row) round-trips through create → read.
3. **api_contract** — every one of h-dcn's ~18 handler behaviours has a corresponding route
   that answers with the expected shape/status; the harness emits a route-by-route parity
   checklist.
4. **workflow** — h-dcn's lifecycle (application → pending → active ⇄ suspended, → lapsed,
   → left) runs through the engine with h-dcn's declarative guards.

THE PARITY REPORT
-----------------
The harness builds a :class:`ParityReport` (a dataclass tree the tests assert on, and which
can be rendered to a human-readable walkthrough artifact for task 6.2's Go/No-Go, R8). Each
:class:`ParityCheck` records an ``hdcn_behaviour`` → ``migrated_route`` → ``observed``
outcome with an :class:`Outcome` of ``PASS`` / ``FAIL`` / ``MANUAL``. ``MANUAL`` flags a
behaviour that can only be confirmed by a human walkthrough (look & feel / UX) — the harness
records it as a checklist item rather than asserting it, because that UX review is task
6.2's hands-on part.

Nothing here changes production behaviour — the harness is test/tooling only, additive and
reversible, and the tenant-agnostic core is untouched (``h-dcn`` appears only as pilot test
data).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from sam.members.handler import app
from sam.members.handler.routes import ROUTES, RouteGroup, RouteSpec, route_names
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.migration.hdcn_backfill import MembershipTypeMapper, map_hdcn_row
from sam.members.migration.hdcn_catalog_seed import HDCN_MEMBERSHIP_TYPES
from sam.members.repository.members_repository import DynamoDbMembersRepository
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks

# The faithful in-memory DynamoDB fake (transactional conditional writes + atomic counter)
# already used by the repository + dispatch tests. Reused here so the walkthrough runs over
# the same storage semantics as production without any live AWS.
from sam.tests.test_members_repository import FakeDynamoTable

#: The pilot tenant the whole walkthrough runs for. ``h-dcn`` is pilot test DATA — it never
#: becomes an ``if tenant == ...`` in the module core; the harness simply exercises the
#: first (and only, for the pilot) tenant the wired config/hooks/catalog know about.
PILOT_TENANT = "h-dcn"

#: A representative pilot region (one of h-dcn's declared region scope values).
PILOT_REGION = "Noord"


# ── The parity-report data structures (the harness emits + asserts on these) ──────────


class Dimension(str, Enum):
    """The four R7.1 parity dimensions the walkthrough covers."""

    AUTHZ = "authz"
    DATA = "data"
    API_CONTRACT = "api_contract"
    WORKFLOW = "workflow"


class Outcome(str, Enum):
    """The outcome of one parity check.

    ``PASS`` / ``FAIL`` are asserted automatically by the harness. ``MANUAL`` marks a
    behaviour that can only be confirmed by a human walkthrough (look & feel / UX) — the
    harness records it as a checklist item for task 6.2's hands-on review and does NOT
    assert on it (per the task's constraint: keep automated assertions to behaviour the
    module actually implements).
    """

    PASS = "pass"
    FAIL = "fail"
    MANUAL = "manual"


@dataclass(frozen=True)
class ParityCheck:
    """One route-by-route / behaviour-by-behaviour parity observation.

    Maps an h-dcn behaviour → the migrated route that answers it → the observed outcome,
    so the report reads as an auditable checklist at the Go/No-Go (R7.2 → R8).

    Attributes:
        dimension: Which of the four R7.1 dimensions this check belongs to.
        hdcn_behaviour: The h-dcn behaviour under test (mirrors an h-dcn handler behaviour,
            or a named authz/data/workflow behaviour).
        migrated_route: The migrated module's route name that answers it (``None`` for a
            behaviour with no single owning route, e.g. a cross-cutting authz property).
        outcome: PASS / FAIL / MANUAL.
        observed: A short human-readable note on what was observed (status codes, ids, etc.).
    """

    dimension: Dimension
    hdcn_behaviour: str
    migrated_route: Optional[str]
    outcome: Outcome
    observed: str

    @property
    def asserted(self) -> bool:
        """Whether this check is an automated assertion (PASS/FAIL) vs. a MANUAL flag."""
        return self.outcome is not Outcome.MANUAL


@dataclass
class ParityReport:
    """The walkthrough evidence the harness builds (R7.2) — a checklist feeding R8's Go/No-Go.

    A pure in-memory structure the tests assert on and which :meth:`render` turns into a
    human-readable walkthrough artifact for the hands-on review (task 6.2).
    """

    tenant_id: str
    region: str
    checks: List[ParityCheck] = field(default_factory=list)

    # -- recording --------------------------------------------------------------------
    def record(
        self,
        dimension: Dimension,
        hdcn_behaviour: str,
        migrated_route: Optional[str],
        outcome: Outcome,
        observed: str,
    ) -> ParityCheck:
        check = ParityCheck(dimension, hdcn_behaviour, migrated_route, outcome, observed)
        self.checks.append(check)
        return check

    # -- queries ----------------------------------------------------------------------
    def by_dimension(self, dimension: Dimension) -> List[ParityCheck]:
        return [c for c in self.checks if c.dimension is dimension]

    def failures(self) -> List[ParityCheck]:
        return [c for c in self.checks if c.outcome is Outcome.FAIL]

    def manual_items(self) -> List[ParityCheck]:
        return [c for c in self.checks if c.outcome is Outcome.MANUAL]

    def asserted_checks(self) -> List[ParityCheck]:
        return [c for c in self.checks if c.asserted]

    def routes_covered(self) -> set:
        """The set of migrated route names any check in the report touched."""
        return {c.migrated_route for c in self.checks if c.migrated_route}

    @property
    def all_passed(self) -> bool:
        """True when every ASSERTED check passed (MANUAL items are not assertions)."""
        return all(c.outcome is Outcome.PASS for c in self.asserted_checks())

    def summary(self) -> Dict[str, int]:
        counts = {o.value: 0 for o in Outcome}
        for c in self.checks:
            counts[c.outcome.value] += 1
        return counts

    # -- rendering (the human-readable walkthrough artifact for task 6.2) -------------
    def render(self) -> str:
        """Render the report as a plain-text walkthrough artifact (Go/No-Go evidence)."""
        lines: List[str] = []
        lines.append("=" * 78)
        lines.append(
            f"Members parity/walkthrough report — tenant={self.tenant_id!r} "
            f"region={self.region!r}"
        )
        lines.append("(test-pool/local walkthrough — NOT a live-traffic soak)")
        lines.append("=" * 78)
        summary = self.summary()
        lines.append(
            f"checks: {len(self.checks)}  "
            f"pass={summary['pass']}  fail={summary['fail']}  manual={summary['manual']}"
        )
        for dimension in Dimension:
            dim_checks = self.by_dimension(dimension)
            lines.append("")
            lines.append(f"── {dimension.value} ({len(dim_checks)} checks) " + "─" * 30)
            for c in dim_checks:
                mark = {"pass": "PASS", "fail": "FAIL", "manual": "MANUAL"}[c.outcome.value]
                route = c.migrated_route or "-"
                lines.append(f"  [{mark:6}] {c.hdcn_behaviour} → {route}")
                lines.append(f"           {c.observed}")
        lines.append("=" * 78)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-friendly view (for writing the artifact to disk if desired)."""
        return {
            "tenant_id": self.tenant_id,
            "region": self.region,
            "summary": self.summary(),
            "checks": [
                {
                    "dimension": c.dimension.value,
                    "hdcn_behaviour": c.hdcn_behaviour,
                    "migrated_route": c.migrated_route,
                    "outcome": c.outcome.value,
                    "observed": c.observed,
                }
                for c in self.checks
            ],
        }


# ── The harness: wire the module like production, then walk it ────────────────────────


def _entitlement(tenant: str, capabilities: Sequence[str]) -> str:
    """Encode a verified entitlement claim (the shape the auth toolkit reads)."""
    return json.dumps({"v": 1, "t": {tenant: list(capabilities)}})


#: The admin capability set a Regio_All caller carries for the walkthrough.
_ADMIN_CAPS = ("members:read", "members:write", "members:admin", "members:export")


class MembersParityHarness:
    """Wires the migrated Members module exactly as production does and walks it end-to-end.

    Construction builds a :class:`MembershipService` over a real
    :class:`DynamoDbMembersRepository` backed by the in-memory :class:`FakeDynamoTable`,
    with h-dcn's lifecycle config + hook registry — the same wiring
    ``app._get_membership_service`` performs — and seeds the h-dcn Lidmaatschap Beheer
    catalog (task 4.2 data) so ``membership_type`` references resolve. The harness then
    drives the module through its HTTP edge (:func:`app.handler`) with verified
    API-GW-authorizer claims, exactly as the dispatch tests do.

    Use it as a context manager (or call :meth:`install` / :meth:`uninstall`) so the injected
    service is torn down cleanly and the module's global service is restored.
    """

    def __init__(self, tenant_id: str = PILOT_TENANT, region: str = PILOT_REGION):
        self.tenant_id = tenant_id
        self.region = region
        self.table = FakeDynamoTable()
        self.repo = DynamoDbMembersRepository(
            table=self.table, client=self.table.meta.client
        )
        self.hooks: TenantHookRegistry = register_hdcn_hooks(TenantHookRegistry())
        self.service = MembershipService(
            self.repo,
            lifecycle_provider=StaticLifecycleConfigProvider(
                {tenant_id: HDCN_LIFECYCLE_CONFIG}
            ),
            tenant_hooks=self.hooks,
        )
        self._seed_catalog()
        self._original_service_getter: Optional[Callable[[], MembershipService]] = None

    # -- lifecycle --------------------------------------------------------------------
    def _seed_catalog(self) -> None:
        """Seed the h-dcn catalog as DATA (task 4.2) so member type references resolve."""
        for entry in HDCN_MEMBERSHIP_TYPES:
            self.repo.save_membership_type(self.tenant_id, entry)

    def install(self) -> "MembersParityHarness":
        """Point the module edge at this harness's wired service (like the dispatch tests).

        Access is gated the normal SaaS way — capability (token) + scope grant (projection);
        there is no pilot-routing gate to install. The service getter is restored in
        :meth:`uninstall` so the harness leaves no global state behind.
        """
        self._original_service_getter = app._get_membership_service
        app._get_membership_service = lambda: self.service  # type: ignore[assignment]
        return self

    def uninstall(self) -> None:
        """Restore the module's original service getter."""
        if self._original_service_getter is not None:
            app._get_membership_service = self._original_service_getter  # type: ignore[assignment]
            self._original_service_getter = None

    def __enter__(self) -> "MembersParityHarness":
        return self.install()

    def __exit__(self, *exc: Any) -> None:
        self.uninstall()

    # -- request driving --------------------------------------------------------------
    def event(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        capabilities: Sequence[str] = _ADMIN_CAPS,
        groups: Sequence[str] = ("Regio_All",),
        sub: str = "admin-sub",
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        tenant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build an API Gateway proxy event with verified authorizer claims.

        ``authenticated=False`` omits the authorizer context entirely, so the edge sees no
        verified token and answers 401 — the unauthenticated walkthrough path.
        """
        request_context: Dict[str, Any] = {}
        if authenticated:
            request_context = {
                "authorizer": {
                    "claims": {
                        "sub": sub,
                        "cognito:groups": list(groups),
                        "custom:entitlements": _entitlement(
                            tenant or self.tenant_id, list(capabilities)
                        ),
                    }
                }
            }
        return {
            "httpMethod": method,
            "path": path,
            "headers": {},
            "queryStringParameters": dict(query) if query else None,
            "body": json.dumps(body) if body is not None else None,
            "requestContext": request_context,
        }

    def call(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        """Drive one request through the module edge and return the proxy response dict."""
        return app.handler(self.event(method, path, **kwargs))

    @staticmethod
    def data(resp: Mapping[str, Any]) -> Any:
        """Extract the ``data`` payload from a 200 response body."""
        return json.loads(resp["body"]).get("data")

    # -- member fixtures --------------------------------------------------------------
    def valid_member_body(
        self,
        member_id: str,
        *,
        region: Optional[str] = None,
        member_number: Optional[str] = None,
        status: Optional[str] = None,
        membership_type: str = "erelid",
    ) -> Dict[str, Any]:
        """A well-formed create body for the pilot tenant (mirrors the dispatch-test shape)."""
        membership: Dict[str, Any] = {
            "membership_type": membership_type,
            "joined": "2024-01-01",
        }
        if member_number is not None:
            membership["member_number"] = member_number
        if status is not None:
            membership["status"] = status
        return {
            "member_id": member_id,
            "personal": {"name": "Alex", "contact": "alex@example.com"},
            "membership": membership,
            "scope_values": {"region": [region or self.region]},
        }

    # ── Dimension 1: authz (incl. scope) ──────────────────────────────────────────────
    def walk_authz(self, report: ParityReport) -> None:
        """Walk the authz contract: 401 / 403 / scope narrowing / verify-before-trust.

        Mirrors h-dcn's access model: an unauthenticated caller is rejected (401), an
        authenticated-but-unentitled caller is forbidden (403), a region-scoped caller
        sees/acts only within their region (Property 4), an admin/``Regio_All`` caller is
        tenant-wide, and the tenant is derived from the verified token — a client-supplied
        body ``tenant_id`` can never redirect a write (verify-before-trust).
        """
        d = Dimension.AUTHZ

        # Unauthenticated → 401 (no verified token at the edge).
        resp = self.call("GET", "/members", authenticated=False)
        report.record(
            d, "reject unauthenticated caller", "list_members",
            Outcome.PASS if resp["statusCode"] == 401 else Outcome.FAIL,
            f"GET /members unauthenticated → {resp['statusCode']} (expected 401)",
        )

        # Authenticated but WITHOUT the required capability → 403.
        resp = self.call("GET", "/members", capabilities=("members:export",))
        report.record(
            d, "forbid caller lacking members:read", "list_members",
            Outcome.PASS if resp["statusCode"] == 403 else Outcome.FAIL,
            f"GET /members without members:read → {resp['statusCode']} (expected 403)",
        )

        # Seed one member per region as admin, then check scope narrowing on reads.
        self.call("POST", "/members", body=self.valid_member_body(
            "AUTHZ-N", region="Noord", member_number="A-1001"))
        self.call("POST", "/members", body=self.valid_member_body(
            "AUTHZ-Z", region="Zuid", member_number="A-1002"))

        # Admin / Regio_All → tenant-wide (sees both regions).
        resp = self.call("GET", "/members", groups=("Regio_All",))
        ids = sorted(m["member_id"] for m in self.data(resp)) if resp["statusCode"] == 200 else []
        report.record(
            d, "admin/Regio_All sees tenant-wide", "list_members",
            Outcome.PASS if resp["statusCode"] == 200 and ids == ["AUTHZ-N", "AUTHZ-Z"]
            else Outcome.FAIL,
            f"Regio_All GET /members → {resp['statusCode']} ids={ids} (expected both)",
        )

        # Region-scoped caller (Regio_Noord) → only their region's member (Property 4).
        resp = self.call("GET", "/members", groups=("Regio_Noord",))
        ids = [m["member_id"] for m in self.data(resp)] if resp["statusCode"] == 200 else []
        report.record(
            d, "region-scoped caller sees only their region", "list_members",
            Outcome.PASS if resp["statusCode"] == 200 and ids == ["AUTHZ-N"] else Outcome.FAIL,
            f"Regio_Noord GET /members → {resp['statusCode']} ids={ids} (expected [AUTHZ-N])",
        )

        # A scoped caller reading an out-of-scope member → 404 (no existence leak).
        resp = self.call("GET", "/members/AUTHZ-Z", groups=("Regio_Noord",))
        report.record(
            d, "out-of-scope read is indistinguishable 404", "get_member",
            Outcome.PASS if resp["statusCode"] == 404 else Outcome.FAIL,
            f"Regio_Noord GET /members/AUTHZ-Z → {resp['statusCode']} (expected 404)",
        )

        # A scoped caller WRITING out of scope → 403 (Property 4 — honest denial on write).
        resp = self.call(
            "PUT", "/members/AUTHZ-Z", groups=("Regio_Noord",),
            body={"personal": {"name": "Nope"}},
        )
        report.record(
            d, "region-scoped caller cannot write out of region", "update_member",
            Outcome.PASS if resp["statusCode"] == 403 else Outcome.FAIL,
            f"Regio_Noord PUT /members/AUTHZ-Z → {resp['statusCode']} (expected 403)",
        )

        # Verify-before-trust: a body tenant_id can never redirect the write.
        body = self.valid_member_body("AUTHZ-VBT", region="Noord", member_number="A-1003")
        body["tenant_id"] = "evil-tenant"
        resp = self.call("POST", "/members", body=body)
        redirected = self.repo.get_member("evil-tenant", "AUTHZ-VBT")
        landed = self.repo.get_member(self.tenant_id, "AUTHZ-VBT")
        report.record(
            d, "verify-before-trust: body tenant_id ignored", "create_member",
            Outcome.PASS if resp["statusCode"] == 200 and redirected is None
            and landed is not None else Outcome.FAIL,
            "POST /members with body tenant_id='evil-tenant' persisted under verified "
            f"tenant only (evil={redirected is None}, pilot={landed is not None})",
        )

    # ── Dimension 2: data ──────────────────────────────────────────────────────────────
    def walk_data(self, report: ParityReport) -> None:
        """Walk the data contract: resolved field config, scope_values, active-only dropdown,
        and a backfilled member (4.1 transform) round-trip through create → read.
        """
        d = Dimension.DATA

        # The resolved field config (fixed base ⊕ h-dcn overlay) is served.
        resp = self.call("GET", "/members/field-config")
        cfg = self.data(resp) if resp["statusCode"] == 200 else {}
        field_names = {f.get("key") or f.get("name") for f in cfg.get("fields", [])}
        has_personal_and_membership = bool(cfg.get("by_group", {}).get("personal")) and \
            bool(cfg.get("by_group", {}).get("membership"))
        report.record(
            d, "fixed base ⊕ overlay field config resolves", "get_field_config",
            Outcome.PASS if resp["statusCode"] == 200 and has_personal_and_membership
            else Outcome.FAIL,
            f"GET /members/field-config → {resp['statusCode']}, "
            f"{len(field_names)} fields, groups={sorted(cfg.get('by_group', {}))}",
        )

        # The Lidmaatschap Beheer dropdown lists ONLY active types. Retire one, confirm it
        # drops out of the options while remaining visible in the management list.
        self.call("POST", "/membership-types", body={
            "type_code": "temp_retired", "label": {"nl": "Tijdelijk", "en": "Temp"},
            "active": True, "order": 99,
        })
        self.call("DELETE", "/membership-types/temp_retired")  # soft-delete (active=false)
        resp = self.call("GET", "/members/field-config")
        options = self.data(resp).get("membership_type_options", []) if resp["statusCode"] == 200 else []
        option_codes = {o.get("value") for o in options}
        report.record(
            d, "dropdown lists only ACTIVE membership types", "get_field_config",
            Outcome.PASS if "temp_retired" not in option_codes and "erelid" in option_codes
            else Outcome.FAIL,
            f"active options={sorted(option_codes)} (retired 'temp_retired' excluded)",
        )

        # The management catalog list DOES show the retired entry (soft-delete, not gone).
        resp = self.call("GET", "/membership-types")
        all_codes = {e.get("type_code") for e in self.data(resp)} if resp["statusCode"] == 200 else set()
        report.record(
            d, "management catalog shows retired (soft-deleted) types", "list_membership_types",
            Outcome.PASS if "temp_retired" in all_codes else Outcome.FAIL,
            f"GET /membership-types (all) codes include retired: {'temp_retired' in all_codes}",
        )

        # A backfilled member (4.1 transform on a fixture row) round-trips create → read.
        raw_row = {
            "member_id": "BACKFILL-1",
            "naam": "Backfilled Bram",
            "email": "bram@example.com",
            "lidnummer": "L-9001",
            "status": "actief",
            "lidmaatschapstype": "Erelid",
            "ingangsdatum": "2024-01-01",  # → membership.joined (a required fixed field)
            "regio": "noord",
            "motor": "BMW R80",  # a club/Motor detail → variable overlay
        }
        record = map_hdcn_row(raw_row, type_mapper=MembershipTypeMapper(), tenant_id=self.tenant_id)
        region_seeded = record.get("scope_values", {}).get("region") == ["Noord"]
        # The transform maps 'actief'→'active'; create it (needs a motor for the active hook —
        # the fixture carries one in overlay).
        create = self.call("POST", "/members", body=record)
        read = self.call("GET", "/members/BACKFILL-1", groups=("Regio_Noord",))
        read_data = self.data(read) if read["statusCode"] == 200 else {}
        round_tripped = (
            create["statusCode"] == 200
            and read["statusCode"] == 200
            and read_data.get("membership", {}).get("member_number") == "L-9001"
            and read_data.get("membership", {}).get("membership_type") == "erelid"
        )
        report.record(
            d, "backfilled member (4.1 transform) round-trips create→read", "create_member",
            Outcome.PASS if round_tripped else Outcome.FAIL,
            f"map_hdcn_row→POST /members→GET: create={create['statusCode']} "
            f"read={read['statusCode']} number={read_data.get('membership', {}).get('member_number')}",
        )

        # scope_values.region is present + canonicalized on the stored record.
        report.record(
            d, "scope_values.region present + canonicalized", "create_member",
            Outcome.PASS if region_seeded and read_data.get("scope_values", {}).get("region") == ["Noord"]
            else Outcome.FAIL,
            f"stored scope_values.region={read_data.get('scope_values', {}).get('region')} "
            f"(transform canonicalized 'noord'→'Noord': {region_seeded})",
        )

    # ── Dimension 3: api contract (route-by-route parity checklist) ─────────────────────
    def walk_api_contract(self, report: ParityReport) -> None:
        """Walk EVERY declared route group and confirm the migrated module answers.

        The route map is the union of h-dcn's ~18 handler behaviours + the new catalog group
        (design C8). For each route the harness sends a representative request and records
        whether the module answered with an expected status (never 404 "no such route" and
        never 501 "not built"). Some behaviours (bulk transition edge cases, invitation
        delivery UX) are asserted at the "route answers" level and flagged MANUAL for the
        deeper hands-on review.
        """
        d = Dimension.API_CONTRACT

        # Seed a member + membership + payment + delegate so read/lifecycle routes have data.
        self.call("POST", "/members", body=self.valid_member_body(
            "API-1", region=self.region, member_number="C-1001", status="pending"))
        self.call("POST", "/members/API-1/memberships", body={
            "membership_id": "MS-1", "status": "pending"})
        # Payments are a READ-only surface in the migrated module (no write route creates
        # them), so get_member_payments answers 200 with whatever the repository holds
        # (an empty list for the pilot) — the parity point is that the route ANSWERS.

        # Each entry: (route_name, method, path, body, query, expected_ok_statuses, note)
        # expected statuses are the "route answered as designed" set — importantly NOT
        # {404 no-route, 501 not-implemented}. Where a request is intentionally minimal we
        # accept the module's honest client-error answer (e.g. 422/409) as "route answered".
        checks: List[tuple] = [
            # ── Member CRUD (8 h-dcn behaviours) ──
            ("create_member", "POST", "/members",
             self.valid_member_body("API-NEW", member_number="C-2001"), None, {200}, {},
             "create a member"),
            ("list_members", "GET", "/members", None, None, {200}, {}, "list members"),
            ("list_members_filtered", "POST", "/members/search",
             {"status": "active"}, None, {200}, {}, "server-side filtered list"),
            ("export_members", "GET", "/members/export", None, None, {200}, {}, "export members"),
            ("get_self", "GET", "/members/me", None, None, {200, 404}, {"sub": "admin-sub"},
             "own record (404 if the caller has no member record)"),
            ("get_field_config", "GET", "/members/field-config", None, None, {200}, {},
             "resolved field config + dropdown options"),
            ("get_member", "GET", "/members/API-1", None, None, {200}, {}, "get one member"),
            ("update_member", "PUT", "/members/API-1",
             {"personal": {"name": "Renamed"}}, None, {200}, {}, "update a member"),
            ("delete_member", "DELETE", "/members/API-NEW", None, None, {200}, {},
             "delete a member"),
            # ── Membership lifecycle (7 h-dcn behaviours) ──
            ("create_membership", "POST", "/members/API-1/memberships",
             {"membership_id": "MS-2", "status": "pending"}, None, {200}, {},
             "create a membership"),
            ("list_memberships", "GET", "/members/API-1/memberships", None, None, {200}, {},
             "list memberships"),
            ("get_membership", "GET", "/members/API-1/memberships/MS-1", None, None, {200}, {},
             "get one membership"),
            ("update_membership", "PUT", "/members/API-1/memberships/MS-1",
             {"status": "suspended"}, None, {200}, {}, "update a membership"),
            ("transition_membership", "POST",
             "/members/API-1/memberships/MS-1/transition",
             {"to_state": "active"}, None, {200, 409}, {},
             "apply a guarded lifecycle transition"),
            ("delete_membership", "DELETE", "/members/API-1/memberships/MS-2", None, None,
             {200}, {}, "delete a membership"),
            ("bulk_transition_memberships", "POST", "/memberships/transition",
             {"to_state": "left", "member_ids": ["API-1"]}, None, {200}, {},
             "bulk lifecycle transition"),
            # ── Delegates (2 h-dcn behaviours) ──
            ("manage_delegates", "PUT", "/members/API-1/delegates",
             {"delegates": [{"email": "d@x.com"}]}, None, {200}, {}, "manage delegates"),
            ("send_delegate_invitation", "POST", "/members/API-1/delegates/invitations",
             {"delegate_email": "invite@x.com"}, None, {200}, {}, "send delegate invitation"),
            # ── Payments — member-scoped (1 h-dcn behaviour) ──
            ("get_member_payments", "GET", "/members/API-1/payments", None, None, {200}, {},
             "get member payments"),
            # ── Lidmaatschap Beheer catalog (new, design C8) ──
            ("list_membership_types", "GET", "/membership-types", None, None, {200}, {},
             "list catalog (management)"),
            ("get_membership_type", "GET", "/membership-types/erelid", None, None, {200}, {},
             "get one catalog entry"),
            ("create_membership_type", "POST", "/membership-types",
             {"type_code": "new_type", "label": {"nl": "Nieuw", "en": "New"}, "order": 50},
             None, {200}, {}, "create catalog entry"),
            ("update_membership_type", "PUT", "/membership-types/new_type",
             {"label": {"nl": "Nieuw2", "en": "New2"}, "order": 51}, None, {200}, {},
             "update catalog entry"),
            ("deactivate_membership_type", "DELETE", "/membership-types/new_type", None, None,
             {200}, {}, "soft-delete (retire) catalog entry"),
        ]

        for name, method, path, body, _q, expected, extra_kwargs, note in checks:
            resp = self.call(method, path, body=body, **extra_kwargs)
            status = resp["statusCode"]
            # A route "answered as designed" when the status is in the expected set and is
            # neither a routing miss (404 where a route should exist) nor a 501 stub.
            answered = status in expected and status != 501
            report.record(
                d, note, name,
                Outcome.PASS if answered else Outcome.FAIL,
                f"{method} {path} → {status} (expected one of {sorted(expected)})",
            )

        # Verify the checklist covered every declared route exactly once — the report is the
        # union of h-dcn's behaviours, so a missing route is a parity gap.
        declared = set(route_names())
        covered = {c.migrated_route for c in report.by_dimension(d)}
        missing = declared - covered
        report.record(
            d, "every declared route is exercised", None,
            Outcome.PASS if not missing else Outcome.FAIL,
            f"{len(covered)}/{len(declared)} routes exercised; missing={sorted(missing)}",
        )

        # Look & feel / UX parity (the frontend renders the same, invitation email delivery,
        # export file formatting) can only be confirmed by a human walkthrough — flagged for
        # task 6.2's hands-on review, not asserted here.
        report.record(
            d, "frontend look & feel / UX parity", None, Outcome.MANUAL,
            "requires hands-on review (task 6.2): the module serves the contract; the "
            "presentation-only frontend rendering is confirmed by a human walkthrough",
        )

    # ── Dimension 4: workflow (lifecycle end-to-end through the engine) ─────────────────
    def walk_workflow(self, report: ParityReport) -> None:
        """Walk a representative member through h-dcn's full lifecycle via the engine.

        application → pending (approval flag) → active (member-number + contact guards) →
        suspended → active → lapsed → left, with the declarative guards enforced (a guard
        that fails denies the move with a 409 and does not mutate the record).
        """
        d = Dimension.WORKFLOW
        mid = "WF-1"
        # Start at application (initial state) with the fields activation will require, plus
        # a motor so the active-state validate_member hook passes.
        body = self.valid_member_body(mid, region=self.region, member_number="W-1001",
                                       status="application")
        body["overlay"] = {"motor": "Honda CB500"}
        self.call("POST", "/members", body=body)

        def transition(to_state: str, context: Optional[Mapping[str, Any]] = None) -> int:
            payload: Dict[str, Any] = {"to_state": to_state}
            if context is not None:
                payload["context"] = dict(context)
            resp = self.call("POST", f"/members/{mid}/memberships/MS-1/transition", body=payload)
            return resp["statusCode"]

        def current_status() -> Optional[str]:
            m = self.repo.get_member(self.tenant_id, mid)
            return (m or {}).get("membership", {}).get("status")

        # A denied transition first: application→pending WITHOUT the approval flag → 409, and
        # the state is not mutated (guard enforced).
        denied = transition("pending")  # no context.approved
        report.record(
            d, "application→pending denied without approval flag", "transition_membership",
            Outcome.PASS if denied == 409 and current_status() == "application" else Outcome.FAIL,
            f"pending (unapproved) → {denied} (expected 409), state still {current_status()!r}",
        )

        # The happy path, step by step.
        steps = [
            ("application→pending (approved)", "pending", {"approved": True}, "pending"),
            ("pending→active (guards pass)", "active", None, "active"),
            ("active→suspended", "suspended", None, "suspended"),
            ("suspended→active", "active", None, "active"),
            ("active→lapsed", "lapsed", None, "lapsed"),
            ("lapsed→left (terminal)", "left", None, "left"),
        ]
        for label, to_state, ctx, expected_state in steps:
            code = transition(to_state, ctx)
            ok = code == 200 and current_status() == expected_state
            report.record(
                d, label, "transition_membership",
                Outcome.PASS if ok else Outcome.FAIL,
                f"{label} → {code} (expected 200), state now {current_status()!r}",
            )

        # An undeclared edge (application→active directly) is denied — proven on a fresh member.
        body2 = self.valid_member_body("WF-2", member_number="W-1002", status="application")
        self.call("POST", "/members", body=body2)
        resp = self.call("POST", "/members/WF-2/memberships/MS-1/transition",
                         body={"to_state": "active"})
        report.record(
            d, "undeclared transition edge is denied", "transition_membership",
            Outcome.PASS if resp["statusCode"] == 409 else Outcome.FAIL,
            f"application→active (undeclared) → {resp['statusCode']} (expected 409)",
        )

    # ── Orchestration ──────────────────────────────────────────────────────────────────
    def run(self) -> ParityReport:
        """Walk all four R7.1 dimensions and return the assembled parity report.

        Installs the wired service for the duration of the walk (context-managed) so the
        module edge dispatches into the harness's in-memory service + repository. Each
        dimension walker appends its route-by-route / behaviour-by-behaviour checks.
        """
        report = ParityReport(tenant_id=self.tenant_id, region=self.region)
        with self:
            self.walk_authz(report)
            self.walk_data(report)
            self.walk_api_contract(report)
            self.walk_workflow(report)
        return report


def run_parity_walkthrough(
    tenant_id: str = PILOT_TENANT, region: str = PILOT_REGION
) -> ParityReport:
    """Build + run the parity walkthrough for the pilot tenant/region and return the report.

    The single entry point a runnable script or a test can call. Constructs a fresh
    :class:`MembersParityHarness` (in-memory, no live AWS/Google/h-dcn-app) and walks all
    four dimensions.
    """
    return MembersParityHarness(tenant_id=tenant_id, region=region).run()
