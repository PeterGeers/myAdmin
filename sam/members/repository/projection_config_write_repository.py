"""Members config **write repository** (spec 02, design C3) — the net-new, SAM-owned writer.

The ``boto3``-backed **writer** sibling of the read-only
:mod:`sam.members.repository.projection_config_reader` (``MembersProjectionReader``). It
performs a versioned ``put_item`` on exactly the three SAM-owned ``config#*`` rows —
``config#fields`` / ``config#scope`` / ``config#mail`` — so DynamoDB ``governance_projection``
becomes the system-of-record for those rows while the reader keeps serving them UNCHANGED.

Two write verbs, two purposes (spec 03, design C2/C6)
-----------------------------------------------------
- :meth:`MembersConfigWriteRepository.put_config` — the whole-row ``put_item`` REPLACE. It is the
  C6 create/migration primitive ONLY (R1.5): tenant-create seeds the ``{fields, overrides,
  functional_groups}`` skeleton, the LIST→MAP migration backfills it. It is NEVER on the runtime
  Change-Op path (a partial whole-row replace is the exact truncation bug this spec kills).
- :meth:`MembersConfigWriteRepository.ensure_skeleton` — the NEW-TENANT, IF-ABSENT create of that
  same ``config#fields`` skeleton + a seeded ``version`` (spec 03 task 2.0a / C6 / Must-fix #1). It
  reuses the C6 whole-row primitive but guards it with ``attribute_not_exists(sk)`` so it is
  idempotent and NEVER overwrites a populated row. The tenant-create / config-provisioning path
  MUST call it so the parent maps exist before the first Change-Op (today onboarding is manual —
  see ``functional_groups_list_to_map_RUNBOOK.md`` §"New-tenant row skeleton" for the call site).
- :meth:`MembersConfigWriteRepository.apply_ops` — the runtime Change-Op path. ONE
  version-conditional ``update_item`` built from a set of SET/REMOVE PATH ops. Because an
  ``update_item`` only ever writes the attributes the ops name, a partial op set is structurally
  unable to truncate ``functional_groups`` or any slice — the guarantee is in the verb, not in a
  flawless merge. See :meth:`MembersConfigWriteRepository.apply_ops` for the ops input contract
  that tasks 2.2/2.3 (the ``ConfigFieldsCrudService`` + placement mechanics) produce.

Why this exists (design C3)
---------------------------
Phase 1 introduces a SAM-owned write path (API Gateway PUT -> Members Lambda edge ->
config-write domain service -> **this repository** -> DynamoDB) for the three tenant-level
config rows the SAM plane ONLY reads. This is infrastructure: the config-write domain service
(no ``boto3``) shapes the validated body and the row-level version stamp, then hands
``(tenant_id, config_id, attributes, version)`` here for persistence. The domain never imports
this module (dependency inversion — the arrow points inward, mirroring the reader's layering).

Split-ownership guardrail (R2)
------------------------------
The write surface is CLOSED to exactly ``{scope, fields, mail}`` via :data:`_WRITABLE_CONFIG_IDS`.
This repository is the structural second guard behind the route's ``configId`` check: it NEVER
authors ``tenant`` / ``module#`` / ``role#`` / ``scopegrant#`` / ``config#views`` rows, so the
split-ownership partition between SAM and ``ProjectionSync`` (Flask) stays clean. A write for any
id outside the closed set raises ``ValueError`` BEFORE any ``put_item``.

Schema tokens only (R1.6)
-------------------------
Every key attribute name and token comes from :mod:`services.projection_schema` — the same single
source the reader uses (``CONFIG_ID_*``, ``RECORD_TYPE_CONFIG``, ``build_sort_key``, ``build_key``,
``PARTITION_KEY_ATTR`` / ``SORT_KEY_ATTR`` / ``VERSION_ATTR``). Reusing the shared schema means the
writer and reader cannot drift on the key shape or the ``config#<id>`` id tokens.

Config + fail-fast (R5.1/R5.2)
------------------------------
The table is resolved from ``GOVERNANCE_PROJECTION_TABLE`` via the S3 fail-fast client
(:func:`services.projection_schema.get_projection_table_resource`) — missing/blank throws, no
dangerous default, resolved lazily on first real ``put_item``. The ``table`` is injectable so tests
use an in-memory fake / local dynamodb-local. A blank ``tenant_id`` is rejected before any write so
the tenancy boundary is never crossed by a blank key (R5.5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services import projection_schema as schema

__all__ = [
    "MembersConfigWriteRepository",
    "ChangeOpError",
    "StaleVersionError",
    "TruncationTripwireError",
    "SET",
    "REMOVE",
    "FIELDS_SKELETON_PARENTS",
]

#: The ``config#fields`` parent-map skeleton the Phase-2 path ``update_item`` REQUIRES to exist
#: (spec 03, design C6 / Must-fix #1). A path ``update_item`` cannot seed a parent map in the same
#: expression that sets a child (``SET a.b.c`` when ``a.b`` is absent → "paths overlap" / "document
#: path not found"), so the three parent maps MUST pre-exist before the first Change-Op. These are
#: the parent keys :meth:`MembersConfigWriteRepository.ensure_skeleton` guarantees (each an empty
#: map), matching the empty-is-valid shape the reader already serves for a never-authored tenant.
FIELDS_SKELETON_PARENTS = ("fields", "overrides", "functional_groups")

#: The two op actions the Change-Op path supports. A ``SET`` writes a value at a path; a
#: ``REMOVE`` deletes the attribute at a path. These are the ONLY two verbs — there is no
#: whole-record replace on the Change-Op path (R1.5).
SET = "SET"
REMOVE = "REMOVE"
_VALID_ACTIONS = frozenset({SET, REMOVE})

#: Sentinel ``base_version`` for case (ii) — an EXISTING row that predates the version model
#: (legacy, no ``version`` attribute). Passing this selects the ``attribute_not_exists(version)``
#: condition so the first versioned write onto a legacy row is not spuriously rejected (design D5,
#: design-review Must-fix #2). ``None`` (not this sentinel) means case (iii): no row yet.
LEGACY_NO_VERSION = "__legacy_no_version__"

#: Attribute that stores the last applied ``client_op_id`` for lost-response idempotency
#: (review Should-fix; task 4.2). Compared on a conditional-check failure to recognise a replay.
_CLIENT_OP_ID_ATTR = "last_client_op_id"


class ChangeOpError(ValueError):
    """A caller-safe, deterministic rejection of a malformed / unsafe Change-Op set.

    Raised BEFORE any ``update_item`` so the service (tasks 2.2/2.3) can surface an intelligible
    400 (steering 35/39 — no raw internals). Covers: an empty op list, a malformed op shape, an
    unknown action, a blank/empty path segment, and — the important one — OVERLAPPING paths in the
    same request (the "document paths overlap" class DynamoDB would otherwise reject opaquely).
    """


class StaleVersionError(RuntimeError):
    """The version-conditional write failed — the row changed under the caller (design D5, R6).

    Raised when DynamoDB rejects the single ``update_item`` with
    ``ConditionalCheckFailedException`` and the write is NOT a recognised idempotent replay. The
    service maps this to a caller-safe 409 "reload and retry" (task 4.1). No partial change was
    made — the whole op set is atomic (all-or-nothing)."""


class TruncationTripwireError(RuntimeError):
    """LAST-LINE DEFENSE: an ``apply_ops`` call would SILENTLY shrink the catalog / field set
    (spec 03 task 8.4 / R11.5) — refused before any write, nothing persisted.

    The Change-Op model already makes catalog truncation STRUCTURALLY hard (a path ``update_item``
    only writes the attributes the ops name, so a partial payload cannot replace a whole map —
    design C1/D1). This tripwire is the runtime backstop UNDERNEATH that guarantee: even if a LOGIC
    BUG upstream produced an op set that would reduce the stored group or field COUNT, the write is
    refused unless that reduction is EXPLAINED by an explicit whole-entry delete op in the SAME
    request. A legitimate ``delete_field`` / ``delete_group`` / ``reset_field`` (a ``REMOVE`` of a
    whole ``fields.<key>`` / ``overrides.<dotted>`` / ``functional_groups.<gkey>`` entry) is allowed
    — the count may drop by exactly what those deletes remove. A SILENT shrink (the projected count
    would fall with NO delete op accounting for it) is refused with a caller-safe message.

    This does NOT fire on GROWTH: the C6 ``ensure_skeleton`` create and the first write onto an
    empty skeleton go empty→populated (an increase), and the migration whole-row write never goes
    through ``apply_ops``. Only a net REDUCTION not covered by explicit deletes trips it."""

#: The CLOSED set of ``config#<id>`` ids this repository may write (R2.1). The tokens come from
#: the shared projection schema so the writer, reader, and Flask builder cannot drift. Any id
#: outside this set is rejected before a ``put_item`` (R2.3) — so ``tenant`` / ``module#`` /
#: ``role#`` / ``scopegrant#`` / ``config#views`` are structurally unwritable by SAM (R2.4/R2.5).
_WRITABLE_CONFIG_IDS = frozenset(
    {schema.CONFIG_ID_SCOPE, schema.CONFIG_ID_FIELDS, schema.CONFIG_ID_MAIL}
)


class MembersConfigWriteRepository:
    """Versioned writer for the three SAM-owned ``config#*`` rows (design C3).

    Performs a single ``put_item`` per write, authoring the EXACT attribute shape the
    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader` reads back
    for that ``configId`` (R1.4), so the reader stays unchanged. The write surface is closed to
    :data:`_WRITABLE_CONFIG_IDS` (R2), the table resolves fail-fast (R5.1/R5.2), and every write
    requires a non-empty ``tenant_id`` partition key (R5.5).

    Args:
        table: A boto3 DynamoDB Table (or a fake exposing ``put_item``). Defaults to the
            fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`). Injectable so
            tests use an in-memory fake / local dynamodb-local.
    """

    def __init__(self, table=None, version_fn=None):
        self._table = table
        # The row-level version minter (ISO-8601 UTC ordering stamp). Defaults to the shared pure
        # domain helper; injectable so tests pin a deterministic stamp for the apply_ops bump.
        if version_fn is None:
            from sam.members.domain.config_write_version import next_write_stamp

            version_fn = next_write_stamp
        self._version_fn = version_fn

    @property
    def table(self):
        """The projection table, resolved lazily + fail-fast on first use (R5.1/R5.2)."""
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    def put_config(
        self,
        tenant_id: str,
        config_id: str,
        attributes: dict,
        version: str,
    ) -> dict:
        """Write one SAM-owned ``config#<config_id>`` row with a versioned ``put_item``.

        Builds the key via ``build_key(tenant_id, build_sort_key(RECORD_TYPE_CONFIG, config_id))``,
        merges the caller-shaped ``attributes`` onto that key, stamps :data:`VERSION_ATTR` with the
        row-level ``version``, and performs a single ``put_item``. The item is authored in the exact
        shape the reader reads back for ``config_id`` (R1.4) — this repository adds only the key and
        the version stamp; it does not reshape the domain-provided ``attributes``.

        The key attributes (``PARTITION_KEY_ATTR`` / ``SORT_KEY_ATTR``) and the version stamp always
        win over any same-named keys that leaked into ``attributes``, so the written row's key and
        version are never shadowed by the body.

        Args:
            tenant_id: The tenant (partition key) to write under. Must be non-empty (R5.5).
            config_id: One of ``{scope, fields, mail}`` (R2.1) — rejected otherwise (R2.3).
            attributes: The reader-shaped attribute body (e.g. ``fields``/``overrides``/
                ``functional_groups`` for ``fields``), with no key or version attribute needed.
            version: The row-level monotonic ISO-8601 write stamp (computed by the domain service).

        Returns:
            The exact item dict written to DynamoDB (key + version + attributes merged).

        Raises:
            ValueError: ``tenant_id`` is blank (R3.5/R5.5), or ``config_id`` is outside the closed
                writable set (R2.3) — both raised BEFORE any ``put_item``.
        """
        if not tenant_id:
            raise ValueError(
                "tenant_id (partition key) must be non-empty — a blank tenant is a "
                "cross-tenant hazard (R5.5)"
            )
        if config_id not in _WRITABLE_CONFIG_IDS:
            raise ValueError(
                f"config_id {config_id!r} is not writable by the SAM plane; the write "
                f"surface is closed to {sorted(_WRITABLE_CONFIG_IDS)!r} (R2.3)"
            )

        sort_key_value = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, config_id)
        key = schema.build_key(tenant_id, sort_key_value)

        # Merge the reader-shaped body first, then let the key + version stamp win so neither the
        # partition/sort key nor the authoritative version can be shadowed by a stray body attr.
        item = {
            **(attributes or {}),
            **key,
            schema.VERSION_ATTR: version,
        }

        self.table.put_item(Item=item)
        return item

    # ──────────────────────────────────────────────────────────────────────────────────
    # Row-skeleton create primitive (spec 03, task 2.0a / design C6 / review Must-fix #1)
    # ──────────────────────────────────────────────────────────────────────────────────

    def ensure_skeleton(self, tenant_id: str) -> dict:
        """Create a tenant's ``config#fields`` row skeleton IF-ABSENT — idempotent (design C6).

        This is the NEW-TENANT seeding half of C6 (the migration backfills legacy rows). A
        freshly-created tenant must get its ``config#fields`` row seeded with the parent-map
        skeleton ``{fields: {}, overrides: {}, functional_groups: {}}`` plus a seeded ``version``
        BEFORE the first Change-Op, because the Phase-2 path ``update_item`` requires those parent
        maps to exist (Must-fix #1 — an ``if_not_exists``-in-the-same-op seed is rejected by
        DynamoDB as "document paths overlap"). Call this from the tenant-create / config-provision
        path (there is no SAM runtime tenant-create path today — see the module/RUNBOOK notes and
        :mod:`sam.members.migration.functional_groups_list_to_map` for the legacy-row backfill).

        It is the C6 create primitive — the idempotent, race-safe sibling of the sanctioned
        whole-row :meth:`put_config` writer (R1.5), authoring the IDENTICAL item shape (key +
        version win over the body); it does NOT add a second general-purpose whole-row writer and
        is never on the runtime Change-Op path. The IF-ABSENT guarantee is a
        ``ConditionExpression`` of ``attribute_not_exists(sk)``: the row is created ONLY when it
        does not already exist, so a populated row (one that already carries real fields / overrides
        / groups) is NEVER overwritten or truncated. Running it twice — or against an
        already-provisioned tenant — is a safe no-op.

        Args:
            tenant_id: The tenant (partition key) to seed. Must be non-empty (R5.5).

        Returns:
            ``{"created": <bool>, "version": <str | None>}`` — ``created`` is ``True`` when this
            call wrote the skeleton, ``False`` when a row already existed (idempotent no-op); when
            ``True`` ``version`` is the seeded stamp, when ``False`` it is ``None`` (the existing
            row's version is left untouched and is not read back here).

        Raises:
            ValueError: ``tenant_id`` is blank (R5.5) — raised BEFORE any write.
        """
        if not tenant_id:
            raise ValueError(
                "tenant_id (partition key) must be non-empty — a blank tenant is a "
                "cross-tenant hazard (R5.5)"
            )

        version = self._version_fn()
        skeleton = {parent: {} for parent in FIELDS_SKELETON_PARENTS}
        sort_key_value = schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
        )
        key = schema.build_key(tenant_id, sort_key_value)

        # The C6 whole-row create, but IF-ABSENT: a put_item carrying the same key/version/body as
        # put_config, guarded by attribute_not_exists(sk) so it NEVER overwrites an existing row.
        # We reuse put_config's exact item shaping (key + version win over the body) and add the
        # conditional guard here rather than widening put_config's signature — put_config stays the
        # plain create/migration primitive, ensure_skeleton is its idempotent, race-safe sibling.
        item = {
            **skeleton,
            **key,
            schema.VERSION_ATTR: version,
        }

        from botocore.exceptions import ClientError

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(#sk)",
                ExpressionAttributeNames={"#sk": schema.SORT_KEY_ATTR},
            )
        except ClientError as exc:
            if _client_error_code(exc) != "ConditionalCheckFailedException":
                raise
            # The row already exists — idempotent no-op. We did NOT overwrite it.
            return {"created": False, "version": None}

        return {"created": True, "version": version}

    # ──────────────────────────────────────────────────────────────────────────────────
    # Change-Op path write — a single version-conditional ``update_item`` (spec 03, C2/D5)
    # ──────────────────────────────────────────────────────────────────────────────────

    def apply_ops(
        self,
        tenant_id: str,
        config_id: str,
        ops: Sequence[Mapping[str, Any]],
        base_version: str | None,
        client_op_id: str | None = None,
    ) -> dict:
        """Apply a set of Change-Ops to one ``config#<config_id>`` row as ONE atomic, version-
        conditional ``update_item`` (spec 03, design C2 + D5; design-review Must-fix #1/#2).

        This is the ONLY runtime write verb on the Change-Op path. It issues a SINGLE
        ``update_item`` carrying a combined ``SET``/``REMOVE`` ``UpdateExpression`` built from the
        ops' paths plus a ``ConditionExpression`` that guards + bumps ``version`` in the same
        expression. DynamoDB leaves every attribute the ops do not name physically untouched, so a
        partial op set can NEVER truncate ``functional_groups`` or any other slice (R1.3/R4.2) —
        the guarantee is structural, not "safe if a merge is perfect". The whole-row
        :meth:`put_config` stays ONLY the C6 create/migration primitive (R1.5); it is never on this
        path.

        The ops input contract (so tasks 2.2/2.3 produce EXACTLY this shape)
        -------------------------------------------------------------------
        ``ops`` is a non-empty sequence of op mappings. Each op is::

            {
                "action": "SET" | "REMOVE",   # the two verbs (module constants SET / REMOVE)
                "path":   [segment, ...],      # one or more KEY SEGMENTS, outer→inner
                "value":  <any>,               # REQUIRED for SET; absent/ignored for REMOVE
            }

        - ``path`` is a list of raw key SEGMENTS, NOT a dotted string. The service decides placement
          and hands the segments verbatim:
            * a variable field aspect  → ``["fields", "<key>", "<attr>"]`` (UPDATE an aspect)
            * a whole variable field   → ``["fields", "<key>"]``            (CREATE the entry)
            * a base/calculated override aspect → ``["overrides", "<group>.<key>", "<attr>"]``
            * a whole override entry   → ``["overrides", "<group>.<key>"]``
            * a group entry            → ``["functional_groups", "<gkey>"]``
          Every segment — INCLUDING the dotted ``"<group>.<key>"`` override key — is bound through
          ``ExpressionAttributeNames`` (``#n0.#n1.#n2``), so a ``.`` inside a segment is treated as
          a LITERAL key name and never mis-parsed as a nested document path (design-review Q2).
        - ``value`` may be any DynamoDB-serialisable value for a ``SET`` (a scalar, or a whole entry
          map for a CREATE). It is read only for ``SET``; a ``REMOVE`` ignores it.
        - CREATE-vs-UPDATE verb choice (seeding) is the SERVICE's responsibility (task 2.3): the
          parent maps (``fields``/``overrides``/``functional_groups``) are guaranteed to exist by
          the row skeleton (C6), so a CREATE is ``SET ["overrides", key] = :whole_entry`` and an
          UPDATE is ``SET ["overrides", key, attr] = :v``. This repository does NOT do
          ``if_not_exists`` parent-seeding in the same expression (DynamoDB rejects it, Must-fix #1).

        Multi-op semantics — ALL-OR-NOTHING + up-front overlap rejection
        ----------------------------------------------------------------
        A request MAY carry several ops; they apply in ONE ``update_item`` (one atomic write — all
        succeed or none do). OVERLAPPING paths are REJECTED up front with :class:`ChangeOpError`
        (e.g. ``SET overrides.x`` together with ``SET overrides.x.label`` — the same "document paths
        overlap" class DynamoDB would reject opaquely). A path overlaps another when one is a prefix
        of the other (or they are identical); the check runs BEFORE the call so the error is
        intelligible to the caller rather than a raw DynamoDB fault.

        Version-conditional — the THREE cases (design D5, design-review Must-fix #2)
        ---------------------------------------------------------------------------
        The single ``update_item`` carries a ``ConditionExpression`` with exactly one of three
        shapes, selected by ``base_version``. This method computes and stamps the NEXT ``version``
        itself (callers do not pass it) and bumps it in the SAME expression so the lock-and-bump is
        atomic. Concretely:
          (i)   ``base_version`` is a non-empty string → the row is expected to exist WITH that
                version → ``version = :base`` (optimistic lock; the common case).
          (ii)  ``base_version`` is the sentinel :data:`LEGACY_NO_VERSION` (an existing row that
                predates versioning) → ``attribute_not_exists(version)`` so the first versioned
                write is not spuriously rejected.
          (iii) ``base_version`` is ``None`` → no row yet (first write onto the skeleton) →
                ``attribute_not_exists(sk)``.
        In all three, a NEW ``version`` is SET in the SAME expression (so the lock-and-bump is
        atomic). A stale base → ``ConditionalCheckFailedException`` → :class:`StaleVersionError`
        (caller-safe 409), with NO partial change.

        Idempotency hook (optional ``client_op_id`` — review Should-fix; task 4.2 builds on this)
        ---------------------------------------------------------------------------------------
        When ``client_op_id`` is supplied, it is stamped onto the row (``last_client_op_id``) in the
        same ``update_item``. On a ``ConditionalCheckFailedException``, this method re-reads the row:
        if the stored ``last_client_op_id`` already equals this ``client_op_id`` (a lost-response
        retry that ALREADY produced the current version), it returns success rather than a spurious
        self-409. Any other conditional failure is a genuine stale write → :class:`StaleVersionError`.

        Args:
            tenant_id: The tenant (partition key). Must be non-empty (R5.5).
            config_id: One of ``{fields, scope, mail}`` (R2.1) — rejected otherwise (R2.3).
            ops: The non-empty Change-Op sequence (shape above). Overlapping / malformed → reject.
            base_version: The version the caller read (case i), :data:`LEGACY_NO_VERSION` (case ii),
                or ``None`` for a first write (case iii).
            client_op_id: Optional idempotency token for lost-response retries.

        Returns:
            ``{"version": <new version>, "idempotent_replay": <bool>}`` — the new row version and
            whether this call was recognised as an already-applied replay (no new write made).

        Raises:
            ValueError: blank ``tenant_id`` or a ``config_id`` outside the closed writable set
                (both BEFORE any call), matching :meth:`put_config`.
            ChangeOpError: empty/malformed ops, unknown action, blank segment, or OVERLAPPING paths
                (all BEFORE any call).
            TruncationTripwireError: (``config#fields`` only) the op set would SILENTLY shrink the
                group/field count below the stored count by MORE than the explicit whole-entry
                delete ops account for (spec 03 task 8.4 / R11.5) — refused BEFORE any write, last-
                line defense beneath the structural Change-Op guarantee.
            StaleVersionError: the version-conditional write failed and it is not an idempotent
                replay (caller-safe 409; no partial change).

        Last-line truncation tripwire (``config#fields`` only — spec 03 task 8.4 / R11.5)
        ---------------------------------------------------------------------------------
        The Change-Op model already makes catalog truncation STRUCTURALLY hard (a path
        ``update_item`` only writes attributes the ops name). As defense in depth, for
        ``config#fields`` this method reads the CURRENT stored row and refuses the write if it would
        reduce the group count (keys of ``functional_groups``) or the field count (keys of
        ``fields`` + ``overrides``) below the stored count UNLESS explicit whole-entry ``REMOVE``
        ops (``delete_field`` / ``delete_group`` / ``reset_field``) account for the drop. It never
        fires on a growth (the C6 empty→populated first write) or an attribute-level edit.
        """
        if not tenant_id:
            raise ValueError(
                "tenant_id (partition key) must be non-empty — a blank tenant is a "
                "cross-tenant hazard (R5.5)"
            )
        if config_id not in _WRITABLE_CONFIG_IDS:
            raise ValueError(
                f"config_id {config_id!r} is not writable by the SAM plane; the write "
                f"surface is closed to {sorted(_WRITABLE_CONFIG_IDS)!r} (R2.3)"
            )

        normalized = self._normalize_and_validate_ops(ops)
        new_version = self._version_fn()
        plan = self._build_update_expression(
            normalized, new_version, base_version, client_op_id
        )

        sort_key_value = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, config_id)
        key = schema.build_key(tenant_id, sort_key_value)

        # LAST-LINE DEFENSE (spec 03 task 8.4 / R11.5): for config#fields, refuse a SILENT shrink of
        # the group/field catalog that is NOT explained by an explicit delete op in this request.
        # Runs AFTER validation + key resolution, BEFORE the update_item, so a refusal persists
        # nothing (caller-safe, atomic). Only config#fields carries the catalog/field-count
        # semantics; scope/mail rows have no such invariant.
        if config_id == schema.CONFIG_ID_FIELDS:
            self._assert_no_silent_truncation(key, normalized)

        from botocore.exceptions import ClientError

        try:
            self.table.update_item(
                Key=key,
                UpdateExpression=plan["UpdateExpression"],
                ConditionExpression=plan["ConditionExpression"],
                ExpressionAttributeNames=plan["ExpressionAttributeNames"],
                ExpressionAttributeValues=plan["ExpressionAttributeValues"],
            )
        except ClientError as exc:
            if _client_error_code(exc) != "ConditionalCheckFailedException":
                raise
            # The version condition failed. If this is a lost-response retry of the SAME
            # client_op_id that already produced the current row, treat it as an idempotent
            # success rather than a spurious self-409 (review Should-fix; task 4.2).
            if client_op_id and self._is_idempotent_replay(
                key, client_op_id
            ):
                return {"version": self._read_version(key), "idempotent_replay": True}
            raise StaleVersionError(
                "config write rejected: the row changed since it was read — reload and retry"
            ) from exc

        return {"version": new_version, "idempotent_replay": False}

    # ── Change-Op helpers (no boto3 — pure expression building + validation) ────────────

    @staticmethod
    def _normalize_and_validate_ops(
        ops: Sequence[Mapping[str, Any]],
    ) -> list[dict]:
        """Validate the ops shape + reject overlapping paths; return normalized op dicts.

        Raises :class:`ChangeOpError` (caller-safe, BEFORE any DynamoDB call) on: an empty list, a
        non-mapping op, an unknown action, a missing/empty path, a blank path segment, a ``SET``
        without a ``value`` key, or OVERLAPPING paths (one path a prefix of another, or duplicate).
        """
        if not ops:
            raise ChangeOpError("at least one Change-Op is required (empty op set)")

        normalized: list[dict] = []
        for index, op in enumerate(ops):
            if not isinstance(op, Mapping):
                raise ChangeOpError(f"op #{index} is malformed (not an object)")
            action = op.get("action")
            if action not in _VALID_ACTIONS:
                raise ChangeOpError(
                    f"op #{index} has an unknown action {action!r} "
                    f"(expected one of {sorted(_VALID_ACTIONS)!r})"
                )
            path = op.get("path")
            if not isinstance(path, (list, tuple)) or len(path) == 0:
                raise ChangeOpError(
                    f"op #{index} has an empty or malformed path (expected a non-empty "
                    f"list of key segments)"
                )
            segments = [str(seg) for seg in path]
            for seg in segments:
                if seg == "":
                    raise ChangeOpError(
                        f"op #{index} has a blank path segment — every segment must be "
                        f"a non-empty key name"
                    )
            entry: dict = {"action": action, "path": tuple(segments)}
            if action == SET:
                if "value" not in op:
                    raise ChangeOpError(
                        f"op #{index} is a SET but carries no 'value'"
                    )
                entry["value"] = op["value"]
            normalized.append(entry)

        _reject_overlapping_paths([e["path"] for e in normalized])
        return normalized

    def _build_update_expression(
        self,
        normalized: list[dict],
        new_version: str,
        base_version: str | None,
        client_op_id: str | None,
    ) -> dict:
        """Build the combined SET/REMOVE UpdateExpression + version ConditionExpression + the
        ExpressionAttributeNames/Values maps for ONE ``update_item`` (design C2/D5).

        Every path segment binds via a ``#n<i>`` name placeholder (so dotted override keys are
        literal, never a nested path). ``version`` (and, when supplied, ``last_client_op_id``) are
        SET in the same SET clause so the lock-and-bump is atomic.
        """
        names: dict[str, str] = {}
        values: dict[str, Any] = {}
        name_cache: dict[str, str] = {}

        def bind_name(segment: str) -> str:
            # Reuse one placeholder per distinct segment text so the names map stays compact and a
            # repeated key (e.g. the "overrides" parent across ops) binds once.
            if segment in name_cache:
                return name_cache[segment]
            placeholder = f"#n{len(name_cache)}"
            name_cache[segment] = placeholder
            names[placeholder] = segment
            return placeholder

        def bind_value(val: Any) -> str:
            placeholder = f":v{len(values)}"
            values[placeholder] = val
            return placeholder

        set_clauses: list[str] = []
        remove_clauses: list[str] = []
        for op in normalized:
            path_expr = ".".join(bind_name(seg) for seg in op["path"])
            if op["action"] == SET:
                set_clauses.append(f"{path_expr} = {bind_value(op['value'])}")
            else:  # REMOVE
                remove_clauses.append(path_expr)

        # Bump version in the SAME expression (atomic lock-and-bump, D5).
        version_name = bind_name(schema.VERSION_ATTR)
        set_clauses.append(f"{version_name} = {bind_value(new_version)}")

        # Idempotency stamp — only when the caller supplies a token (task 4.2 hook).
        if client_op_id is not None:
            op_id_name = bind_name(_CLIENT_OP_ID_ATTR)
            set_clauses.append(f"{op_id_name} = {bind_value(client_op_id)}")

        update_parts: list[str] = []
        if set_clauses:
            update_parts.append("SET " + ", ".join(set_clauses))
        if remove_clauses:
            update_parts.append("REMOVE " + ", ".join(remove_clauses))
        update_expression = " ".join(update_parts)

        # Version-conditional guard (D5). Bind the key segment the chosen condition references
        # (`version` for cases i/ii, `sk` for case iii) through the SAME names map, then render.
        if base_version is None:
            # (iii) no row yet — first write onto the skeleton.
            sk_name = bind_name(schema.SORT_KEY_ATTR)
            condition_expression = f"attribute_not_exists({sk_name})"
        elif base_version == LEGACY_NO_VERSION:
            # (ii) existing legacy row with no version attribute.
            legacy_name = bind_name(schema.VERSION_ATTR)
            condition_expression = f"attribute_not_exists({legacy_name})"
        else:
            # (i) existing row with a version — optimistic lock on the base the caller read.
            base_name = bind_name(schema.VERSION_ATTR)
            values[":base"] = base_version
            condition_expression = f"{base_name} = :base"

        return {
            "UpdateExpression": update_expression,
            "ConditionExpression": condition_expression,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }

    def _is_idempotent_replay(self, key: dict, client_op_id: str) -> bool:
        """True when the stored row's ``last_client_op_id`` already equals ``client_op_id``.

        A lost-response retry: the original write SUCCEEDED (stamping this op id + the new version),
        the response was lost, and the caller retried with a now-stale base version. Recognising the
        op id lets the retry return success instead of a spurious self-409 (review Should-fix).
        """
        item = self._get_item(key)
        return bool(item) and item.get(_CLIENT_OP_ID_ATTR) == client_op_id

    def _read_version(self, key: dict) -> str | None:
        """Return the stored ``version`` for the row (used to report back on an idempotent replay)."""
        item = self._get_item(key)
        return item.get(schema.VERSION_ATTR) if item else None

    def _get_item(self, key: dict) -> dict:
        """Read one row by key (consistent) — the idempotency re-read. Empty dict when absent."""
        response = self.table.get_item(Key=key, ConsistentRead=True)
        return response.get("Item") or {}

    # ──────────────────────────────────────────────────────────────────────────────────
    # Runtime truncation tripwire (spec 03, task 8.4 / R11.5) — last-line defense
    # ──────────────────────────────────────────────────────────────────────────────────

    def _assert_no_silent_truncation(
        self, key: dict, normalized: list[dict]
    ) -> None:
        """Refuse a ``config#fields`` op set that would SILENTLY shrink the catalog (R11.5).

        The RULE (per bucket — the group catalog and the field set independently):

            projected_count  >=  base_count  -  explicit_whole_entry_deletes

        where ``base_count`` is the stored (current) number of entries in the bucket,
        ``projected_count`` is what that bucket's count becomes after the ops apply, and
        ``explicit_whole_entry_deletes`` is the number of ``REMOVE`` ops that target a WHOLE entry
        in that bucket (a ``delete_field`` / ``delete_group`` / ``reset_field``). In other words: a
        reduction is allowed only up to the number of explicit deletes issued. A drop BEYOND that —
        a count falling with no delete op to account for it — is a SILENT truncation and is refused.

        Buckets (matching the stored shape + the reader's count):
          * groups → keys of the ``functional_groups`` map; whole-entry path ``["functional_groups", gkey]``.
          * fields → keys of ``fields`` (variable) + keys of ``overrides`` (base/calc) maps; whole-entry
            paths ``["fields", key]`` and ``["overrides", dotted]``.

        Attribute-level ops (path length >= 3, e.g. ``["fields", k, "label"]``) and ``SET`` of a NEW
        whole entry (growth) never reduce a count, so this never fires on a legitimate edit or on the
        empty→populated C6 first write (a GROWTH). It reads the CURRENT stored row consistently; an
        absent row (count 0) can only grow, so nothing trips.

        Raises:
            TruncationTripwireError: a projected bucket count would fall below the stored count by
                MORE than the explicit whole-entry deletes in this request — no write performed.
        """
        stored = self._get_item(key)

        for bucket_label, parent_keys in (
            ("groups", ("functional_groups",)),
            ("fields", ("fields", "overrides")),
        ):
            base_count = _bucket_entry_count(stored, parent_keys)
            projected_count, explicit_deletes = _project_bucket(
                stored, parent_keys, normalized
            )
            # Allowed floor: the base count minus whatever explicit deletes legitimately remove.
            allowed_floor = base_count - explicit_deletes
            if projected_count < allowed_floor:
                raise TruncationTripwireError(
                    "config write refused: the change would reduce the "
                    f"{bucket_label} count from {base_count} to {projected_count} "
                    f"with only {explicit_deletes} explicit delete(s) — a silent "
                    "truncation. No change was made (reload and retry)."
                )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers (no boto3; pure logic)
# ─────────────────────────────────────────────────────────────────────────────


def _reject_overlapping_paths(paths: list[tuple[str, ...]]) -> None:
    """Reject a Change-Op set whose paths overlap (design C2 multi-op semantics).

    Two paths OVERLAP when one is a prefix of (or identical to) the other, e.g.
    ``("overrides", "x")`` and ``("overrides", "x", "label")`` — DynamoDB would fail with
    "Two document paths overlap near …" on the expression, but we catch it first so the error
    is intelligible + BEFORE the call (caller-safe, no side effects).

    Raises :class:`ChangeOpError` naming BOTH paths so the caller can fix.
    """
    for i, a in enumerate(paths):
        for j, b in enumerate(paths):
            if i >= j:
                continue
            # a is a prefix of b (or vice versa) when slicing yields equality.
            shorter = min(len(a), len(b))
            if a[:shorter] == b[:shorter]:
                raise ChangeOpError(
                    f"document paths overlap: {list(a)} and {list(b)} — DynamoDB "
                    f"would reject this; split into separate calls"
                )


def _bucket_entry_count(stored: Mapping[str, Any], parent_keys: tuple[str, ...]) -> int:
    """Count the entries a truncation bucket holds in the STORED row (task 8.4 / R11.5).

    A bucket is one or more stored parent maps (``functional_groups`` for the group catalog;
    ``fields`` + ``overrides`` for the field set). The count is the total number of keys across
    those maps. A missing / non-map parent contributes 0 (an unauthored row is empty, not an
    error — it can only grow, so it never trips the tripwire)."""
    total = 0
    for parent in parent_keys:
        value = stored.get(parent)
        if isinstance(value, Mapping):
            total += len(value)
    return total


def _project_bucket(
    stored: Mapping[str, Any],
    parent_keys: tuple[str, ...],
    normalized: list[dict],
) -> tuple[int, int]:
    """Project a bucket's post-write entry count + count explicit whole-entry deletes (R11.5).

    Walks the normalized ops and applies ONLY those that change the ENTRY COUNT of a map in this
    bucket — i.e. ops whose path is exactly ``[parent, entry_key]`` (a WHOLE entry), for a parent in
    ``parent_keys``:
      * ``SET`` of a whole entry whose key is NOT already present → +1 (growth / create).
      * ``SET`` of a whole entry whose key IS already present → 0 (replace in place).
      * ``REMOVE`` of a whole entry that IS present → -1, AND counts as one explicit delete.
    Attribute-level ops (path length != 2, e.g. ``[parent, key, attr]``) never change the entry
    count and are ignored here. Ops targeting a different bucket's parents are ignored.

    Returns ``(projected_count, explicit_whole_entry_deletes)`` — the projected total entry count
    across the bucket's maps after the ops, and how many of the ops were whole-entry REMOVEs (the
    legitimate deletes the tripwire allows the count to drop by)."""
    # Per-parent entry-key sets, started from what is actually stored, then mutated by the ops so
    # the projected count reflects the post-write state. A WHOLE-PARENT op (path length 1) replaces
    # or removes the entire map — that is the classic silent-truncation vector (the "replace the
    # whole fields/functional_groups map with a partial payload" bug this spec exists to kill), so
    # it MUST be scored, not ignored.
    present: dict[str, set] = {}
    for parent in parent_keys:
        value = stored.get(parent)
        present[parent] = set(value.keys()) if isinstance(value, Mapping) else set()

    explicit_deletes = 0

    for op in normalized:
        path = op["path"]
        parent = path[0]
        if parent not in present:
            continue  # not this bucket

        if len(path) == 1:
            # WHOLE-PARENT op — replaces/removes the entire map (the truncation vector). The
            # Change-Op model should NEVER emit this (it addresses individual entries); if a logic
            # bug does, score it by the new value's entry count so a partial payload is caught.
            if op["action"] == SET:
                new_value = op["value"]
                present[parent] = (
                    set(new_value.keys()) if isinstance(new_value, Mapping) else set()
                )
            else:  # REMOVE of the whole parent map — zero entries left
                present[parent] = set()
            continue

        if len(path) != 2:
            continue  # attribute-level op (len >= 3) — does not change entry count

        entry_key = path[1]
        keys = present[parent]
        if op["action"] == SET:
            # Add a NEW entry (growth); a SET on an existing key replaces in place (no change).
            keys.add(entry_key)
        else:  # REMOVE of a whole entry — an explicit, legitimate delete
            keys.discard(entry_key)
            explicit_deletes += 1

    projected = sum(len(keys) for keys in present.values())
    return projected, explicit_deletes


def _client_error_code(exc: BaseException) -> str:
    """Best-effort ``ClientError`` code extraction (empty string when unavailable).

    Duck-typed so this helper works whether or not botocore types are on the import path
    (mirrors the established pattern in ``mail_send_adapters.py``).
    """
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            return str(error.get("Code", ""))
    return ""
