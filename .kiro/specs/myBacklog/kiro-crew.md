# Kiro Crew — Added Value Analysis

## What is Kiro Crew?

Kiro Crew (launched August 2026) is an autonomous agent orchestrator built on top of the Kiro CLI. It provides persistent, self-learning agents that run unattended — executing multi-step tasks, retrying on failures, and evolving from your work patterns across sessions.

Key capabilities:

- **Unattended execution** — start a task, walk away, come back when done
- **Persistent memory** — remembers project context, corrections, and preferences across sessions
- **Self-learning** — turns corrections into lasting lessons, adapts to your patterns
- **Scheduling & triggers** — cron schedules, webhook triggers, heartbeat monitors
- **Multi-agent orchestration** — dispatches parallel agents on complex tasks
- **Checkpoints & retries** — long-running tasks validate at each step, retry on failure
- **Apps** — integrate custom workflows and tools

Source: [kiro.dev/crew](https://kiro.dev/crew/)

---

## Current Environment

| Aspect          | myAdmin                                    | hdcn                                  |
| --------------- | ------------------------------------------ | ------------------------------------- |
| Stack           | Flask/Python + React/TS                    | AWS SAM, Python, TypeScript, DynamoDB |
| Hosting         | Railway + Docker                           | AWS (Lambda, API Gateway, DynamoDB)   |
| Dev environment | WSL Ubuntu 26.04                           | Windows (potential move to WSL)       |
| Complexity      | Multi-module (FIN, STR, ZZP), multi-tenant | Serverless microservices              |
| Spec-driven     | Yes (.kiro/specs with TASKS.md)            | TBD                                   |

---

## Added Value Assessment

### High Value Use Cases

#### 1. Spec Task Execution (myAdmin)

**Problem:** Multi-phase TASKS.md files with 10-20+ checkboxes require babysitting Kiro through each step.
**Crew solution:** Point Crew at a TASKS.md, it works through phases autonomously — implementing, testing, committing, moving to next task.
**Estimated time saved:** 2-4 hours per major spec (currently requires periodic check-ins and re-prompting).

#### 2. Cross-Module Incident Investigation (myAdmin)

**Problem:** Issues that span backend/frontend/infrastructure require reading multiple files, tracing flows, correlating logs.
**Crew solution:** Point Crew at an error or ticket, it investigates across repos, identifies root cause, proposes fix.
**Estimated time saved:** 30-60 min per investigation.

#### 3. SAM Deployment Pipeline Monitoring (hdcn)

**Problem:** SAM deployments can fail on CloudFormation stack updates, requiring rollback analysis and retry.
**Crew solution:** Heartbeat monitors detect deployment failures, Crew investigates and either retries or flags for attention.
**Estimated value:** Catch deployment issues faster, especially during off-hours.

#### 4. Scheduled Maintenance Tasks (both projects)

**Problem:** Recurring tasks (dependency updates, test suite health, dead code detection, security scans) get deferred because they're manual.
**Crew solution:** Cron-triggered agents run these on schedule, surface results.
**Candidates:**

- Weekly dependency audit (outdated packages, security advisories)
- Test health scan (flaky tests, coverage drift)
- Database schema drift detection
- Infrastructure state drift (Terraform plan)

### Medium Value Use Cases

#### 5. Persistent Project Context

**Problem:** Every new Kiro session requires re-establishing project context (despite steering files).
**Crew solution:** Memory carries forward — knows the mutaties model, tenant isolation patterns, your coding preferences, past decisions.
**Value:** Reduces ramp-up per session from 2-3 minutes to near-zero.

#### 6. Migration Tasks (both projects)

**Problem:** Database migrations, API version bumps, dependency upgrades touch many files and need careful sequencing.
**Crew solution:** Crew works through migration checklist autonomously with checkpoints.
**Example:** Upgrading Chakra UI 2.x → 3.x across all frontend components.

#### 7. Ticket Triage (future, if ticket system grows)

**Problem:** Managing issue backlog across two projects.
**Crew solution:** Triage incoming issues, identify affected module, flag priority, assign to backlog.
**Current relevance:** Low — limited by current workflow (no external ticketing system observed).

### Lower Value / Already Covered

#### 8. Simple Bug Fixes

Already handled well by interactive Kiro in autopilot mode. Crew adds overhead for quick tasks.

#### 9. Context from Steering Files

Your `.kiro/steering/` files already provide session context. Crew's memory would complement but partially overlap.

---

## Environment Recommendation

| Concern          | Recommendation                                                                      |
| ---------------- | ----------------------------------------------------------------------------------- |
| Where to install | WSL Ubuntu (both projects)                                                          |
| Why WSL          | Native Linux tools, no shell confusion, direct filesystem access, SAM/Docker native |
| hdcn project     | Move to WSL alongside myAdmin for consistent environment                            |
| IDE              | Keep Windows Kiro IDE for interactive work                                          |
| Crew runtime     | Kiro CLI inside WSL — runs natively as background process                           |

### The Shell Confusion Problem (solved)

Current pain: Kiro IDE reports Windows/CMD context but terminal is WSL/bash → constant "use linux tools" corrections. Crew running as CLI inside WSL eliminates this entirely — it's natively Linux, no steering workaround needed.

---

## Prerequisites

- [x] Ubuntu 26.04 with glibc 2.43 (compatible)
- [ ] Install Kiro CLI in WSL: `curl -fsSL https://cli.kiro.dev/install | bash`
- [ ] Authenticate CLI with AWS Builder ID
- [ ] Configure Crew for myAdmin project
- [ ] (Optional) Move hdcn to WSL

---

## Risks & Considerations

| Risk                                   | Mitigation                                                                               |
| -------------------------------------- | ---------------------------------------------------------------------------------------- |
| Crew is brand new (day 1)              | Wait 2-4 weeks for initial stabilization before relying on it for critical work          |
| Autonomous changes without review      | Use Crew's checkpoint system, require PR-based workflow for production-affecting changes |
| Memory accumulating stale context      | Regularly inspect/prune what Crew carries forward (explicitly supported)                 |
| Cost (API usage for unattended agents) | Monitor usage, set limits on long-running tasks                                          |
| Security (credentials access)          | Crew inherits CLI auth — ensure scoped IAM permissions, never store secrets in memory    |

---

## Decision

**Status:** Evaluate after stabilization (target: September 2026)

**Action items:**

1. Install Kiro CLI in WSL now (zero cost, 30 seconds)
2. Monitor Crew changelog for stability signals over next 2-4 weeks
3. First pilot: run a small TASKS.md spec autonomously (low-risk feature)
4. If successful: configure scheduled maintenance tasks
5. If successful: consider hdcn SAM deployment monitoring

**Expected ROI:** Meaningful for multi-step spec implementations and scheduled maintenance. Not needed for daily interactive development — current Kiro IDE workflow handles that well.
