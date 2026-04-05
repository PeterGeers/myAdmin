---
inclusion: manual
---

# PR Review Checklist

Use this checklist when reviewing code changes. Pull it into context with `#pr-checklist`.

## Security

- [ ] No hardcoded secrets, API keys, or credentials
- [ ] Parameterized queries (no string interpolation in SQL)
- [ ] Tenant isolation maintained (queries filter by tenant_id)
- [ ] Auth decorators present on all new routes (`@cognito_required` + `@tenant_required`)
- [ ] Input validation on all user-provided data
- [ ] No sensitive data in logs or error messages

## Code Quality

- [ ] Files under 500 lines (max 1000)
- [ ] Functions have docstrings and type hints (Python)
- [ ] Proper TypeScript types (no `any`)
- [ ] Error handling with try/except on all routes
- [ ] Follows existing patterns (Blueprint routing, service layer)
- [ ] No dead code or commented-out blocks

## Testing

- [ ] New code has unit tests
- [ ] Tests use existing fixtures from conftest.py
- [ ] Proper markers applied (unit/integration/api)
- [ ] Edge cases covered (empty input, invalid data, missing fields)
- [ ] All tests pass (`pytest tests/unit/` and `npm test`)

## Performance

- [ ] No N+1 query patterns
- [ ] Large result sets paginated
- [ ] Expensive operations cached where appropriate
- [ ] No unnecessary database calls in loops

## Documentation

- [ ] New routes documented with docstrings
- [ ] API changes reflected in Swagger/Flasgger annotations
- [ ] Spec updated if implementing a spec task
- [ ] Breaking changes noted
