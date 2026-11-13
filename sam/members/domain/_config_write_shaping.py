"""Scope/mail body validation and embed-origin/consent shaping.
Part of ConfigWriteService (task 9).
"""

from __future__ import annotations

from collections.abc import Mapping

from ._config_write_shared import (
    _EMBED_ORIGIN_MAX_LEN,
    _EMBED_ORIGIN_RE,
    _EMBED_ORIGINS_MAX_COUNT,
    ConfigWriteValidationError,
)


class ConfigWriteShapingMixin:
    """Scope/mail body validation and embed-origin/consent shaping."""

    def _validate_scope_body(self, body: Mapping) -> dict:
        """Validate + shape a ``config#scope`` body into the reader's ``get_scope_config`` shape.

        The SAM-owned ``config#scope`` row is ``{"dimensions": [ <ScopeDimension dict>, … ]}`` —
        the exact shape ``MembersProjectionReader.get_scope_config`` reads back (R8.1). The frontend
        scope-save mirror (task 3.1a) writes the already-derived dimension set here as the
        AUTHORITATIVE source; this service shape-checks it and authors the ``dimensions`` attribute
        ONLY. Validation is SHAPE-ONLY, mirroring ``_validate_fields_body`` (the reader degrades an
        individual malformed dimension gracefully, so the service checks the container shape, not
        every leaf):

        - ``dimensions`` — ``None`` / absent → ``[]`` (EMPTY is valid: a tenant-wide scope config,
          R8.5 / R1.6 — the reader resolves an empty list to tenant-wide, never an error);
        - otherwise a list whose every entry is a mapping (one dimension spec), carried through
          verbatim so the reader maps each onto a ``ScopeDimension`` 1:1.

        It never authors ``all_wildcard`` / ``multi_valued`` (s5d clean break, R8.1) — it does not
        add keys, it only passes the authored dimension specs through.
        """
        if not isinstance(body, Mapping):
            raise ConfigWriteValidationError(
                "config#scope body must be an object with a 'dimensions' list"
            )
        dimensions = self._validate_scope_dimensions(body.get("dimensions"))
        return {"dimensions": dimensions}

    @staticmethod
    def _validate_scope_dimensions(raw) -> list:
        """Validate the ``dimensions`` list; preserve each dimension spec verbatim.

        ``None`` / absent → ``[]`` (empty is valid = tenant-wide). Must be a list; each entry must
        be a mapping (a dimension spec: ``key`` / ``field`` / ``enabled`` / ``values`` / ``label`` /
        ``required_for``). Each spec is carried through unchanged — the reader normalizes defaults
        and ignores unknown keys, so the service does not reshape a dimension.
        """
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ConfigWriteValidationError("config#scope 'dimensions' must be a list")
        for entry in raw:
            if not isinstance(entry, Mapping):
                raise ConfigWriteValidationError(
                    "config#scope 'dimensions' entries must be objects"
                )
        return [dict(entry) for entry in raw]

    def _validate_mail_body(self, body: Mapping) -> dict:
        """Validate + shape a ``config#mail`` body into the reader's accessor shape (R9/R15).

        Authors ONLY the attributes the ``MembersProjectionReader`` mail accessors read back:
        ``mail_enabled`` / ``mail_certified`` / ``application_scope_copy`` (fail-closed bools —
        only an explicit ``True`` opens a gate), ``mail_local_part`` (default ``"noreply"``),
        ``mail_domain`` (NO safe default — omitted when blank so the pre-send resolver fails
        closed, R4.2), ``mail_reply_to_default`` (NEW, Task 5.1 — optional; omitted when blank;
        the scheduled/unattended-send Reply-To, falling back to the From when absent),
        ``application_embed_origins`` (NEW, Task 5.1 — the ONE tenant-authored embed-origin list
        that later feeds BOTH the CloudFront ``frame-ancestors`` and the SAM public API CORS;
        absent/empty writes nothing, a malformed list is rejected fail-loud, R5.2/R8), and
        ``consent_notice`` (the versioned bilingual notice — a truly absent notice writes nothing,
        back-compatible, but an INTENDED-but-malformed notice is REJECTED fail-loud, R8.2/R12.1).

        SHAPE-ONLY, fail-closed, mirroring the Flask ``build_config_mail_row`` so the SAM-written
        row is byte-for-byte what the reader expects — writer and builder cannot drift (R9). The
        boolean gates collapse any non-``True`` value to ``False`` (an absent/malformed gate can
        never silently permit sending).
        """
        if not isinstance(body, Mapping):
            raise ConfigWriteValidationError("config#mail body must be an object")

        attributes: dict = {
            # Fail-closed gates: only an explicit boolean True opens them (R0/R5.2).
            "mail_enabled": body.get("mail_enabled") is True,
            "mail_certified": body.get("mail_certified") is True,
            "application_scope_copy": body.get("application_scope_copy") is True,
            "mail_local_part": self._shape_mail_local_part(body.get("mail_local_part")),
        }

        # Domain: NO safe default — omit unless a non-blank string (a guessed host = a
        # foreign-sender leak, R4.2). The reader resolves a missing domain to None (fail-closed).
        domain = body.get("mail_domain")
        if isinstance(domain, str) and domain.strip():
            attributes["mail_domain"] = domain

        # Reply-To default (Task 5.1, R9): optional tenant-authored string for the
        # scheduled/unattended-send Reply-To. Omit unless a non-blank string so the send path
        # falls back to the From address when it is absent.
        reply_to = body.get("mail_reply_to_default")
        if isinstance(reply_to, str) and reply_to.strip():
            attributes["mail_reply_to_default"] = reply_to

        # Embed origins (Task 5.1, R5.2): ONE tenant-authored list `application_embed_origins`
        # that later feeds TWO distinct enforcement points — the CloudFront form's CSP
        # `frame-ancestors` (task 5.2) AND the SAM public API CORS `Access-Control-Allow-Origin`
        # (task 5.3). Absent / empty is back-compatible (write nothing = standalone, no origins);
        # an INTENDED-but-malformed list (non-list, or a non-string / blank-only entry) is REJECTED
        # fail-loud (R8 posture) rather than silently dropped, so a broken embed config surfaces.
        origins = self._shape_embed_origins(body.get("application_embed_origins"))
        if origins:
            attributes["application_embed_origins"] = origins

        # Consent notice (R8.2): a truly ABSENT notice (key omitted, or an empty/falsey value —
        # no authoring intent) writes nothing, back-compatible. But when the body INTENDS a notice
        # (the ``consent_notice`` key is present and non-empty) yet it is malformed (blank version,
        # or no non-blank locale text), REJECT with a clear error rather than silently omitting —
        # so an admin's broken notice surfaces instead of vanishing. When well-formed it projects
        # the SAME shape the reader's get_consent_notice reads.
        raw_consent_notice = body.get("consent_notice")
        if raw_consent_notice:  # key present AND non-empty → authoring intent
            consent_notice = self._shape_consent_notice(raw_consent_notice)
            if consent_notice is None:
                raise ConfigWriteValidationError(
                    "config#mail 'consent_notice' is malformed: it must carry a non-blank "
                    "'version' and at least one non-blank locale text under 'text'"
                )
            attributes["consent_notice"] = consent_notice

        return attributes

    @staticmethod
    def _shape_mail_local_part(raw) -> str:
        """``mail_local_part`` → a non-blank string, else the default ``"noreply"`` (R4)."""
        if isinstance(raw, str) and raw.strip():
            return raw
        return "noreply"

    @staticmethod
    def _shape_embed_origins(raw) -> list[str]:
        """Shape + VALIDATE ``application_embed_origins`` → trimmed, de-duplicated origins (R5.2, SEC-7).

        ONE tenant-authored list that later feeds TWO enforcement points (CloudFront
        ``frame-ancestors`` — task 5.2 — and the SAM public API CORS ``Access-Control-Allow-Origin``
        — task 5.3). This shaper is the single authoring guard for both; the consumers read the
        already-shaped attribute back, so writer and both enforcers cannot drift.

        **SEC-7 — framing defaults closed, so the author guard must be strict.** Each entry becomes
        a token in the edge CSP directive ``'frame-ancestors ' + list.join(' ')``
        (``infrastructure/application-form.tf``). A host with no list is NOT embeddable (no header);
        the only way framing opens is a stored origin here. So an entry is INPUT-VALIDATED to a bare
        ``https://host[:port]`` serialized origin (:data:`_EMBED_ORIGIN_RE`) — **no ``*``
        wildcard-all** (which would let anyone frame the form), **no ``http://``**, and **no path /
        query / fragment / whitespace / CSP-delimiter characters** (`` ``, ``;``, ``'``, ``"``) that
        could inject an extra ``frame-ancestors`` token or a second CSP directive at the edge. The
        list is bounded (:data:`_EMBED_ORIGINS_MAX_COUNT`, :data:`_EMBED_ORIGIN_MAX_LEN`).

        - ``None`` / absent / empty list → ``[]`` (back-compatible = standalone, no embed origins —
          mirrors how ``mail_domain`` / ``mail_reply_to_default`` omit rather than default). The
          caller writes nothing when the result is empty.
        - a list whose every entry is a well-formed ``https://`` origin → each entry is
          ``strip()``-ed and de-duplicated **preserving first-seen order**.
        - anything else — not a list, a non-string / blank-only entry, a ``*`` / ``http`` / malformed
          or injection-bearing origin, an over-long entry, or too many entries — is REJECTED
          fail-loud with a clear :class:`ConfigWriteValidationError` (R8 / SEC-7), so a malformed or
          dangerous embed config surfaces as a 400 instead of silently weakening ``frame-ancestors``.
        """
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ConfigWriteValidationError(
                "config#mail 'application_embed_origins' must be a list of non-blank origin strings"
            )
        if len(raw) > _EMBED_ORIGINS_MAX_COUNT:
            raise ConfigWriteValidationError(
                "config#mail 'application_embed_origins' has too many entries "
                f"(max {_EMBED_ORIGINS_MAX_COUNT})"
            )
        origins: list[str] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigWriteValidationError(
                    "config#mail 'application_embed_origins' entries must be non-blank strings"
                )
            origin = entry.strip()
            if len(origin) > _EMBED_ORIGIN_MAX_LEN:
                raise ConfigWriteValidationError(
                    "config#mail 'application_embed_origins' entry is too long "
                    f"(max {_EMBED_ORIGIN_MAX_LEN} characters)"
                )
            if not _EMBED_ORIGIN_RE.match(origin):
                # SEC-7: reject `*`, http://, paths, and whitespace/CSP-delimiter injection — only a
                # bare https://host[:port] origin may reach the edge frame-ancestors directive.
                raise ConfigWriteValidationError(
                    "config#mail 'application_embed_origins' entries must each be a well-formed "
                    "'https://host[:port]' origin — no '*' wildcard, no 'http://', no path, and no "
                    f"injection characters (got {origin!r})"
                )
            if origin not in seen:
                seen.add(origin)
                origins.append(origin)
        return origins

    @staticmethod
    def _shape_consent_notice(raw) -> dict | None:
        """Shape a consent notice to ``{"version": str, "text": {locale: str}}`` or ``None``.

        Mirrors the Flask builder's ``_resolve_application_consent_notice`` read-side shaping so
        the written row matches ``get_consent_notice`` exactly (R12.1): requires a non-blank
        ``version`` (string, or an int coerced to str) AND >=1 non-blank string locale under
        ``text``; anything malformed collapses to ``None`` (the attribute is then omitted).
        """
        if not isinstance(raw, Mapping):
            return None
        raw_version = raw.get("version")
        if isinstance(raw_version, bool):
            return None
        if isinstance(raw_version, str):
            version = raw_version.strip()
        elif isinstance(raw_version, int):
            version = str(raw_version)
        else:
            version = ""
        if not version:
            return None
        raw_text = raw.get("text")
        if not isinstance(raw_text, Mapping):
            return None
        text: dict[str, str] = {}
        for locale, text_body in raw_text.items():
            if (
                isinstance(locale, str)
                and locale.strip()
                and isinstance(text_body, str)
                and text_body.strip()
            ):
                text[locale] = text_body
        if not text:
            return None
        return {"version": version, "text": text}
