# AWS Region Strategy — RESOLVED

> **Status: resolved (historical).** The region question is settled and codified; this file is
> a stub kept only so the decision is traceable. The earlier long "switch your AWS CLI default
> from eu-central-1 to eu-west-1" how-to has been removed — that change was made long ago and the
> walkthrough is no longer useful.

**Decision:** the platform runs in **`eu-west-1` (Ireland)** throughout. CloudFront + ACM control
plane operations use `us-east-1` (a service requirement, not a second deployment region).

- All Cognito pools, DynamoDB, S3, Lambda, API Gateway, SNS, SES live in `eu-west-1`.
- `.env` / Terraform / `samconfig.toml` already pin `eu-west-1`; critical region vars fail fast.
- Single region is deliberate — small, single-geography (NL/BE) user base; no multi-region /
  cross-continent DR requirement. Revisit only if a global user base or a hard DR SLA appears.

**Active rule of record:** steering `23-aws-accounts.md` ("Region: `eu-west-1` throughout").
**Account model + the nonprofit move:** see `accounts-strategy.md` (the S6 audit) in this folder.
