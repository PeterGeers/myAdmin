"""
The Members **mail-send worker** package (R4, pivot-output-actions task 4.3).

The CONSUMER side of the R4 queued send path (design §4.2/§4.3). The ``deliver`` route
(task 4.2) + the R5 scheduler ENQUEUE send jobs to ``MailSendQueue``; this package drains
that queue and does the actual SES send so the request never blocks on it:

    render (mail-merge per recipient / attach for to_fixed) → SES send →
    metadata-only audit (log_analytics_output / ses_mail) →
    idempotent on redelivery (stable job id, dedupe) → retry → DLQ after N.

Layering (steering 35): the Lambda entrypoint :mod:`sam.members.worker.app` is a THIN
adapter (parse the SQS event → deserialize the envelope → delegate → report partial-batch
failures); the business logic lives in the :class:`~sam.members.worker.mail_send_worker.
MailSendWorker` service, which depends only on injected ports (an SES sender, a dedupe
marker store, the template service, and an audit sink). No boto3 / SQS / SES wiring lives
in the service — the production ports resolve lazily at the edge.
"""
