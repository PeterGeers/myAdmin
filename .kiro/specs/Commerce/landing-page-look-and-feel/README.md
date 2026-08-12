# Landing Page Look & Feel — Spec Overview

## Status: In Progress

## Summary

Extend the existing landing page feature with visual customization capabilities: per-block styling (backgrounds, spacing, text colour), global theme presets, expanded layout variants per block type, and typography/spacing controls. Enables tenant admins to create distinctive, professional-looking pages without CSS knowledge.

## Reading Order

1. `requirements.md` — User stories and acceptance criteria
2. `design.md` — Technical architecture, data model extensions, rendering changes
3. `tasks.md` — Implementation phases with task checkboxes

## Parent Spec

- Landing Page base: `.kiro/specs/Commerce/landing-page/`
- Original analysis: `.kiro/specs/Commerce/landing-page/improve-landing-page-look-and-feel.md`

## Key Decisions

| #   | Decision                                          | Rationale                                                                                                     |
| --- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| 1   | Theme presets are system-level (hardcoded)        | Simpler, no extra storage. Tenants select preset + override colours. Promote to configurable later if needed. |
| 2   | Include "Reset to theme defaults" button          | Low effort, good UX safety net                                                                                |
| 3   | Gradient: curated presets + free-form input       | 6–8 presets for quick selection, paste custom CSS gradient for power users                                    |
| 4   | Video-bg hero: YouTube embed only (Phase C)       | No hosting cost, auto-serves correct resolution. Self-hosted deferred.                                        |
| 5   | Carousel: auto-advances every 10s + user controls | Vanilla JS inline, pause on hover/interaction, prev/next + dot navigation                                     |
| 6   | Extract renderers to `landing_page_renderers.py`  | Current publish service is at 1171 lines (file limit). Phase C layout variants would exceed it.               |

## Change Log

| Date       | Change                                                  |
| ---------- | ------------------------------------------------------- |
| 2026-08-12 | Initial spec created from improvement analysis document |
