"""
Members mail — the **send-run STATUS read service** (mail spec Task 3.2; R9.2/R9.3/R9.6;
design "Components and Interfaces" / Property 3).

ONE storage-agnostic Members-domain component that backs the two READ routes

    GET /members/mail-runs            → the tenant's send-run tallies (newest first)
    GET /members/mail-runs/{run_id}   → one run's tally + its FAILURE drill-down

over the tenant-pinned repository methods task 3.1 shipped (``list_mail_runs`` /
``get_mail_run`` / ``list_mail_run_failures``). Its whole job is the R9.3 **role-scoped
filtering** the status/history screen needs, applied to the SAME tenant-scoped data:

    *The SENDING USER sees the status of their OWN sends; a TENANT ADMIN sees ALL the
     tenant's sends.*

Where it sits (steering 35)
---------------------------
Thin edge handler → THIS service (the scope decision) → the repository seam (the sole
DynamoDB touch-point, tenant-pinned). It is NOT the handler (the handler resolves WHO the
caller is — the verified ``sub`` + whether they hold ``members:admin`` — and maps a missing
run to a 404) and NOT the repository (the repository pins ``tenant_id`` and never decides
scope). It names no boto3, no DynamoDB — only the :class:`MailRunStore` Protocol.

The scope decision — a BOOLEAN the EDGE computes (verify-before-trust)
----------------------------------------------------------------------
WHO may see ALL the tenant's runs vs only their OWN is an AUTHORIZATION fact that derives
from the VERIFIED entitlement (``members:admin``), so the EDGE computes it (via the
three-state ``has_capability`` over the verified claims) and hands this service a plain
``admin`` boolean. The service never reads a token/claim/header itself (it has no business
touching auth material); it just applies the rule:

- ``admin=True``  → return EVERY run in the tenant (oversight, R9.3).
- ``admin=False`` → return ONLY the runs the caller triggered (``triggered_by == sub``).

Tenancy (Property 3)
--------------------
``tenant_id`` is AUTHORITATIVE on every call — the repository pins it, so a run only ever
matches within its own tenant and no cross-tenant read is possible even for an admin. The
own-sends filter is an ADDITIONAL narrowing WITHIN the tenant, never a widening.

Drill-down scoping (R9.3)
-------------------------
``get_run`` applies the SAME scope: a plain user may only drill into a run they triggered;
a run that exists in the tenant but was triggered by someone else is reported as absent
(``None``) to a non-admin — deliberately indistinguishable from "no such run" so a scoped
caller cannot probe for another user's runs (mirrors the member-read not-found policy). An
admin may drill into any run in the tenant.

Pure / injectable (design "Pure/injectable")
--------------------------------------------
The service depends only on the injected :class:`MailRunStore` seam (the SAM-plane concrete
is :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository`, which
satisfies it by duck-typing). No I/O of its own; a unit test drives it with an in-memory
fake repo and no AWS.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "MailRunStatusService",
    "MailRunStore",
    "MailRunView",
]


@runtime_checkable
class MailRunStore(Protocol):
    """The minimal, tenant-pinned read seam this service needs (design C6).

    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` satisfies
    this by duck-typing (the task-3.1 ``list_mail_runs`` / ``get_mail_run`` /
    ``list_mail_run_failures`` methods). Every method is keyed by ``tenant_id`` so the
    service cannot reach another tenant's data even by mistake (Property 3).
    """

    def list_mail_runs(self, tenant_id: str) -> Sequence[Mapping[str, Any]]:
        """List the tenant's send-run tallies, newest first."""
        ...

    def get_mail_run(
        self, tenant_id: str, run_id: str
    ) -> Mapping[str, Any] | None:
        """Return a run's tally for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_mail_run_failures(
        self, tenant_id: str, run_id: str
    ) -> Sequence[Mapping[str, Any]]:
        """List a run's FAILURE sub-records, tenant-pinned."""
        ...

    def delete_mail_run(self, tenant_id: str, run_id: str) -> None:
        """Manual-delete a run tally AND all its FAILURE sub-records, tenant-pinned (R9.6)."""
        ...


@dataclass(frozen=True)
class MailRunView:
    """One run's tally + its FAILURE drill-down — the single-run read's shape (R9.2).

    ``run`` is the aggregated ``mailrun#`` tally (``mode`` / ``triggered_by`` /
    ``recipient_count`` / ``status`` / ``sent`` / ``failed`` / timestamps). ``failures`` is
    the list of FAILURE sub-records (``address`` / ``status`` / ``reason`` / ``message_id``) —
    empty for a run with no failures (the common case: successes are only COUNTED in the
    tally, never stored per-recipient). The edge shapes this into the JSON the screen renders.
    """

    run: Mapping[str, Any]
    failures: tuple[Mapping[str, Any], ...]


class MailRunStatusService:
    """Role-scoped read of the Members send-run status records (R9.2/R9.3/R9.6).

    Backs the ``GET /members/mail-runs[/{run_id}]`` routes. The caller (the edge dispatch)
    supplies the AUTHORITATIVE ``tenant_id`` (from the verified entitlement), the verified
    ``sub`` (the caller's stable id — the ``triggered_by`` a run carries), and an ``admin``
    boolean the edge computed from the verified ``members:admin`` entitlement. The service
    applies the R9.3 scope: an admin sees all the tenant's runs; a plain user sees only the
    runs they triggered.
    """

    def __init__(self, store: MailRunStore):
        self._store = store

    @staticmethod
    def _owns(run: Mapping[str, Any], sub: str | None) -> bool:
        """True when ``run`` was triggered by ``sub`` (the own-sends predicate, R9.3).

        A run with no ``triggered_by`` (or a caller with no verified ``sub``) is NOT owned by
        a plain user — fail-closed, so an attribution-less run is only ever visible to an
        admin, never leaked to an arbitrary non-admin caller.
        """
        if not sub:
            return False
        return run.get("triggered_by") == sub

    def list_runs(
        self, tenant_id: str, *, requester_sub: str | None, admin: bool
    ) -> list[Mapping[str, Any]]:
        """List the runs visible to the caller — all (admin) or own (plain user), R9.3.

        Reads the tenant's tallies (newest first, tenant-pinned — Property 3) and, for a
        non-admin, narrows to the runs the caller triggered (``triggered_by == sub``). An
        admin sees the full tenant list (oversight). The tenant bound is the repository's; the
        own-sends filter is an additional narrowing WITHIN the tenant, never a widening.
        """
        runs = list(self._store.list_mail_runs(tenant_id))
        if admin:
            return runs
        return [r for r in runs if self._owns(r, requester_sub)]

    def get_run(
        self, tenant_id: str, run_id: str, *, requester_sub: str | None, admin: bool
    ) -> MailRunView | None:
        """Return one run's tally + its FAILURE drill-down, subject to the R9.3 scope.

        An admin may drill into any run in the tenant. A plain user may only drill into a run
        they triggered — a run that exists in the tenant but was triggered by someone else is
        reported as ``None`` (absent), deliberately indistinguishable from "no such run" so a
        scoped caller cannot probe for another user's runs. A truly absent run is ``None`` for
        everyone. The failure sub-records are only read once visibility is established, so an
        out-of-scope caller never even observes another user's failure detail.
        """
        run = self._store.get_mail_run(tenant_id, run_id)
        if run is None:
            return None
        if not admin and not self._owns(run, requester_sub):
            # Exists in the tenant but not the caller's own run → report as absent (no probe).
            return None
        failures = tuple(self._store.list_mail_run_failures(tenant_id, run_id))
        return MailRunView(run=run, failures=failures)

    def delete_run(
        self, tenant_id: str, run_id: str, *, requester_sub: str | None, admin: bool
    ) -> bool:
        """Manually delete one send-run, subject to the SAME R9.3 scope as :meth:`get_run`.

        The manual-delete half of the R9.6 retention model (design "Resolved implementation
        choices"): the user/admin may purge a run from the status screen before the TTL fires.
        Visibility is resolved EXACTLY as a read — an admin may delete any run in the tenant; a
        plain user may delete only a run they triggered (``triggered_by == sub``). A run that is
        truly absent, OR exists in the tenant but was triggered by someone else and the caller is
        not an admin, is NOT deleted and returns ``False`` (the not-visible signal) — deliberately
        indistinguishable, so a scoped caller cannot probe for (or destroy) another user's runs,
        and the edge maps the signal to a 404 (no probe) rather than confirming existence.

        Only once visibility is established does it delegate to the repository's tenant-pinned
        :meth:`MailRunStore.delete_mail_run`, which removes the ``mailrun#`` tally AND all its
        ``mailrecipient#`` FAILURE sub-records in one op (no orphaned failures). ``tenant_id`` is
        authoritative on every touch (Property 3) — no cross-tenant delete even for an admin.
        """
        run = self._store.get_mail_run(tenant_id, run_id)
        if run is None:
            return False
        if not admin and not self._owns(run, requester_sub):
            # Exists in the tenant but not the caller's own run → not visible (no probe, no delete).
            return False
        self._store.delete_mail_run(tenant_id, run_id)
        return True
