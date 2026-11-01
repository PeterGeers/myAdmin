# Nonprofit public-pages hosting (jabaki.nl migration)

**Status: DRAFT — nothing here has been applied.** These files only *describe* the
new setup. No AWS resource is created until someone runs `terraform apply` (a
later, separately-approved step).

## What this is, in plain terms

It rebuilds the public landing-page hosting for `*.jabaki.nl` in the **nonprofit**
AWS account (506221081911), as a brand-new, separate copy that does not touch the
currently-live site. Same behaviour as today, just in the new account:

- an S3 bucket to hold the published pages,
- a CloudFront (CDN) distribution to serve them over HTTPS,
- the small "url-rewrite" function that maps `peter.jabaki.nl` -> `/peter/index.html`,
- the two small key/value lookups the routing uses,
- a new HTTPS certificate for `*.jabaki.nl`,
- the permissions the backend needs to publish pages.

## What it deliberately does NOT do

- It does **not** manage the `jabaki.nl` domain zone or any **email** records.
  Those stay in the personal account and are never touched by this.
- It does **not** change where `*.jabaki.nl` currently points. That "flip the
  switch" moment is a later, separate step (Phase 5).
- It does **not** include the extra "CSP" response function (that feature is
  deferred).

## How it eventually gets applied (two steps, both reviewed first)

1. `terraform init -backend-config="bucket=<state-bucket>"` then
   `terraform apply` the **certificate request** only. That prints a validation
   record. We add that one record to the personal `jabaki.nl` zone (Phase 2.3)
   and wait for the certificate to say ISSUED.
2. `terraform apply` the rest (bucket, CDN, function, permissions), which now
   references the issued certificate.

Each apply is `plan -out=tf.plan` -> read the plan -> `apply tf.plan`, per the
project's manual plan-first rule.

## Bucket name
`myadmin-public-pages-nonprofit-506221081911` (checked: not currently taken).
