# Cognito: Move from Plus to Essentials Tier

**Date:** 2026-04-03
**Status:** Ready to implement

## Current situation

myAdmin uses Cognito Plus tier at $0.02/MAU. For < 10,000 MAU, Essentials is free.

## Finding: Essentials supports everything myAdmin needs

| Feature                                    | Used by myAdmin | Essentials | Plus |
| ------------------------------------------ | --------------- | ---------- | ---- |
| Sign-up, sign-in                           | ✅              | ✅         | ✅   |
| User groups (Finance_CRUD, SysAdmin, etc.) | ✅              | ✅         | ✅   |
| Custom attributes (custom:tenants)         | ✅              | ✅         | ✅   |
| Admin APIs (create user, manage groups)    | ✅              | ✅         | ✅   |
| Passkeys / WebAuthn / FIDO2                | ✅              | ✅         | ✅   |
| Passwordless sign-in (OTP)                 | Not used        | ✅         | ✅   |
| Email MFA                                  | Not used        | ✅         | ✅   |
| Protect against unsafe passwords           | Not used        | ❌         | ✅   |
| Protect against malicious sign-in          | Not used        | ❌         | ✅   |
| User activity logging & export             | Not used        | ❌         | ✅   |

Source: [AWS Cognito Feature Plans](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-sign-in-feature-plans.html)

Passkeys are supported on Essentials — confirmed by AWS docs and working in the h-dcn project.

## Cost impact

| Tier       | < 10,000 MAU | 10,001+ MAU |
| ---------- | ------------ | ----------- |
| Plus       | $0.02/MAU    | $0.02/MAU   |
| Essentials | Free         | $0.015/MAU  |

For myAdmin (< 50 users): Plus = $1.00/month → Essentials = $0.00/month.

## How to switch

1. Go to AWS Console → Cognito → User Pool `eu-west-1_Hdp40eWmu`
2. Settings → Pricing tier
3. Change from Plus to Essentials
4. No code changes needed — all features used by myAdmin are available on Essentials

## What you lose (Plus-only features not used by myAdmin)

- Compromised password detection at runtime
- Malicious sign-in attempt detection
- User activity risk scoring and logging
- Log export to external AWS services

These are advanced security monitoring features. Not needed for a small business app.
