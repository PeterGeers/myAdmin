"""Membership-service WRITE path — the composed ``WritesMixin`` (public import surface).

Historically this module held the entire WRITE path in one ``WritesMixin`` (the largest source
file in the repo). It has been split along cohesion seams into four sub-mixins — each in its own
module — while keeping THIS module's public import surface stable: ``WritesMixin`` is still
imported from here (by ``membership_service`` and by tests), still carries every write-path
method, and the behaviour is unchanged. The split is pure structure.

The four seams (each mixed into the composed ``WritesMixin`` below, so method resolution is
identical to the old single class):

- :mod:`._membership_writes_validation` — ``ValidationMixin``: the authoritative member-record
  validation chain (fixed + overlay required-ness, ``show_when`` gating, enum role / overlay-enum
  ``choices`` gates, ``member_number`` format, the declarative ``FieldFormat`` step, and the
  ``membership_type`` catalog-reference check).
- :mod:`._membership_writes_application` — ``ApplicationWritesMixin``: the PUBLIC application
  intake (``create_application`` + its field gate / un-flatten, ``membership_type`` subset+default,
  the GDPR consent stamp, and the possible-duplicate flag).
- :mod:`._membership_writes_crud` — ``MemberWritesMixin``: the authenticated member / membership /
  delegate create-update-delete writes and the shared write-path helpers (sanitize, authorize,
  deep-merge).
- :mod:`._membership_writes_fieldconfig` — ``FieldConfigSurfaceMixin``: the RESOLVED field-config
  surface the presentation-only frontend reads (staff + public schema, serializers, scope vocab).

``WritesMixin`` composes all four so every cross-method call (and every ``WritesMixin.<static>``
reference made by callers/tests) resolves exactly as before via the composed class's MRO.
"""

from __future__ import annotations

from sam.members.domain._membership_writes_application import (
    ApplicationWritesMixin,
)
from sam.members.domain._membership_writes_crud import (
    MemberWritesMixin,
)
from sam.members.domain._membership_writes_fieldconfig import (
    FieldConfigSurfaceMixin,
)
from sam.members.domain._membership_writes_validation import (
    ValidationMixin,
)

__all__ = ["WritesMixin"]


class WritesMixin(
    ValidationMixin,
    ApplicationWritesMixin,
    MemberWritesMixin,
    FieldConfigSurfaceMixin,
):
    """The full membership-service WRITE path, composed from its four cohesion-seam sub-mixins.

    This is the stable name ``MembershipService`` mixes in and that tests import. It defines no
    members of its own — all behaviour lives in the four sub-mixins above — so splitting the
    former monolithic class changed structure only, never behaviour. Method resolution across the
    seams (e.g. ``create_application`` in ``ApplicationWritesMixin`` calling
    ``_collect_member_record_errors`` in ``ValidationMixin``) works because the composed class
    inherits every one, exactly as when they shared a single class body.
    """
