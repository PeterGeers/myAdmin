# Bugfix Requirements Document

## Introduction

The `Ref3` field in the `mutaties` table stores a full S3 URI (`s3://bucket/key`) instead of just the tenant-relative S3 key. This breaks the frontend's ability to open invoice PDFs from banking transaction rows, because the `handleRef3Click` function passes the `Ref3` value to the `/api/storage/presigned-url` endpoint which expects a plain S3 key (not a URI with protocol and bucket prefix).

The root cause is in `output_service.py` where the storage result `url` field is constructed as `f"s3://{bucket}/{reference}"` instead of using the `reference` value directly. This `url` then flows through `invoice_booking_helper.py` into the `Ref3` database column.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an invoice PDF is uploaded via `output_service.py` to an S3 shared bucket THEN the system stores the full S3 URI (e.g., `s3://myadmin-shared-production/kimgeers/invoices/general/764608e787ea_INV-2026-0001.pdf`) in the `Ref3` field of the `mutaties` table

1.2 WHEN a user clicks a banking transaction row with an S3-stored invoice THEN the system passes the full S3 URI to `/api/storage/presigned-url` which fails to generate a valid presigned URL because the key contains the `s3://bucket/` prefix

1.3 WHEN the `handleRef3Click` function evaluates a `Ref3` value starting with `s3://` THEN the system treats it as an external URL (starts with a protocol scheme) and falls through to the clipboard copy path instead of fetching a presigned URL

### Expected Behavior (Correct)

2.1 WHEN an invoice PDF is uploaded via `output_service.py` to an S3 shared bucket THEN the system SHALL store only the tenant-relative S3 key (e.g., `kimgeers/invoices/general/764608e787ea_INV-2026-0001.pdf`) in the `Ref3` field of the `mutaties` table

2.2 WHEN a user clicks a banking transaction row with an S3-stored invoice THEN the system SHALL pass the plain S3 key to `/api/storage/presigned-url` which generates a valid presigned URL and opens the PDF in a new tab

2.3 WHEN the `handleRef3Click` function evaluates a `Ref3` value containing a plain S3 key (not starting with `http`) THEN the system SHALL correctly identify it as an S3 key and fetch a presigned URL for it

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a `Ref3` value is a Google Drive URL (starts with `https://drive.goo`) THEN the system SHALL CONTINUE TO open it directly in a new browser tab

3.2 WHEN a `Ref3` value is any other HTTP/HTTPS URL THEN the system SHALL CONTINUE TO copy it to the clipboard

3.3 WHEN an invoice PDF is uploaded in test mode (local storage) THEN the system SHALL CONTINUE TO store the local URL format without modification

3.4 WHEN an invoice PDF is uploaded via `invoice_service.py` S3 path THEN the system SHALL CONTINUE TO store the S3 key correctly (this path already returns `{'url': s3_key}` without the bucket prefix)

3.5 WHEN the S3 shared storage provider uploads a file THEN the system SHALL CONTINUE TO return the tenant-relative S3 key from the `upload()` method

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type StorageUploadResult
  OUTPUT: boolean

  // Returns true when output_service.py uploads to S3 shared bucket
  // (i.e., the provider has a non-empty bucket attribute)
  RETURN X.provider_has_bucket = true
END FUNCTION
```

## Property Specification

```pascal
// Property: Fix Checking — Ref3 stores plain S3 key
FOR ALL X WHERE isBugCondition(X) DO
  result ← output_service.upload_to_storage'(X)
  ASSERT result.url = result.reference
  // The url field must equal the reference (plain S3 key),
  // not "s3://{bucket}/{reference}"
END FOR
```

## Preservation Goal

```pascal
// Property: Preservation Checking — Non-S3 paths unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT output_service.upload_to_storage(X) = output_service.upload_to_storage'(X)
  // When there is no bucket (test mode, local storage),
  // behavior remains identical
END FOR
```
