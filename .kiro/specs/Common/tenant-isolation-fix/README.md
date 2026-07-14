# Tenant Isolation & Cache Consistency Fix

## Status: Ready for Implementation

## Problem Summary

Two related issues discovered during investigation of Aangifte IB report discrepancy:

1. **Tenant isolation flaws** — multiple pathways allow cross-tenant data leakage:
   - Frontend sends `'all'` when no tenant selected
   - Backend routes accept `'all'` bypassing ownership checks
   - Cache uses `str.startswith()` prefix matching instead of exact match

2. **Cache data consistency** — summary and detail views can show mismatched data due to cache TTL expiration, concurrent mutations, and lack of snapshot isolation

## Reading Order

1. `bugfix.md` — Requirements with current/expected behavior
2. `design.md` — Technical approach and code patterns
3. `tasks.md` — Implementation checklist (5 phases, ~4.5 hours)

## Priority

- Phase 1 (startswith fix): **CRITICAL** — exploitable tenant leak
- Phase 2-3 (all fallback): **HIGH** — defense in depth
- Phase 4 (cache consistency): **MEDIUM** — data correctness, hard to exploit

## Change Log

| Date       | Change                                           |
| ---------- | ------------------------------------------------ |
| 2026-07-10 | Initial spec created from live debugging session |
