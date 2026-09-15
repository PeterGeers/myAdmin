---
inclusion: auto
---

# Spec Reference Guide

Pull into context with `#specs-reference` when creating or managing specs.

## Progress Tracking

### Status Indicators

Use at the top of spec documents:

- `Status: Draft` — Initial creation
- `Status: In Progress` — Active implementation
- `Status: Ready for Implementation` — Design approved
- `Status: Complete` — All tasks finished
- `Status: ✅ ALL DECISIONS MADE` — Analysis complete

### Task Checkboxes

- `- [ ]` — Not started
- `- [x]` or `- ✅` — Completed
- `- ❌` — Blocked or failed

### Phase Organization

```markdown
## Phase 1: Foundation (3-4 days)

- [x] Task 1
- [x] Task 2
- [ ] Task 3

## Phase 2: Implementation (2-3 days)

- [ ] Task 4
- [ ] Task 5
```

## Cross-Referencing

### Between Specs

```markdown
See `.kiro/specs/Common/Railway migration/TASKS.md` - Phase 2.6
Related: `.kiro/specs/Common/templates/analysis.md`
```

### To Code

```markdown
Implementation: `backend/src/services/template_service.py`
Tests: `backend/tests/unit/test_template_service.py`
```

### To Documentation

```markdown
See `backend/templates/README.md` for template structure
Reference: `backend/docs/guides/TEMPLATE_GUIDE.md`
```

## Spec Examples

### Railway Migration

**Location**: `.kiro/specs/Common/Railway migration/`

- README.md, IMPACT_ANALYSIS_SUMMARY.md, TASKS.md (1106 lines), OPEN_ISSUES.md
- Pattern: Comprehensive analysis → clear decisions → detailed tasks

### Template Preview Validation

**Location**: `.kiro/specs/Common/template-preview-validation/`

- README.md, requirements.md, design.md, AI_ASSISTANCE_APPROACH.md
- Pattern: Requirements-first → design → implementation guidance

### Templates

**Location**: `.kiro/specs/Common/templates/`

- analysis.md, issues.md, TAX_FORMS_OVERVIEW.md
- Pattern: Analysis-focused with decision documentation

## Common Patterns

### Multi-Phase Implementation

- Phase 1: Foundation/Infrastructure
- Phase 2: Core Implementation
- Phase 3: Integration
- Phase 4: UI/Frontend
- Phase 5: Testing
- Phase 6: Deployment

### Decision Documentation

- **Context**: Why this decision was needed
- **Options**: Alternatives considered
- **Decision**: What was chosen
- **Rationale**: Why this option was best
- **Consequences**: Impact and trade-offs

### Testing Strategy per Spec

- Unit test requirements
- Integration test scenarios
- API test cases
- E2E test workflows
- Acceptance criteria validation

## Spec Lifecycle

```
Draft → In Progress → Ready for Implementation → Complete
  ↓         ↓              ↓                        ↓
Create   Design      Implement                  Archive
Analyze  Review      Test                       (if needed)
Decide   Approve     Deploy
```

## Finding Relevant Specs

**By Domain**: Common/ (auth, infra), FIN/ (financial), STR/ (rental)
**By Feature**: Search spec folder names for keywords
**By Status**: Check README.md or document headers for status indicators
**By Cross-Reference**: Follow links from related specs or code comments

## Multi-tenant platform specs (reasoning vs rules vs decisions)

The `.kiro/specs/multi-tenant/` tree follows a three-layer convention — keep them
distinct:

- **Analysis (`.kiro/specs/multi-tenant/Analysis/`)** — the reasoning and open
  decisions (the *why*). Start at `overall_roadmap.md`, the leading index of steps.
- **ADRs (`docs/decisions/`)** — the durable decision log (append-only; supersede,
  never rewrite). The settled model is **ADR 0003** (myAdmin is the platform base;
  evolve in place; import apps as SAM-backed modules), which supersedes 0001/0002.
- **Steering (`.kiro/steering/`)** — the active rules that must track current truth
  (`architecture.md`, `identity.md`, `aws-accounts.md`, `product.md`).

When a decision is settled: record it as an ADR and distil the rule into steering;
keep the Analysis doc as the reasoning trail, marking superseded framing visibly.

### Roadmap linkage

Each roadmap step (S1, S2, …) gets its own step folder under
`.kiro/specs/multi-tenant/` (e.g. `s1-prepare-platform/`,
`s2-jwt-verification/`) with `requirements.md` / `design.md` / `tasks.md` and a
`README.md`. Migration/execution docs tag each gate/phase back to the roadmap step it
belongs to or depends on (see `Analysis/migration_plan.md` for the pattern). The
roadmap is the index; per-step docs carry the detail.

### Cross-referencing to code (platform)

```markdown
Implementation (Flask plane): `backend/src/...`
Implementation (SAM-backed module): the module's own Lambda repo/subtree
Module registry: `backend/src/services/module_registry.py`
```
