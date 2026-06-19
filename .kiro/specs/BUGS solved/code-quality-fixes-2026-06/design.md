# Design

## Overview

This spec addresses code quality issues through refactoring (file splitting), dead code removal, test coverage improvements, type safety enhancements, and documentation updates. No new architecture or APIs are introduced — this is purely a quality improvement effort.

## Approach

1. **File splitting** — Break files >1000 lines into focused modules following existing patterns
2. **Dead code removal** — Remove verified unused code (vulture 60%+ confidence)
3. **Test coverage** — Add unit/API tests for untested modules
4. **Type safety** — Add Python type hints and replace TypeScript `any` types
5. **Documentation** — Update stale docs to match current code
