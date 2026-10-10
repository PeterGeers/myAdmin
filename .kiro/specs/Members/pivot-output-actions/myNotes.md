 
---

## Phase 4 interim shims to finish later (found while building R4)

The queued send path (R4) is complete and green, but two pieces are honest interim
shims until the SAM-plane pivot/label engines exist (design §4.2/§12). Capture so they
are not forgotten:

1. **PivotRunner shim (tasks 4.1/4.2).** The deliver handler builds the
   `ExecuteAndDeliverService` with `_PassThroughPivotRunner` (result rows = member rows)
   because the pivot/list engine runs frontend/Flask-side today, not on the SAM plane. It
   satisfies the `PivotRunner` Protocol so it drops out unchanged when a real SAM-plane
   pivot engine lands. A `count` set currently would not aggregate server-side.
2. **pdf_labels attachment in the worker (task 4.3).** `MailSendWorker._build_pdf_labels`
   raises `MailSendPermanent` (loud DLQ signal) rather than send a corrupt PDF — the
   Avery label-layout generator is frontend-side (R6) and not yet on the SAM plane. CSV
   attachments work. Wire a SAM-plane label generator in when available.

Both are tracked design §12 open items; neither blocks TEST verification of the
per_recipient + to_fixed(csv) paths.
