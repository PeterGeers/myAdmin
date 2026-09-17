"""On-change sync trigger + reconciliation backstop (design.md D3 R5.7, T21).

S3's projection (``ProjectionSync``, T16) is the one-directional MySQL->DynamoDB
copy of the tenant-level governance subset. It must run **on change** to the
source governance tables — not per request. This module is the "Change trigger"
named in design.md D3 "Components and interfaces": the seam the Flask-plane
governance write paths (provisioning / module enable-disable / role grant) call
**after a successful commit** to signal that a given ``administration`` changed,
so the projection tracks MySQL within a bounded, documented delay.

Two mechanisms, per design.md D3 "On-change sync trigger (R5.7)":

1. **On-change enqueue.** A governance write that mutates ``tenants`` /
   ``tenant_modules`` / ``user_tenant_roles`` calls :func:`enqueue_sync` (or a
   :class:`ProjectionSyncTrigger` instance) with the affected ``administration``.
   The trigger records the affected tenant on a queue and — for the default
   in-process queue — drains it by running ``ProjectionSync.sync_administration``
   for that tenant.

2. **Reconciliation backstop.** :func:`reconcile` (a periodic pass) runs
   ``ProjectionSync.sync_all()``, which is idempotent (R5.6): re-running against
   an unchanged source is a no-op. This backstops any *missed* on-change signal
   (a crash between commit and enqueue, an enqueue failure, etc.), so the
   projection is **eventually consistent** with MySQL within the reconciliation
   interval even if a single signal is lost.

**Bounded-delay / eventual-consistency guarantee (documented, R5.7/R5.8).** The
projection is *eventually consistent* with MySQL. The bound on staleness is::

    max staleness  <=  on-change sync latency          (normal path)
                   OR  reconciliation interval          (if a signal is missed)

The on-change path advances the projection within one sync cycle of a committed
governance write. If that signal is lost, the periodic reconciliation pass (its
interval is the operational knob, e.g. every N minutes — a scheduler/cron
concern outside this module) closes the gap. Staleness is therefore never
unbounded; it is bounded by whichever of the two fires first. The read side
(T19) compares ``version`` and refreshes on a newer one (R5.8), so a converged
projection is observed by readers within their own TTL on top of this bound.

**Never breaks the governance write (design.md D3 / Error Handling).** The
trigger is called *after* the governance write has already committed. An enqueue
or drain failure MUST NOT propagate back into the governance write path — the
governance write already succeeded and MySQL is the system of record. A failure
here is **logged** and left for the reconciliation backstop to pick up. The
public :func:`enqueue_sync` therefore swallows and logs any exception; only the
lower-level :meth:`ProjectionSyncTrigger.enqueue` (used directly in tests with an
injected fake) surfaces errors, so tests can assert on them.

**One-directional / read-only discipline (R5.1/R5.2/R5.9).** This module issues
**zero** MySQL writes and **never** writes the projection table itself — it only
*signals* and delegates the actual DynamoDB write to ``ProjectionSync`` (the sole
writer). It holds no MySQL connection; the affected ``administration`` is passed
in by the caller (it must flow from the authenticated governance action — no
hardcoded tenant, workspace database-patterns / data-ownership).

**Dependency injection (testability, T22).** :class:`ProjectionSyncTrigger`
takes an optional ``queue`` and an optional ``sync`` (or a ``sync_factory``) so
the T22 convergence property test — and the unit tests here — can drive it with
an in-memory fake queue and a fake sync, never touching real AWS / MySQL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# --- Queue seam -------------------------------------------------------------


@runtime_checkable
class SyncQueue(Protocol):
    """A minimal enqueue seam for affected-``administration`` sync work.

    The default (:class:`InMemorySyncQueue`) is an in-process list drained
    synchronously; a production deployment could substitute a durable queue
    (SQS, a DB-backed outbox, ...) exposing the same one-method contract without
    touching the callers. Tests inject a fake to assert what was enqueued.
    """

    def enqueue(self, administration: str) -> None:
        """Record that ``administration`` needs a projection sync."""
        ...


class InMemorySyncQueue:
    """In-process, list-backed :class:`SyncQueue` (the Flask-monolith default).

    Appropriate for the single-process Flask monolith: the affected tenant is
    recorded and drained synchronously in the same process (see
    :class:`ProjectionSyncTrigger`). Records every enqueued ``administration`` so
    it is observable in tests and for light introspection.
    """

    def __init__(self) -> None:
        self._pending: list[str] = []

    def enqueue(self, administration: str) -> None:
        if not administration:
            raise ValueError(
                "administration must be non-empty — a blank tenant scope is a "
                "cross-tenant hazard (R5.4)"
            )
        self._pending.append(administration)

    def drain(self) -> list[str]:
        """Return and clear the pending administrations (FIFO order)."""
        pending, self._pending = self._pending, []
        return pending

    @property
    def pending(self) -> tuple[str, ...]:
        """The currently-pending administrations (read-only snapshot)."""
        return tuple(self._pending)


# --- Sync seam --------------------------------------------------------------


@runtime_checkable
class SyncLike(Protocol):
    """The subset of ``ProjectionSync`` the trigger drives.

    Kept narrow so tests can inject a fake that records calls without pulling in
    DynamoDB/MySQL. ``ProjectionSync`` satisfies this structurally.
    """

    def sync_administration(self, administration: str) -> Any: ...

    def sync_all(self) -> Any: ...


# --- The trigger ------------------------------------------------------------


class ProjectionSyncTrigger:
    """On-change trigger + reconciliation entry point for the projection (R5.7).

    Wraps a :class:`SyncQueue` and a :class:`SyncLike` sync. On
    :meth:`enqueue`, it records the affected ``administration`` and — for the
    in-process default queue — drains it immediately by running the sync for that
    tenant (so the projection tracks the change within one sync cycle). On
    :meth:`reconcile`, it runs the idempotent ``sync_all()`` backstop.

    The sync is resolved lazily (via ``sync_factory``) so constructing the
    trigger never forces DynamoDB/MySQL env resolution (R4.1) — only an actual
    enqueue/reconcile that needs to write does.

    Args:
        queue: The :class:`SyncQueue` to record affected tenants on. Defaults to
            a fresh :class:`InMemorySyncQueue`.
        sync: A ready :class:`SyncLike`. Optional — if omitted, ``sync_factory``
            builds one on first use.
        sync_factory: A zero-arg callable returning a :class:`SyncLike`. Used to
            defer construction of the real ``ProjectionSync`` (fail-fast env) to
            first use. Ignored when ``sync`` is provided.
        drain_on_enqueue: When True (default) an in-process enqueue is drained
            synchronously (the Flask-monolith path). Set False to only record and
            let a separate worker/reconciliation drain it.
    """

    def __init__(
        self,
        queue: SyncQueue | None = None,
        *,
        sync: SyncLike | None = None,
        sync_factory: Callable[[], SyncLike] | None = None,
        drain_on_enqueue: bool = True,
    ) -> None:
        self._queue: SyncQueue = queue if queue is not None else InMemorySyncQueue()
        self._sync = sync
        self._sync_factory = sync_factory
        self._drain_on_enqueue = drain_on_enqueue

    @property
    def queue(self) -> SyncQueue:
        """The underlying queue (exposed for tests/introspection)."""
        return self._queue

    def _resolve_sync(self) -> SyncLike:
        """Return the sync, building it from ``sync_factory`` on first use.

        Deferred so merely constructing the trigger never triggers the sync's
        fail-fast env resolution (R4.1). Raises if neither a sync nor a factory
        was provided and one is needed.
        """
        if self._sync is None:
            if self._sync_factory is None:
                raise RuntimeError(
                    "ProjectionSyncTrigger has no sync and no sync_factory — "
                    "cannot run a projection sync"
                )
            self._sync = self._sync_factory()
        return self._sync

    def enqueue(self, administration: str) -> None:
        """Record ``administration`` as needing a sync (and drain if in-process).

        This is the *raw* enqueue: it lets errors surface, so tests can assert on
        them and callers that want best-effort behaviour use the module-level
        :func:`enqueue_sync` wrapper instead.

        Args:
            administration: The affected tenant scope (must be non-empty).

        Raises:
            ValueError: ``administration`` is blank.
        """
        self._queue.enqueue(administration)
        if self._drain_on_enqueue and isinstance(self._queue, InMemorySyncQueue):
            self._drain()

    def _drain(self) -> None:
        """Run the sync for each pending administration (in-process default)."""
        pending = self._queue.drain()  # type: ignore[attr-defined]
        if not pending:
            return
        sync = self._resolve_sync()
        # De-dup while preserving order — collapsing repeated signals for the
        # same tenant is safe (the sync is idempotent, R5.6) and avoids redundant
        # work when several fields of one tenant change in quick succession.
        seen: set[str] = set()
        for administration in pending:
            if administration in seen:
                continue
            seen.add(administration)
            sync.sync_administration(administration)

    def reconcile(self) -> Any:
        """Run the idempotent reconciliation backstop (``sync_all``), R5.7/R5.6.

        The periodic pass that catches any *missed* on-change signal. Because the
        sync is idempotent, re-projecting an unchanged source is a no-op, so
        reconciliation is safe to run on any cadence.

        Returns:
            Whatever ``ProjectionSync.sync_all()`` returns (a ``SyncResult``).
        """
        return self._resolve_sync().sync_all()


# --- Module-level default + best-effort hook -------------------------------

#: The process-wide default trigger, lazily built on first use. Governance write
#: paths call :func:`enqueue_sync` / :func:`reconcile` which route through this,
#: so callers never construct a trigger or the sync themselves. Tests reset it
#: via :func:`set_default_trigger`.
_default_trigger: ProjectionSyncTrigger | None = None


def _build_default_trigger() -> ProjectionSyncTrigger:
    """Build the process default trigger backed by the real ``ProjectionSync``.

    The sync itself is built lazily (``sync_factory``) so importing this module
    or enqueuing before any config is loaded does not force the projection's
    fail-fast env resolution (R4.1) until a real sync is actually run.
    """

    def _factory() -> SyncLike:
        # Imported lazily to avoid a hard import-time dependency on the sync /
        # DynamoDB client and to keep this module cheap to import.
        from database import DatabaseManager
        from services.projection_sync import (
            DatabaseSourceProvider,
            ProjectionSync,
        )

        db = DatabaseManager()
        return ProjectionSync(DatabaseSourceProvider(db))

    return ProjectionSyncTrigger(sync_factory=_factory)


def get_default_trigger() -> ProjectionSyncTrigger:
    """Return the process-wide default trigger, building it on first use."""
    global _default_trigger
    if _default_trigger is None:
        _default_trigger = _build_default_trigger()
    return _default_trigger


def set_default_trigger(trigger: ProjectionSyncTrigger | None) -> None:
    """Override (or reset with ``None``) the process default trigger.

    Primarily for tests: inject a trigger backed by an in-memory queue + fake
    sync so a governance-write hook can be asserted without touching AWS/MySQL.
    """
    global _default_trigger
    _default_trigger = trigger


def enqueue_sync(administration: str | None) -> bool:
    """Best-effort on-change enqueue for a governance write path (R5.7).

    Call this **after** a governance write (provisioning / module enable-disable
    / role grant) has committed, passing the affected ``administration``. It
    routes to the process default trigger.

    **Never breaks the governance write.** The governance write has already
    committed; this is a downstream signal. Any failure (bad tenant value, queue
    error, sync error) is caught and logged, and the function returns ``False`` —
    the periodic :func:`reconcile` backstop will re-project the tenant later. It
    never re-raises into the caller.

    Args:
        administration: The affected tenant scope. A falsy value is logged and
            ignored (returns ``False``) rather than raising.

    Returns:
        ``True`` if the sync was enqueued/ran without error, ``False`` if it was
        skipped or failed (the reconciliation backstop covers the miss).
    """
    if not administration:
        logger.warning(
            "projection sync trigger: skipped enqueue for a blank administration "
            "— reconciliation will backstop"
        )
        return False
    try:
        get_default_trigger().enqueue(administration)
        return True
    except Exception as exc:
        # The governance write already committed; do NOT propagate. Log and let
        # the reconciliation backstop catch this tenant on its next pass.
        logger.warning(
            "projection sync trigger: enqueue failed for administration %r: %s "
            "— governance write is unaffected; reconciliation will backstop",
            administration,
            exc,
        )
        return False


def reconcile() -> Any:
    """Run the reconciliation backstop via the process default trigger (R5.7).

    Entry point for a periodic scheduler/cron. Runs the idempotent
    ``sync_all()`` so any missed on-change signal is corrected. Unlike
    :func:`enqueue_sync`, this surfaces errors to its (operational) caller so a
    scheduler can alert on a failing reconciliation.

    Returns:
        The ``SyncResult`` from ``ProjectionSync.sync_all()``.
    """
    return get_default_trigger().reconcile()
