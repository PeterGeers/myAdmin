"""``config#mail`` reads for the Members projection config reader (pivot-output-actions R0,
design §6.3; mail spec R4/R5; Member Application Form D26).

INTERNAL helper module of :mod:`sam.members.repository.projection_config_reader` — extracted
from the large reader class (code-quality file-length split, 2026-10-28) with **zero behaviour
change**. :class:`_MailConfigReadMixin` is composed into the public ``MembersProjectionReader``;
it relies on the shared read infrastructure from
:class:`_config_reader_base._ConfigReaderBase` (``_find_config_row``) resolved via the composed
class' MRO. Nothing imports this module directly except the reader facade.
"""

from __future__ import annotations

from collections.abc import Mapping

from sam.members.repository._config_reader_base import _CONFIG_ID_MAIL


class _MailConfigReadMixin:
    """The ``config#mail`` gate / sender / consent-notice reads (R0/R4/R5/D26)."""

    # ── Mail-enabled gate (pivot-output-actions R0, design §6.3) ───────────────────────

    def is_mail_enabled(self, tenant_id: str) -> bool:
        """Return whether the tenant is cleared to send mail, from ``config#mail`` (R0).

        Reads the tenant partition, finds the ``config#mail`` row (the per-tenant
        "mail-enabled / SES-certified" onboarding gate authored on the Flask plane
        as ``members.mail_enabled`` and projected by ``build_config_mail_row``), and
        returns its ``mail_enabled`` boolean. The Members edge calls this at request
        time to decide whether to offer the mail output actions (R1–R5) — a Lambda
        NEVER queries MySQL for the flag (ADR 0005/0006); it reads only this
        projected row.

        Fail-closed (R0): a **missing** ``config#mail`` row, a missing
        ``mail_enabled`` attribute, or any non-boolean-``True`` value all resolve to
        ``False``. The gate opens only on an explicit projected ``True`` — the
        absence of the projection never permits sending. Never raises on
        missing/empty data (empty-is-valid, same discipline as the sibling config
        readers).

        Args:
            tenant_id: The tenant (partition key) whose mail gate to resolve.

        Returns:
            ``True`` iff the tenant's projected ``config#mail`` row carries
            ``mail_enabled`` == ``True``; ``False`` otherwise (fail-closed).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return False
        return row.get("mail_enabled") is True

    # ── Per-tenant sender resolution fields (mail spec Task 0.3, R4/R5) ────────────────
    #
    # The same ``config#mail`` row that carries ``mail_enabled`` (task 0.2 extends
    # ``build_config_mail_row`` to project these alongside it). The pre-send certification
    # resolver (task 1.1) consumes these to compose From = ``<mail_local_part|noreply>@<mail_domain>``
    # and to read the certified gate. Each accessor reads from the SAME projected partition
    # as ``is_mail_enabled`` (one Query per tenant via the shared partition cache). Defaults
    # mirror the design Data Models: ``mail_local_part`` → ``"noreply"`` when absent;
    # ``mail_certified`` → ``False`` (fail-closed) when absent/malformed; ``mail_domain`` has
    # no safe default (it is authored at onboarding) → ``None`` when absent, which the
    # resolver treats as not-usable (no From can be composed).

    #: The default From local-part when a tenant has not authored ``mail_local_part``.
    _DEFAULT_MAIL_LOCAL_PART = "noreply"

    def get_mail_domain(self, tenant_id: str) -> str | None:
        """Return the tenant's projected ``mail_domain`` from ``config#mail`` (R4).

        The tenant's own mail domain (e.g. ``h-dcn.nl``), authored at onboarding and
        projected into the ``config#mail`` row. The pre-send resolver (task 1.1) uses it as
        the host of the composed From (``<local_part>@<domain>``).

        There is NO safe default for a domain — a wrong/guessed host would send from a
        foreign domain (the ``jabaki.nl`` regression, R4.2). So an **absent** ``config#mail``
        row, a missing attribute, or a non-string/empty value all resolve to ``None`` (not a
        placeholder); the resolver then refuses the send (fail-closed, no From composable).
        Never raises on missing/empty data (empty-is-valid, same discipline as the sibling
        config readers).

        Args:
            tenant_id: The tenant (partition key) whose mail domain to resolve.

        Returns:
            The projected ``mail_domain`` string, or ``None`` when absent/unusable.
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return None
        domain = row.get("mail_domain")
        if not isinstance(domain, str) or not domain:
            return None
        return domain

    def get_mail_local_part(self, tenant_id: str) -> str:
        """Return the tenant's projected ``mail_local_part`` from ``config#mail`` (R4).

        The From local-part (e.g. ``info``, ``onderhoud``) the tenant optionally authored at
        onboarding. **Default** ``"noreply"`` when the ``config#mail`` row is absent, the
        attribute is missing, or the value is a non-string/empty (design Data Models: the
        local-part is optional with a generic default, unlike the domain). The resolver
        composes From = ``<local_part>@<domain>``.

        Never raises on missing/empty data (empty-is-valid).

        Args:
            tenant_id: The tenant (partition key) whose From local-part to resolve.

        Returns:
            The projected ``mail_local_part`` string, or ``"noreply"`` when absent.
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return self._DEFAULT_MAIL_LOCAL_PART
        local_part = row.get("mail_local_part")
        if not isinstance(local_part, str) or not local_part:
            return self._DEFAULT_MAIL_LOCAL_PART
        return local_part

    def is_mail_certified(self, tenant_id: str) -> bool:
        """Return the tenant's projected ``mail_certified`` gate from ``config#mail`` (R5).

        The onboarding-recorded SES-verified flag (design "Option B"): the pre-send
        certification check reads THIS projected boolean rather than making a live SES call
        on the send path. (Option A — a live ``GetEmailIdentity`` at pre-send — is the noted
        future alternative; see the resolver docstring, task 1.1.)

        **Fail-closed** (R5.2/Property 4), identical discipline to ``is_mail_enabled``: a
        **missing** ``config#mail`` row, a missing ``mail_certified`` attribute, or any
        non-boolean-``True`` value (``"true"``, ``1``, ``"yes"``, …) all resolve to
        ``False``. The gate opens only on an explicit projected ``True`` — the absence of the
        projection never permits sending. Never raises on missing/empty data.

        Args:
            tenant_id: The tenant (partition key) whose certified gate to resolve.

        Returns:
            ``True`` iff the tenant's projected ``config#mail`` row carries
            ``mail_certified`` == ``True``; ``False`` otherwise (fail-closed).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return False
        return row.get("mail_certified") is True

    def get_mail_reply_to_default(self, tenant_id: str) -> str | None:
        """Return the tenant's projected ``mail_reply_to_default`` from ``config#mail`` (Task 5.1).

        The OPTIONAL tenant-authored Reply-To for SCHEDULED / unattended sends (a scheduled send
        has no invoking user). The send path uses this when present, and FALLS BACK to the
        composed From address when it is absent (an interactive send instead uses the invoking
        user's verified email at runtime). There is no fabricated default here — an **absent**
        ``config#mail`` row, a missing attribute, or a non-string/blank value all resolve to
        ``None`` so the caller applies the From fallback. Never raises on missing/empty data
        (empty-is-valid, same discipline as ``get_mail_domain``).

        Args:
            tenant_id: The tenant (partition key) whose scheduled-send Reply-To to resolve.

        Returns:
            The projected non-blank ``mail_reply_to_default`` string, or ``None`` when absent.
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return None
        reply_to = row.get("mail_reply_to_default")
        if isinstance(reply_to, str) and reply_to.strip():
            return reply_to
        return None

    def get_application_embed_origins(self, tenant_id: str) -> list[str]:
        """Return the tenant's projected ``application_embed_origins`` from ``config#mail`` (R5.2).

        The ONE tenant-authored embed-origin allow-list (authored onto ``config#mail`` by the
        builder's form-shell panel, shaped + validated on write by
        :meth:`sam.members.domain.config_write_service.ConfigWriteService._shape_embed_origins`).
        It feeds TWO distinct enforcement points that MUST read the SAME list so they cannot
        drift: the CloudFront form's CSP ``frame-ancestors`` (task 5.2, at the edge) and the SAM
        public API CORS ``Access-Control-Allow-Origin`` (task 5.3, consumed here by
        :func:`sam.members.handler.public_app._tenant_embed_origins`). This is the SAM read side
        of that list.

        The written attribute is ALREADY trimmed + de-duplicated (first-seen order) by the write
        shaper, so this read is a verbatim pass-through with the SAME conservative guards as the
        public-edge CORS convention (``public_app._allowed_origins``: trim + de-dupe, NO scheme
        check). Re-trimming + re-de-duping here is belt-and-suspenders so a stray stored value
        (a hand-edited row, a legacy entry) never surfaces a blank or duplicate origin.

        **Empty-is-valid / fail-safe — never raises** (same discipline as ``get_mail_domain``):
        an absent ``config#mail`` row, a missing attribute, a non-list value, or a list with no
        usable (non-blank string) entries all resolve to ``[]`` = standalone (no cross-origin
        embed permitted for this tenant). A per-request flood never crashes the CORS decision.

        Args:
            tenant_id: The tenant (partition key) whose embed-origin allow-list to resolve.

        Returns:
            The projected embed origins as a trimmed, de-duplicated list, or ``[]`` when
            absent/unusable (fail-safe — the tenant permits no cross-origin embed).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return []
        raw = row.get("application_embed_origins")
        if not isinstance(raw, (list, tuple)):
            return []
        origins: list[str] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, str):
                continue
            origin = entry.strip()
            if origin and origin not in seen:
                seen.add(origin)
                origins.append(origin)
        return origins

    # ── Tenant consent notice (Member Application Form D26/R12.1a/R12.1c, task 2.6) ────
    #
    # The per-tenant, bilingual, VERSIONED consent/privacy notice the tenant authored on the
    # Flask plane (``members.application_consent_notice``) and projected onto the SAME
    # ``config#mail`` row by ``build_config_mail_row`` / ``_resolve_application_consent_notice``
    # (task 8.2). Projected shape: ``{"version": <str>, "text": {<locale>: <body>, …}}``, present
    # ONLY when the tenant authored a well-formed notice (a non-blank version AND at least one
    # non-blank locale body); OMITTED otherwise so an un-authored tenant projects a
    # back-compatible row. These two accessors are the SAM read side (the task's
    # ``get_consent_notice`` / version accessor), mirroring ``get_mail_domain`` /
    # ``is_mail_enabled``: one shared partition Query (cached), empty-is-valid, never raises.

    def get_consent_notice(self, tenant_id: str) -> dict | None:
        """Return the tenant's projected consent notice from ``config#mail`` (D26/R12.1c).

        The public field-config read (R5) serves this notice's current text + version to the
        form; :meth:`get_consent_notice_version` reads the version alone for the server-side
        consent stamp (task 2.6). Returns ``{"version": <str>, "text": {<locale>: <body>, …}}``
        when the tenant authored a well-formed notice, else ``None`` (un-authored / malformed /
        absent row — the platform MAY seed a default elsewhere, R12.1c).

        **Degrades gracefully — never raises** (same discipline as ``get_mail_domain``): an
        absent ``config#mail`` row, a missing / non-mapping ``consent_notice`` attribute, a
        missing / blank ``version``, or an empty / non-mapping ``text`` all resolve to ``None``.
        Only non-blank string locale bodies survive into the returned ``text`` map, so a served
        notice body is always ``{str: str}`` — the symmetric read-side guard to the Flask
        builder's ``_resolve_application_consent_notice`` (task 8.2) so a stray stored value
        never surfaces a broken notice.

        Args:
            tenant_id: The tenant (partition key) whose consent notice to resolve.

        Returns:
            The projected ``{"version", "text"}`` notice, or ``None`` when absent/unusable.
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return None
        notice = row.get("consent_notice")
        if not isinstance(notice, Mapping):
            return None
        version = notice.get("version")
        if not isinstance(version, str) or not version.strip():
            return None
        raw_text = notice.get("text")
        if not isinstance(raw_text, Mapping):
            return None
        text = {
            str(locale): body
            for locale, body in raw_text.items()
            if isinstance(locale, str)
            and locale.strip()
            and isinstance(body, str)
            and body.strip()
        }
        if not text:
            return None
        return {"version": version.strip(), "text": text}

    def get_consent_notice_version(self, tenant_id: str) -> str | None:
        """Return the CURRENT version id of the tenant's consent notice, or ``None`` (R12.1a).

        The server-authoritative half of the consent stamp (task 2.6): ``create_application``
        records THIS version — the tenant's current notice version, resolved server-side — on
        the application record, NEVER a client-supplied ``notice_version``, so a later notice
        revision never retroactively changes an existing record's recorded version (R12.1a).

        ``None`` when the tenant has authored no well-formed notice (delegates to
        :meth:`get_consent_notice`); the caller decides how a tenant-with-no-notice behaves
        (task 2.6 still records the applicant's affirmative acceptance with a ``None`` version
        rather than failing the submit — the notice text is the tenant's concern, the
        affirmative consent is the applicant's). Never raises.

        Args:
            tenant_id: The tenant (partition key) whose current notice version to resolve.

        Returns:
            The current notice ``version`` string, or ``None`` when no notice is authored.
        """
        notice = self.get_consent_notice(tenant_id)
        if notice is None:
            return None
        return notice.get("version")

    # ── Full config#mail body (the typed Mail authoring read, spec 02 task 7.1 fix) ────

    def get_mail_config(self, tenant_id: str) -> dict:
        """Return the full reader-shaped ``config#mail`` body for the typed Mail authoring form.

        The AUTHORITATIVE read-back for the SAM-owned mail scalars: the typed Mail function
        (``MembersMailConfigEditor``) loads its initial values from THIS (surfaced on
        ``GET /members/field-config`` as ``mail_config``) instead of the legacy MySQL
        ``members.*`` params — those are SAM-owned now (``mail_reply_to_default`` is SAM-only
        net-new; the rest are being retired), so MySQL is the wrong source and a saved value
        would read back blank. Composing the body here from the SAME accessors the write path /
        builder use means the authoring form reads exactly what was written (writer/reader cannot
        drift).

        Shape mirrors ``build_config_mail_row`` / ``ConfigWriteService._validate_mail_body`` and
        the SAM accessors EXACTLY: ``mail_enabled`` / ``mail_local_part`` / ``mail_certified`` are
        ALWAYS present (fail-closed bools; ``mail_local_part`` defaults to ``"noreply"``), while
        ``mail_domain`` / ``mail_reply_to_default`` / ``consent_notice`` are included ONLY when
        authored (a non-``None`` accessor result), so an un-authored tenant yields the
        back-compatible minimal body. Empty-is-valid / fail-closed: a missing ``config#mail`` row
        yields the safe defaults (not-enabled, not-certified, ``noreply``, no domain/reply-to/
        notice) rather than raising. All six accessors share the per-invocation partition cache,
        so this resolves in a single Query.

        Args:
            tenant_id: The tenant (partition key) whose mail config to resolve.

        Returns:
            The reader-shaped ``config#mail`` body (always a dict; never raises).
        """
        body: dict = {
            "mail_enabled": self.is_mail_enabled(tenant_id),
            "mail_local_part": self.get_mail_local_part(tenant_id),
            "mail_certified": self.is_mail_certified(tenant_id),
        }
        domain = self.get_mail_domain(tenant_id)
        if domain is not None:
            body["mail_domain"] = domain
        reply_to = self.get_mail_reply_to_default(tenant_id)
        if reply_to is not None:
            body["mail_reply_to_default"] = reply_to
        consent_notice = self.get_consent_notice(tenant_id)
        if consent_notice is not None:
            body["consent_notice"] = consent_notice
        return body
