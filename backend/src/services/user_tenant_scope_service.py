"""
UserTenantScopeService — read/write a member-user's scope grant (s5d task 5.1).

This is the Flask/MySQL-plane SERVICE layer for the ``user_tenant_scope`` table
(migration ``20260820120000_create_user_tenant_scope_table``). It is the single
seam the Tenant-Admin scope-authoring ROUTES (task 5.2, ``tenant_admin_scope.py``)
call to GET / SET / clear a user's scope grant for a ``(email, administration,
module)`` — and it is deliberately the ONLY thing this class does.

What it does (design → Data Models ``user_tenant_scope`` · API scope authoring ·
Error Handling · Properties 1/2/5):

- **GET** (:meth:`get_scope`) — return the user's current ``scopes`` JSON for the
  current tenant + module, or an empty dict ``{}`` when no row exists (R1.1).
- **SET** (:meth:`set_scope`) — an ATOMIC OVERWRITE (R4.5) of the ``(email,
  administration, module)`` row's ``scopes`` JSON: the save reflects EXACTLY what
  was passed (upsert). Clearing all selections (an empty/no-grant scopes object)
  DELETES the row (deny-by-default downstream, R4.5) rather than storing ``{}``.
- **VALIDATE** — before writing, every dimension key must exist in the tenant's
  ``members.scope_dimensions`` parameter, and every granted value must be one of
  that dimension's canonical ``values`` — compared via the shared ``scope_canon``
  by canonical-equality (R4.2, R9.6). The all-access sentinel ``["*"]`` is valid
  for any enabled dimension. An unknown dimension or unknown value raises
  :class:`ScopeValidationError` (the route maps it to 400) and NOTHING is written
  (atomic — design Error Handling). A validated value is stored as its CANONICAL
  declared spelling so member data and grant share one vocabulary.
- **AXIS INDEPENDENCE (R1.3, Property 5)** — this service NEVER reads or writes
  ``user_tenant_roles``. Capability (roles), governance (Tenant_Admin) and scope
  (this table) are orthogonal; a scope write touches only ``user_tenant_scope``.
- **PROJECTION TRIGGER (R2.4, Property 2)** — after a committed write/delete it
  fires ``enqueue_sync(tenant)`` so the ``scopegrant#…`` projection reflects the
  change. Best-effort/logged (same contract as role writes in
  ``tenant_admin_roles.py`` / ``projection_sync_trigger.enqueue_sync``): a failure
  is swallowed and NEVER breaks the write.

Steering 31 (database patterns): all DB access goes through ``DatabaseManager``
with parameterized ``%s`` placeholders; every query is tenant-isolated on
``administration`` (which flows in from the verified tenant — never a body value,
never a hardcoded default); the ``scopes`` JSON column is stored via ``json.dumps``
and read via ``json.loads`` (mirroring ``parameter_service.py``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from services.scope_canon import scope_canon

logger = logging.getLogger(__name__)

# The MODULE-namespaced parameter that is the SOURCE OF TRUTH for which member
# field each scope dimension binds to and its canonical ``values`` (design D4/R5.1).
# These mirror the constants ``projection_sync.build_scopegrant_rows`` reads, so
# authoring validation and the projection builder agree byte-for-byte.
_MEMBERS_PARAM_NAMESPACE = "members"
_SCOPE_DIMENSIONS_PARAM_KEY = "scope_dimensions"

#: The all-access sentinel grant for a dimension (design → ``scopes`` JSON shape).
WILDCARD_VALUE = "*"


class ScopeValidationError(ValueError):
    """A scope grant references an unknown dimension or an unknown value (R4.2).

    Raised by :meth:`UserTenantScopeService.set_scope` BEFORE any write, so the
    PUT is atomic (nothing is written on a bad grant — design Error Handling). The
    route (task 5.2) maps this to a 400.
    """


class ScopeReconciliationBlocked(ValueError):
    """A proposed scope-dimension change would ORPHAN one or more existing grants (R23).

    The ORPHANING tier of the two-tier reconciliation (OQ-7): a rename/remove of a dimension
    or the removal of a granted value would strand an existing ``user_tenant_scope`` grant
    (leave it referencing a dimension/value that no longer exists). The change is REFUSED (not
    applied); the frontend shows a contact-SysAdmin interim message (the structural fix, Option
    D, is out of scope). Carries the orphaned references so the UI can name them.

    Attributes:
        orphaned: a list of ``{"email", "dimension", "values"}`` describing each grant that the
            proposed change would strand (the values no longer declared, or ``["*"]`` when the
            whole dimension would be removed/renamed).
    """

    def __init__(self, message: str, orphaned: list[dict[str, Any]]):
        super().__init__(message)
        self.orphaned = orphaned


class UserTenantScopeService:
    """Read/write a member-user's scope grant in ``user_tenant_scope`` (R1.1).

    Depends only on a ``DatabaseManager`` (parameterized MySQL access) and a
    ``ParameterService`` (read-only, for the ``members.scope_dimensions`` value
    list used at validation). The projection trigger is injected as a callable so
    tests can assert it fired without touching AWS/MySQL; it defaults to the
    process-wide ``projection_sync_trigger.enqueue_sync``.

    Args:
        db: A ``DatabaseManager`` (or anything exposing ``execute_query``).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.
        enqueue_sync: The best-effort projection-sync trigger, called with the
            affected ``administration`` AFTER a committed write/delete. Defaults to
            ``services.projection_sync_trigger.enqueue_sync``; injectable for tests.
    """

    def __init__(
        self,
        db: Any,
        parameter_service: Any,
        enqueue_sync: Any = None,
    ) -> None:
        self.db = db
        self.parameter_service = parameter_service
        if enqueue_sync is None:
            from services.projection_sync_trigger import enqueue_sync as _default

            enqueue_sync = _default
        self._enqueue_sync = enqueue_sync

    # -- read ----------------------------------------------------------------

    def get_scope(self, email: str, administration: str, module: str) -> dict[str, Any]:
        """Return the user's ``scopes`` for ``(email, administration, module)``.

        Returns an empty dict ``{}`` when no row exists (absent record = no grant,
        R1.1/R1.5). A row whose stored ``scopes`` JSON is malformed also collapses
        to ``{}`` (defensive; never raises on read).

        Args:
            email: The target member-user's email (the row key, per-user).
            administration: The verified tenant (tenant isolation — steering 31).
            module: The owning module (``MEMBERS`` for s5d).
        """
        self._require_tenant(administration)
        rows = self.db.execute_query(
            "SELECT scopes FROM user_tenant_scope "
            "WHERE email = %s AND administration = %s AND module = %s",
            (email, administration, module),
            fetch=True,
        )
        if not rows:
            return {}
        parsed = self._parse_scopes(rows[0].get("scopes"))
        return parsed if isinstance(parsed, dict) else {}

    # -- write ---------------------------------------------------------------

    def set_scope(
        self,
        email: str,
        administration: str,
        module: str,
        scopes: Mapping[str, Any],
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Atomically overwrite (or clear) a user's scope grant (R4.5/R4.2/R2.4).

        Validates every dimension key + value against the tenant's
        ``<module>.scope_dimensions`` param (canonical-equality via ``scope_canon``)
        BEFORE writing — an unknown dimension/value raises
        :class:`ScopeValidationError` and NOTHING is written (atomic). A validated
        value is normalized to its canonical declared spelling.

        The stored grant is the EXACT set passed (atomic overwrite / upsert). When
        the normalized grant is empty — no dimensions, or every dimension cleared —
        the ``(email, administration, module)`` row is DELETED (clearing all = deny,
        R4.5), never stored as an empty ``{}``.

        After a committed write or delete, fires ``enqueue_sync(administration)``
        (best-effort — a trigger failure never breaks the write, R2.4). NEVER reads
        or writes ``user_tenant_roles`` (axis independence, R1.3/Property 5).

        Args:
            email: The target member-user's email.
            administration: The verified tenant (tenant isolation).
            module: The owning module (``MEMBERS`` for s5d).
            scopes: The desired grant ``{ "<dimension>": ["<value>", ...] | ["*"] }``.
            created_by: The acting Tenant-Admin (audit column), optional.

        Returns:
            The normalized ``scopes`` that were persisted (``{}`` when the grant was
            cleared and the row deleted).

        Raises:
            ScopeValidationError: An unknown dimension key or unknown value.
            ValueError: ``administration`` is blank (a cross-tenant hazard).
        """
        self._require_tenant(administration)
        normalized = self._validate_and_canonicalize(scopes, administration, module)

        if not normalized:
            # Clearing all selections -> delete the row (deny-by-default, R4.5).
            self._delete_row(email, administration, module)
        else:
            self._upsert_row(email, administration, module, normalized, created_by)

        # R2.4 — on-change projection sync trigger, AFTER the committed write/delete.
        # Best-effort: never breaks the scope write (reconciliation backstops).
        self._fire_enqueue_sync(administration)
        return normalized

    # -- internals -----------------------------------------------------------

    def _upsert_row(
        self,
        email: str,
        administration: str,
        module: str,
        scopes: Mapping[str, Any],
        created_by: str | None,
    ) -> None:
        """Atomic overwrite of the row's ``scopes`` JSON via upsert (R4.5).

        The UNIQUE key ``(email, administration, module)`` makes this an insert-or-
        replace of exactly that user's grant; ``ON DUPLICATE KEY UPDATE`` overwrites
        ``scopes`` wholesale (never merges) so the save reflects exactly the passed
        set. ``administration`` is written explicitly (steering 31).
        """
        self.db.execute_query(
            """
            INSERT INTO user_tenant_scope (email, administration, module, scopes, created_by)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                scopes = VALUES(scopes),
                created_by = VALUES(created_by)
            """,
            (email, administration, module, json.dumps(dict(scopes)), created_by),
            fetch=False,
            commit=True,
        )

    def _delete_row(self, email: str, administration: str, module: str) -> None:
        """Delete the user's scope row for the tenant + module (clear = deny)."""
        self.db.execute_query(
            "DELETE FROM user_tenant_scope "
            "WHERE email = %s AND administration = %s AND module = %s",
            (email, administration, module),
            fetch=False,
            commit=True,
        )

    def _validate_and_canonicalize(
        self,
        scopes: Mapping[str, Any],
        administration: str,
        module: str,
    ) -> dict[str, list[str]]:
        """Validate a grant against the dimension config and canonicalize its values.

        Reads the tenant's ``<module>.scope_dimensions`` param (read-only). Each
        dimension key in ``scopes`` must be an ENABLED dimension; each granted value
        must match one of that dimension's declared ``values`` by canonical-equality
        (``scope_canon``). ``["*"]`` is accepted verbatim for any enabled dimension.

        Returns the normalized grant: each dimension's values stored as their
        CANONICAL DECLARED spelling (de-duplicated, declared order), and dimensions
        whose grant is empty (or an empty list) DROPPED — so an all-cleared grant
        normalizes to ``{}`` and the caller deletes the row.

        Raises:
            ScopeValidationError: An unknown dimension key or an unknown value.
        """
        if not isinstance(scopes, Mapping):
            raise ScopeValidationError(
                "scopes must be an object of { dimension: [values] }"
            )

        dimension_meta = self._load_dimension_meta(administration, module)

        normalized: dict[str, list[str]] = {}
        for dim_key, raw_grant in scopes.items():
            meta = dimension_meta.get(dim_key)
            if meta is None:
                raise ScopeValidationError(
                    f"Unknown scope dimension '{dim_key}' for module '{module}'"
                )

            if not isinstance(raw_grant, Sequence) or isinstance(raw_grant, str):
                raise ScopeValidationError(
                    f"Grant for dimension '{dim_key}' must be a list of values"
                )

            # All-access sentinel: any ["*"] entry grants the whole dimension.
            if any(isinstance(g, str) and g == WILDCARD_VALUE for g in raw_grant):
                normalized[dim_key] = [WILDCARD_VALUE]
                continue

            canon_to_value: dict[str, str] = meta["canon_to_value"]
            declared_order: list[str] = meta["declared_order"]
            accepted: set[str] = set()
            for value in raw_grant:
                if not isinstance(value, str):
                    raise ScopeValidationError(
                        f"Value {value!r} for dimension '{dim_key}' is not a string"
                    )
                declared = canon_to_value.get(scope_canon(value))
                if declared is None:
                    raise ScopeValidationError(
                        f"Unknown value '{value}' for scope dimension '{dim_key}'"
                    )
                accepted.add(declared)

            if accepted:
                # Emit as the canonical declared spelling, in declared order.
                normalized[dim_key] = [v for v in declared_order if v in accepted]

        return normalized

    def _load_dimension_meta(
        self, administration: str, module: str
    ) -> dict[str, dict[str, Any]]:
        """Load enabled ``<module>.scope_dimensions`` as a validation index.

        Returns a map ``dimension_key -> {canon_to_value, declared_order}`` for
        every ENABLED dimension of the tenant (disabled dimensions are omitted, so
        a grant on one is rejected as unknown). The namespace is the module token
        lower-cased (s5d: ``members``); the value list is the source of truth for
        canonical values (D4/R5.1).
        """
        namespace = module.lower() if module else _MEMBERS_PARAM_NAMESPACE
        raw_dimensions = self.parameter_service.get_param(
            namespace,
            _SCOPE_DIMENSIONS_PARAM_KEY,
            tenant=administration,
        )

        meta: dict[str, dict[str, Any]] = {}
        if not (
            isinstance(raw_dimensions, Sequence) and not isinstance(raw_dimensions, str)
        ):
            return meta

        for entry in raw_dimensions:
            if not isinstance(entry, Mapping):
                continue
            key = entry.get("key")
            if not key:
                continue
            if not entry.get("enabled", True):
                continue
            raw_values = entry.get("values") or ()
            if isinstance(raw_values, str) or not isinstance(raw_values, Sequence):
                raw_values = ()
            canon_to_value: dict[str, str] = {}
            declared_order: list[str] = []
            for value in raw_values:
                if not isinstance(value, str):
                    continue
                declared_order.append(value)
                canon_to_value.setdefault(scope_canon(value), value)
            meta[key] = {
                "canon_to_value": canon_to_value,
                "declared_order": declared_order,
            }
        return meta

    def _fire_enqueue_sync(self, administration: str) -> None:
        """Fire the best-effort projection sync; never break the write (R2.4)."""
        try:
            self._enqueue_sync(administration)
        except Exception as exc:
            logger.warning(
                "user_tenant_scope: enqueue_sync failed for administration %r: %s "
                "— scope write is unaffected; reconciliation will backstop",
                administration,
                exc,
            )

    @staticmethod
    def _require_tenant(administration: str) -> None:
        """Guard against a blank tenant (no silent default — steering 31)."""
        if not administration:
            raise ValueError(
                "administration must be non-empty — a blank tenant scope is a "
                "cross-tenant hazard (steering 31)"
            )

    @staticmethod
    def _parse_scopes(raw: Any) -> Any:
        """Parse a ``scopes`` JSON column value (string or already-parsed)."""
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        return raw

    # -- cross-plane scope-grant reconciliation (Task 3.9 / Requirement 23) --------------

    def list_grants(self, administration: str, module: str) -> list[dict[str, Any]]:
        """Return every ``user_tenant_scope`` grant for the tenant + module (R23 detection).

        Each item is ``{"email", "scopes"}`` with ``scopes`` the parsed grant dict. Tenant-
        isolated on ``administration`` (steering 31). Read-only; never touches
        ``user_tenant_roles`` (axis independence, R1.3/Property 5).
        """
        self._require_tenant(administration)
        rows = self.db.execute_query(
            "SELECT email, scopes FROM user_tenant_scope "
            "WHERE administration = %s AND module = %s",
            (administration, module),
            fetch=True,
        )
        grants: list[dict[str, Any]] = []
        for row in rows or []:
            parsed = self._parse_scopes(row.get("scopes"))
            grants.append(
                {
                    "email": row.get("email"),
                    "scopes": parsed if isinstance(parsed, dict) else {},
                }
            )
        return grants

    def reconcile_scope_change(
        self,
        administration: str,
        module: str,
        proposed_dimensions: Sequence[Mapping[str, Any]] | None,
    ) -> ScopeChangeReconciliation:
        """Classify a PROPOSED scope-dimension change against the tenant's existing grants (R23).

        Compares the proposed dimension set (the SAM/overlay-derived ``config#scope`` dimensions
        — the shape ``members.scope_dimensions`` carries) against every current
        ``user_tenant_scope`` grant for the tenant, BEFORE the change is applied. Two tiers
        (OQ-7 RESOLVED, message-based interim — the frontend NEVER auto-rewrites grants):

        - **ROUTINE** (new tenant / add a dimension or value — no existing grant orphaned): the
          caller auto-mirrors the dimension set and surfaces a REMINDER to review user scope
          grants. Returned as ``tier="routine"`` with ``orphaned=[]``.
        - **ORPHANING** (rename/remove a dimension, or drop a granted value — would strand an
          existing grant): the change is BLOCKED. Returned as ``tier="orphaning"`` with the
          orphaned references; :meth:`assert_appliable` raises
          :class:`ScopeReconciliationBlocked` so the caller refuses to apply it.

        Invariant (R23): a grant referencing a dimension/value NOT present in the proposed set is
        an orphan. A granted ``["*"]`` (whole-dimension) orphans only if the dimension itself is
        removed/renamed (an added/removed value does not strand a wildcard grant). Canonical-
        equality (``scope_canon``) is used so a declared-spelling change that is canonically the
        same value is NOT an orphan.
        """
        self._require_tenant(administration)
        # Index the proposed dimensions by key → set of canonical declared values (enabled only;
        # a disabled dimension is treated as absent, matching validation).
        proposed: dict[str, set[str]] = {}
        for entry in proposed_dimensions or ():
            if not isinstance(entry, Mapping):
                continue
            key = entry.get("key")
            if not key or not entry.get("enabled", True):
                continue
            raw_values = entry.get("values") or ()
            if isinstance(raw_values, str) or not isinstance(raw_values, Sequence):
                raw_values = ()
            proposed[key] = {scope_canon(v) for v in raw_values if isinstance(v, str)}

        orphaned: list[dict[str, Any]] = []
        for grant in self.list_grants(administration, module):
            email = grant["email"]
            for dim_key, granted in grant["scopes"].items():
                if not isinstance(granted, Sequence) or isinstance(granted, str):
                    continue
                if dim_key not in proposed:
                    # The whole dimension is gone (removed or renamed) → every grant on it is
                    # stranded, including a wildcard grant.
                    orphaned.append(
                        {"email": email, "dimension": dim_key, "values": list(granted)}
                    )
                    continue
                # A wildcard grant survives any value-set change (it means "the whole dimension").
                if any(g == WILDCARD_VALUE for g in granted if isinstance(g, str)):
                    continue
                declared = proposed[dim_key]
                stranded = [
                    g
                    for g in granted
                    if isinstance(g, str) and scope_canon(g) not in declared
                ]
                if stranded:
                    orphaned.append(
                        {"email": email, "dimension": dim_key, "values": stranded}
                    )

        tier = "orphaning" if orphaned else "routine"
        return ScopeChangeReconciliation(tier=tier, orphaned=orphaned)


@dataclass(frozen=True)
class ScopeChangeReconciliation:
    """The result of classifying a proposed scope-dimension change (Task 3.9 / R23).

    ``tier`` is ``"routine"`` (no existing grant orphaned — auto-mirror + reminder) or
    ``"orphaning"`` (at least one grant would be stranded — block + contact-SysAdmin).
    ``orphaned`` lists the stranded references (empty for routine).
    """

    tier: str
    orphaned: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_routine(self) -> bool:
        return self.tier == "routine"

    @property
    def is_orphaning(self) -> bool:
        return self.tier == "orphaning"

    def assert_appliable(self) -> None:
        """Raise :class:`ScopeReconciliationBlocked` when the change would orphan a grant (R23).

        The no-silent-stale-grant invariant: a caller calls this before applying a proposed scope
        change; a routine change passes, an orphaning change refuses (never applied silently).
        """
        if self.is_orphaning:
            names = ", ".join(
                f"{o['email']}:{o['dimension']}={o['values']}" for o in self.orphaned
            )
            raise ScopeReconciliationBlocked(
                "Scope change blocked: it would orphan existing user scope grants "
                f"({names}). Contact your System Administrator to realign grants before "
                "removing or renaming a dimension or value.",
                self.orphaned,
            )
