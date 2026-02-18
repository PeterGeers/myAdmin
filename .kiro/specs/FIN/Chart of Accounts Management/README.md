# Chart of Accounts Management - Specification

**Status**: Ready for Implementation  
**Date**: 2026-02-17  
**Module**: Financial (FIN) - Tenant Admin  
**Estimated Effort**: 4-6 days

## Overview

Self-service UI for tenants to manage their chart of accounts (`rekeningschema` table) through the Tenant Admin module.

## Documentation Structure

### 1. proposal.md

High-level proposal with business justification, solution overview, and implementation phases.

**Key Sections**:

- Business need and pain points
- Current state analysis
- Proposed solution (Tenant Admin location)
- API and UI specifications
- Development workflow (Docker local development)
- Implementation phases (3 phases, 4-6 days)
- Success criteria

### 2. backend-design.md

Complete backend technical design with implementation details.

**Key Sections**:

- Architecture overview
- Database design (existing `rekeningschema` table)
- 7 API endpoints with full Python code:
  - List accounts (with pagination, search, sort)
  - Get single account
  - Create account
  - Update account
  - Delete account (with usage check)
  - Export to Excel
  - Import from Excel
- Security & access control (FIN module check)
- Error handling (HTTP status codes, validation)
- Testing strategy (unit, API, integration tests)
- Performance considerations
- Audit logging
- Deployment notes

### 3. frontend-design.md

Complete frontend technical design with React/TypeScript implementation.

**Key Sections**:

- Component architecture
- TypeScript interfaces
- ChartOfAccounts.tsx (main component with full code)
- AccountModal.tsx (add/edit modal with full code)
- State management and data flow
- API integration service layer
- Error handling

## Quick Start

### For Developers

1. **Read**: proposal.md (understand the feature)
2. **Backend**: backend-design.md (implement API endpoints)
3. **Frontend**: frontend-design.md (implement UI components)
4. **Test**: Follow testing strategy in backend-design.md

### For Reviewers

1. **Business**: Read proposal.md sections 1-3
2. **Technical**: Review backend-design.md and frontend-design.md
3. **Approval**: Check success criteria in proposal.md

## Key Design Decisions

### 1. Location: Tenant Admin Module

- Tenant-specific configuration data
- Requires admin-level permissions
- Fits existing pattern

### 2. Click-to-Edit Interaction

- Click any table row to edit
- No action buttons cluttering rows
- Cleaner, more intuitive UI

### 3. Module Access Control

- Check `tenant_modules` table for FIN module
- Frontend hides menu item if no access
- Backend returns 403 if not enabled

### 4. Local Docker Development

- Backend: localhost:5000 (Docker container)
- Frontend: localhost:3000 (npm start)
- MySQL: Docker Desktop container
- Fast iteration, no Railway costs

### 5. No Schema Changes

- Uses existing `rekeningschema` table
- No database migrations required
- Minimal risk

## Technology Stack

- **Frontend**: React 19.2.0, TypeScript 4.9.5, Chakra UI 2.8.2
- **Backend**: Flask 2.3.3, Python 3.11
- **Database**: MySQL 8.0 (existing table)
- **Patterns**: Generic Filter Framework, Chakra UI theme
- **Deployment**: Railway (production), Docker (local)

## Related Specifications

- Generic Filter Framework: `.kiro/specs/Common/Filters a generic approach/`
- Tenant Admin Module: `.kiro/specs/Common/TenantAdmin-Module/`
- Multi-tenant Patterns: `backend/src/auth/tenant_context.py`
- Authentication: `backend/src/auth/cognito_utils.py`

## Success Criteria

- ✅ Tenant admins can manage accounts
- ✅ Validation prevents data issues
- ✅ Excel import/export works
- ✅ All changes audit logged
- ✅ Intuitive UI
- ✅ Module access controlled
- ✅ Tested in local environment
- ✅ Code reviewed via PR
- ✅ No breaking changes

## Next Steps

1. Review and approve specifications
2. Create feature branch: `feature/chart-of-accounts-management`
3. Start Phase 1 implementation
4. Test locally with Docker
5. Create PR when complete
6. Deploy to production
