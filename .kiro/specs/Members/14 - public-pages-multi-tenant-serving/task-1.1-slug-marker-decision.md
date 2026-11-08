# Task 1.1 — Slug-marker mechanism decision (VERIFICATION GATE)

> **DECISION FOR TASK 1.2+ TO BUILD ON.** Task 1.1 is the verify-before-lock gate in D-SLUG /
> requirement R4.1. It decides whether `slug_marker_store.claim(slug, owner)` (built in task 1.2,
> in `sam/shared`) uses the **S3 conditional PUT** mechanism or the **DynamoDB fallback**.

## Decision

**SELECTED: S3 conditional `put_object` with `If-None-Match: '*'`** (the preferred/primary
mechanism in D-SLUG and R4.1). The DynamoDB `PutItem(attribute_not_exists(pk))` fallback is **NOT
needed** and is **not** implemented.

Task 1.2 therefore implements `claim(slug, owner)` as:

```python
def claim(slug, owner):             # owner = {owner_plane, kind, tenant_id, resource_ref}
    try:
        s3.put_object(Bucket=BUCKET, Key=f"_slugs/{slug}",
                      Body=json.dumps(owner).encode(), IfNoneMatch="*",
                      ContentType="application/json")
    except ClientError as e:
        if e.response["Error"]["Code"] == "PreconditionFailed":   # HTTP 412
            raise SlugTaken(slug)
        raise
```

- A racing second claimer (any plane / any kind) gets `PreconditionFailed` (HTTP 412) → map to
  `SlugTaken`. The S3 condition IS the check, so there is no check-then-write race (Property 1).
- `resolve(slug)` = `get_object _slugs/{slug}` → decide ownership from the BODY, never the slug
  string (Property 2). `release(slug)` = `delete_object _slugs/{slug}`.
- boto3 note: the CLI flag `--if-none-match '*'` maps to the boto3 `put_object(IfNoneMatch='*')`
  kwarg. The 412 surfaces as `botocore.exceptions.ClientError` with
  `Error.Code == 'PreconditionFailed'`.

## Why — empirical evidence (verified against REAL S3, per HC6; no mock)

Verified **2026-11** against the actual target bucket/region, not documentation alone.

- **Account / identity:** `506221081911`, `arn:aws:sts::506221081911:assumed-role/NonprofitDeployRole/…`
  (profile `nonprofit-deploy`) — confirmed via `sts get-caller-identity` before trusting any S3
  result (steering 41 override-ranking trap guard).
- **Bucket:** `myadmin-public-pages-nonprofit-506221081911`, region **`eu-west-1`**
  (`head-bucket` → `BucketRegion: eu-west-1`).
- **AWS CLI:** `aws-cli/2.35.11` — `s3api put-object` exposes `--if-none-match`.

Conditional-PUT probe against a disposable key `_slug_marker_verify/task-1-1-<ts>-<rand>.json`:

| Step | Command (abridged) | Result | Meaning |
| --- | --- | --- | --- |
| PUT #1 | `put-object … --if-none-match '*'` (key absent) | **success** — `ETag "bfcdf515…"`, exit 0 | first claim wins |
| PUT #2 | `put-object … --if-none-match '*'` (key now present) | **`PreconditionFailed`** (412), exit 254 | second claim → `SlugTaken` ✅ |
| cleanup | `delete-object` | success, exit 0 | disposable object removed |
| confirm | `head-object` | **404 Not Found** | no litter left in bucket ✅ |

PUT #2 returning `PreconditionFailed` on an already-present key is the exact slug-collision
behaviour the platform relies on — proven on real S3, on the real bucket/region, not a mock.
(Full raw transcript was captured under the git-ignored `.agent-output/cond-put-test.txt` during
verification and then cleaned up; the table above is the authoritative record.)

## Consequences for the rest of Task 1

- 1.2 builds `slug_marker_store` on S3 conditional PUT (above). No DynamoDB slug-claim table, no
  new DDB IAM for the marker store.
- 1.4 tests **T2 (cross-plane dup)** and **T3 (concurrency race)** run against REAL S3 (or a
  conditional-honouring emulator) per HC6 — a plain mock that returns success is forbidden, because
  the guarantee IS this S3 behaviour.
- The publish IAM (gated Task 9, SEC-8) scopes `s3:PutObject`/`DeleteObject` to `_slugs/{slug}`
  (markers the producer owns) + its own `{slug}/*` artifacts — never bucket-wide.

## Fallback (recorded, NOT taken)

Had `If-None-Match: '*'` been unavailable on this bucket/region, the sanctioned fallback was a
DynamoDB conditional `PutItem(attribute_not_exists(pk))` on a dedicated slug-claim table (D-SLUG /
R4.1 / Error Handling). The correctness properties (Property 1 atomic uniqueness, etc.) hold either
way. It is not needed — S3 conditional PUT is confirmed available and is the preferred mechanism.
