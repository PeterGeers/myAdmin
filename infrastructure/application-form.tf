# Application Form — Embed enforcement (CSP frame-ancestors) — MOVED (2026-11-15)
#
# The embed-origins KeyValueStore, the viewer-response `frame-ancestors`
# CloudFront function and the backend KVS policy used to live here, attached to
# the personal-account public-pages distribution. That distribution was retired
# when hosting moved to the nonprofit account (506221081911). The embed-origins
# KVS now lives in infrastructure/nonprofit-public-pages/hosting.tf
# (`aws_cloudfront_key_value_store.application_embed_origins`); the
# frame-ancestors function was deliberately NOT ported (design D4, deferred).
# No behaviour was lost: the personal KVS was empty, so the old function never
# emitted a header. Port the function onto the nonprofit distribution when a
# tenant actually needs embedding.
# Spec: .kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit (task 7.2).
#
# The personal objects were deleted by hand; the `removed` blocks drop them from
# state without Terraform trying to destroy anything. Delete these blocks once an
# apply has run with them.

removed {
  from = aws_cloudfront_key_value_store.application_embed_origins
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cloudfront_function.application_form_frame_ancestors
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_iam_policy.application_embed_origins_kvs
  lifecycle {
    destroy = false
  }
}
