"""
S5 — the **h-dcn** tenant-scoped package (design C5, Rung 3; Property 5).

This is the ONLY place h-dcn-specific member logic and the ``tenant_id="h-dcn"`` literal are
allowed to live. The generic Members core (``sam/members/domain/*``) stays tenant-agnostic;
h-dcn plugs into it purely through the named extension points of
:class:`sam.members.domain.tenant_hooks.TenantHookRegistry`, bound here by
:func:`sam.members.tenants.hdcn.hooks.register_hdcn_hooks`.
"""

from .hooks import HDCN_TENANT_ID, register_hdcn_hooks

__all__ = ["HDCN_TENANT_ID", "register_hdcn_hooks"]
