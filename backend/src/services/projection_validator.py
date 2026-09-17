"""Write-time validation of S3 governance projection items (design.md D3, R5.5).

S3 (`s3-claims-and-projection`) builds a one-directional MySQL->DynamoDB
projection. Before the sync (T16) writes any item it MUST validate it. This
module is that gate — the ``ProjectionValidator`` named in design.md D3
("Components and interfaces" + "Write-time validation (R5.5)").

**Pure predicate (R5.5, PBT-friendly).** ``validate_item`` / ``is_valid_item``
perform **no** I/O — no DynamoDB, no MySQL, no env reads, no clock reads. An item
is valid *iff* its tenant key (partition key) is present and non-blank, its sort
key is present and well-formed, its version is present, and its required fields
are well-formed. Given the same input the same verdict is produced, so the T15
property test (Property 5) can drive it over a large generated input space
deterministically.

**Fail loudly, no partial write (design.md D3 "Write-time validation").** The
sync calls :func:`validate_item` on **every** item before writing. A source row
that projected to an item missing its tenant key or a required field causes the
sync to **fail loudly** for that item — :class:`ProjectionValidationError` is
raised and the item is NOT written. No silent partial/garbage projection: the
sync surfaces the failure (row identity, not secrets) rather than persisting
half-formed data.

**Key shape reuse (T11).** The canonical attribute names and the sort-key
"#"-join convention live solely in :mod:`services.projection_schema`
(``PARTITION_KEY_ATTR``, ``SORT_KEY_ATTR``, ``VERSION_ATTR``, ``split_sort_key``,
the record-type tokens). This validator does not redefine them — it validates
against that single source of truth so the builder (T12), validator (T14), sync
(T16), and read side (T19) cannot diverge.

**Scope — structural validity only.** This is a *structural* gate: it checks that
the key/version/required attributes are present and well-formed. It intentionally
does NOT re-derive business rules the builder (T12) already owns (e.g. the
SAM-backed-module projection gate) — its job is to stop a keyless/garbage item
from being written, which is the R5.5 guarantee.
"""

from __future__ import annotations

from typing import Any, Mapping

from services import projection_schema as schema
from services.projection_builder import ProjectionItem


class ProjectionValidationError(ValueError):
    """A projection item failed write-time validation (R5.5).

    Raised by :func:`validate_item` when an item is missing its tenant key or a
    required field, or a field is malformed. The message carries enough context
    to surface the failure — the item's identity (tenant + sort key when
    available) — but never secrets or full attribute dumps.

    Subclasses :class:`ValueError` so callers already catching ``ValueError``
    from the builder (T12) keep working, while the sync (T16) can catch this
    specific type to fail loudly per item.
    """


# Record types whose sort key MUST carry id segment(s) after the record type.
# A ``tenant`` record is keyed by the record type alone ("tenant"); ``module``
# and ``role`` records require at least one id segment (the module name, or the
# email + role) or the key is ambiguous / not well-formed.
_RECORD_TYPES_REQUIRING_ID_PARTS = frozenset(
    {schema.RECORD_TYPE_MODULE, schema.RECORD_TYPE_ROLE}
)


def _is_blank(value: Any) -> bool:
    """True iff a required string-like value is missing or effectively blank.

    ``None`` is blank; a string that is empty or only whitespace is blank. A
    non-string (e.g. an int version) is never "blank" here — presence checks for
    non-string required fields use ``is None`` at the call site instead.
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _identity(item: ProjectionItem) -> str:
    """Return a short, secret-free identity string for error context.

    Uses only the key fields (tenant + sort key) so a raised error can be traced
    to the offending row without dumping attribute values (which could carry
    tenant data). Falls back to ``<missing>`` for a blank part.
    """
    tenant = item.tenant_id if not _is_blank(item.tenant_id) else "<missing>"
    sort_key = item.sort_key if not _is_blank(item.sort_key) else "<missing>"
    return f"tenant_id={tenant!r} sort_key={sort_key!r}"


def _validate_sort_key_well_formed(item: ProjectionItem) -> None:
    """Raise if the sort key is missing or structurally malformed.

    Well-formed means: present and non-blank, and parseable by
    :func:`services.projection_schema.split_sort_key` into a record type plus the
    id segment(s) that record type requires (``module``/``role`` need at least
    one id segment; ``tenant`` needs none). Segments must themselves be non-blank.
    """
    if _is_blank(item.sort_key):
        raise ProjectionValidationError(
            f"projection item is missing its sort key ({_identity(item)}); "
            "a keyless item must not be written (R5.5)"
        )

    try:
        record_type, id_parts = schema.split_sort_key(item.sort_key)
    except ValueError as exc:  # pragma: no cover - split only raises on empty
        raise ProjectionValidationError(
            f"projection item has a malformed sort key ({_identity(item)}): {exc}"
        ) from exc

    if _is_blank(record_type):
        raise ProjectionValidationError(
            f"projection item sort key has a blank record type ({_identity(item)})"
        )

    if any(_is_blank(part) for part in id_parts):
        raise ProjectionValidationError(
            f"projection item sort key has a blank id segment ({_identity(item)})"
        )

    if record_type in _RECORD_TYPES_REQUIRING_ID_PARTS and not id_parts:
        raise ProjectionValidationError(
            f"projection item sort key for record type {record_type!r} is "
            f"missing its id segment(s) ({_identity(item)})"
        )


def _validate_required_attributes(item: ProjectionItem) -> None:
    """Raise if a record type's required non-key attributes are malformed.

    Per design.md D3 the record shapes are:

    - ``module#<name>``  -> requires a boolean ``is_active`` attribute.
    - ``role#<email>#<role>`` -> requires non-blank ``email`` and ``role``
      attributes matching the key.
    - ``tenant`` -> no additional required attributes (existence + tenant-level
      fields; those are optional passthrough).

    Only well-formedness of *required* fields is enforced; extra tenant-level
    attributes are allowed through untouched.
    """
    record_type, _id_parts = schema.split_sort_key(item.sort_key)
    attributes: Mapping[str, Any] = item.attributes or {}

    if record_type == schema.RECORD_TYPE_MODULE:
        if "is_active" not in attributes:
            raise ProjectionValidationError(
                f"module projection item is missing required 'is_active' "
                f"({_identity(item)})"
            )
        if not isinstance(attributes["is_active"], bool):
            raise ProjectionValidationError(
                f"module projection item 'is_active' must be a bool, got "
                f"{type(attributes['is_active']).__name__} ({_identity(item)})"
            )

    elif record_type == schema.RECORD_TYPE_ROLE:
        for required in ("email", "role"):
            if _is_blank(attributes.get(required)):
                raise ProjectionValidationError(
                    f"role projection item is missing required {required!r} "
                    f"({_identity(item)})"
                )


def validate_item(item: ProjectionItem) -> ProjectionItem:
    """Validate one projection item at write time, or raise (R5.5).

    Pure — no I/O, deterministic. Checks, in order:

    1. **Type** — ``item`` is a :class:`~services.projection_builder.ProjectionItem`.
    2. **Tenant key** — ``tenant_id`` (the partition key / tenancy boundary,
       R5.4) is present and non-blank. A blank tenant key is the primary
       cross-tenant hazard and must never be written.
    3. **Sort key** — present and well-formed (see :func:`_validate_sort_key_well_formed`).
    4. **Version** — ``version`` is present (not ``None``). The builder always
       attaches a deterministic version, so a ``None`` here means a malformed item.
    5. **Required attributes** — the record type's required fields are
       well-formed (see :func:`_validate_required_attributes`).

    On success the item is returned unchanged so callers can write
    ``validated = validate_item(item)`` inline. On any failure a
    :class:`ProjectionValidationError` is raised carrying the item's key identity
    (not secrets) so the sync (T16) can surface it and fail loudly for that item
    without writing partial/garbage data.

    Args:
        item: The projection item the sync intends to write.

    Returns:
        The same ``item``, when valid.

    Raises:
        ProjectionValidationError: The item is missing its tenant key, has a
            malformed sort key, is missing its version, or a required field is
            missing/malformed.
    """
    if not isinstance(item, ProjectionItem):
        raise ProjectionValidationError(
            f"validate_item expected a ProjectionItem, got {type(item).__name__}"
        )

    # 2) Tenant key (partition key) present + non-blank — the tenancy boundary.
    if _is_blank(item.tenant_id):
        raise ProjectionValidationError(
            "projection item is missing its tenant key (partition key); a blank "
            f"tenant is a cross-tenant hazard and must not be written (R5.4/R5.5) "
            f"({_identity(item)})"
        )

    # 3) Sort key present + well-formed.
    _validate_sort_key_well_formed(item)

    # 4) Version present (the builder always attaches one; None => malformed).
    if item.version is None:
        raise ProjectionValidationError(
            f"projection item is missing its version ({_identity(item)}); the "
            "versioned/idempotent write (R5.6) requires a version"
        )

    # 5) Record-type required attributes well-formed.
    _validate_required_attributes(item)

    return item


def is_valid_item(item: ProjectionItem) -> bool:
    """Return whether an item passes write-time validation, without raising.

    Convenience pure predicate wrapping :func:`validate_item` — useful for the
    T15 property test (Property 5) to partition generated items into valid /
    invalid without try/except boilerplate. The sync itself should call
    :func:`validate_item` so it fails loudly rather than silently skipping.

    Args:
        item: The projection item to test.

    Returns:
        ``True`` iff :func:`validate_item` would accept the item.
    """
    try:
        validate_item(item)
        return True
    except ProjectionValidationError:
        return False


def validate_items(items: "list[ProjectionItem]") -> "list[ProjectionItem]":
    """Validate a batch of items, failing loudly on the first invalid one (R5.5).

    Mirrors the sync's per-item write discipline: rather than silently dropping a
    bad item, the batch raises on the first :class:`ProjectionValidationError` so
    no partial/garbage projection is written. Callers that want atomic batch
    semantics validate the whole batch here *before* writing any item.

    Args:
        items: The projection items intended for a batch write.

    Returns:
        The same list, when every item is valid.

    Raises:
        ProjectionValidationError: The first item that fails validation.
    """
    for item in items:
        validate_item(item)
    return items
