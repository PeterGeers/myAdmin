# Spec-Driven Development

This project uses formal specifications for feature development. Specs provide structured documentation from requirements through implementation.

## Spec Organization

Specs are located in `.kiro/specs/` organized by domain:

```
.kiro/specs/
├── Common/          # Cross-cutting features (auth, infrastructure, templates)
├── FIN/             # Financial module features
└── STR/             # Short-term rental features
```

## Typical Spec Structure

Each spec folder contains:

### Core Documents

1. **README.md** - Navigation guide
   - Reading order for different audiences
   - Quick start sections
   - Document summaries
   - Status and change log

2. **requirements.md** - Business requirements
   - User stories with acceptance criteria
   - Functional and non-functional requirements
   - Success criteria
   - Out of scope items
   - Acceptance testing scenarios

3. **design.md** - Technical design
   - Architecture and data flow
   - API specifications (endpoints, schemas)
   - Database schema changes
   - Implementation details
   - Security considerations
   - Error handling and performance

4. **TASKS.md** - Implementation checklist
   - Detailed task breakdown by phase
   - Checkboxes for progress tracking (✅/❌)
   - Time estimates
   - Dependencies
   - Testing requirements

### Supporting Documents

- **analysis.md** - Problem analysis and architectural decisions
- **OPEN_ISSUES.md** - Pending decisions and blockers
- **IMPACT_ANALYSIS_SUMMARY.md** - High-level overview and key decisions
- **issues.md** - Known problems and workarounds
- Domain-specific docs (e.g., field mappings, configuration guides)

## Spec Workflow

### 1. Analysis Phase

- Understand the problem deeply
- Document architectural options
- Make key decisions
- Create IMPACT_ANALYSIS_SUMMARY.md

### 2. Requirements Phase

- Define user stories
- Document acceptance criteria
- Identify constraints and dependencies
- Create requirements.md

### 3. Design Phase

- Plan technical approach
- Design APIs and database schema
- Document security and performance considerations
- Create design.md

### 4. Implementation Phase

- Break work into phases and tasks
- Create detailed checklist in TASKS.md
- Track progress with checkboxes
- Update specs as implementation evolves

### 5. Completion

- Mark all tasks complete
- Update status indicators
- Document lessons learned
- Archive if needed

## When to Use Specs

### Create New Spec

- Building new features or modules
- Major architectural changes
- Complex multi-phase work
- Features requiring cross-team coordination

### Update Existing Spec

- Modifying existing features
- Adding functionality to existing modules
- Changing designs or requirements
- Completing implementation tasks

### No Spec Needed

- Bug fixes (unless architectural)
- Minor UI tweaks
- Configuration changes
- Documentation updates

## Progress Tracking

### Status Indicators

Use at the top of spec documents:

- `Status: Draft` - Initial creation
- `Status: In Progress` - Active implementation
- `Status: Ready for Implementation` - Design approved
- `Status: Complete` - All tasks finished
- `Status: ✅ ALL DECISIONS MADE` - Analysis complete

### Task Checkboxes

- `- [ ]` - Not started
- `- [x]` or `- ✅` - Completed
- `- ❌` - Blocked or failed

### Phase Organization

Group tasks into logical phases:

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

Use relative paths from `.kiro/specs/`:

```markdown
See `.kiro/specs/Common/Railway migration/TASKS.md` - Phase 2.6
Related: `.kiro/specs/Common/templates/analysis.md`
```

### To Code

Reference implementation files:

```markdown
Implementation: `backend/src/services/template_service.py`
Tests: `backend/tests/unit/test_template_service.py`
```

### To Documentation

Link to related docs:

```markdown
See `backend/templates/README.md` for template structure
Reference: `backend/docs/guides/TEMPLATE_GUIDE.md`
```

## Spec Examples

### Railway Migration

**Location**: `.kiro/specs/Common/Railway migration/`

**Structure**:

- README.md - Navigation guide ("Start here")
- IMPACT_ANALYSIS_SUMMARY.md - Master plan with all decisions
- TASKS.md - 1106 lines of detailed implementation tasks
- OPEN_ISSUES.md - Decision tracking (all resolved)
- Supporting docs in archive/ folder

**Pattern**: Comprehensive analysis → clear decisions → detailed tasks

### Template Preview Validation

**Location**: `.kiro/specs/Common/template-preview-validation/`

**Structure**:

- README.md - Overview and quick start
- requirements.md - User stories and acceptance criteria
- design.md - Technical architecture
- AI_ASSISTANCE_APPROACH.md - AI integration strategy
- Field mapping docs

**Pattern**: Requirements-first → design → implementation guidance

### Templates

**Location**: `.kiro/specs/Common/templates/`

**Structure**:

- analysis.md - Architectural decisions and options
- issues.md - Known problems
- TAX_FORMS_OVERVIEW.md - Domain-specific reference

**Pattern**: Analysis-focused with decision documentation

## AI Assistant Guidelines

### Before Starting Work

1. **Check for existing specs** - Search `.kiro/specs/` for related work
2. **Read README first** - Understand navigation and status
3. **Review decisions** - Check IMPACT_ANALYSIS_SUMMARY.md or analysis.md
4. **Understand context** - Read requirements and design docs

### During Implementation

1. **Follow the spec** - Use TASKS.md as your checklist
2. **Update progress** - Check off completed tasks
3. **Document changes** - Update design.md if approach changes
4. **Track issues** - Add to OPEN_ISSUES.md or issues.md

### When Creating New Specs

1. **Choose appropriate domain** - Common, FIN, or STR
2. **Create folder structure** - Include README, requirements, design, tasks
3. **Follow established patterns** - Use existing specs as templates
4. **Cross-reference** - Link to related specs and code
5. **Start with README** - Provide navigation for others

### When Updating Specs

1. **Maintain structure** - Don't break existing organization
2. **Update status** - Change status indicators as work progresses
3. **Preserve history** - Don't delete completed tasks, mark them done
4. **Add context** - Explain why changes were made
5. **Update cross-references** - Keep links current

## Best Practices

### Writing Requirements

- Use user story format: "As a [role], I want [feature], so that [benefit]"
- Include clear acceptance criteria
- Define success metrics
- Document what's out of scope

### Writing Design

- Start with architecture overview
- Include diagrams or data flow descriptions
- Specify API contracts (request/response schemas)
- Document security and performance considerations
- Explain key technical decisions

### Writing Tasks

- Break work into manageable chunks (< 1 day each)
- Group into logical phases
- Include time estimates
- Note dependencies between tasks
- Add testing requirements for each phase

### Maintaining Specs

- Keep specs in sync with implementation
- Update when requirements or design changes
- Archive outdated sections rather than deleting
- Add lessons learned at completion

## Common Patterns

### Multi-Phase Implementation

Large features broken into phases:

- Phase 1: Foundation/Infrastructure
- Phase 2: Core Implementation
- Phase 3: Integration
- Phase 4: UI/Frontend
- Phase 5: Testing
- Phase 6: Deployment

### Decision Documentation

Key decisions documented with:

- **Context**: Why this decision was needed
- **Options**: Alternatives considered
- **Decision**: What was chosen
- **Rationale**: Why this option was best
- **Consequences**: Impact and trade-offs

### Testing Strategy

Each spec includes:

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

## Integration with Development

### Before Coding

- Review relevant specs
- Understand requirements and design
- Check for open issues or blockers
- Verify dependencies are complete

### During Coding

- Follow design specifications
- Update task checkboxes as you progress
- Document deviations in design.md
- Add new issues to OPEN_ISSUES.md

### After Coding

- Mark tasks complete
- Update status to "Complete"
- Document lessons learned
- Create follow-up specs if needed

## Finding Relevant Specs

### By Feature

Search spec folder names for feature keywords

### By Domain

- Authentication, infrastructure → Common/
- Financial reports, invoices → FIN/
- Rental management, pricing → STR/

### By Status

Check README.md or top of documents for status indicators

### By Cross-Reference

Follow links from related specs or code comments

## Summary

Specs are the single source of truth for feature development in this project. They provide:

- Clear requirements and acceptance criteria
- Detailed technical designs
- Structured implementation plans
- Progress tracking
- Decision documentation

Always check for existing specs before starting work, and keep them updated as implementation progresses.
