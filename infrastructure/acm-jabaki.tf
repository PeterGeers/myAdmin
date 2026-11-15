# ACM Wildcard Certificate for *.jabaki.nl — RETIRED (2026-11-15)
#
# The personal-account *.jabaki.nl certificate (da81c484…) and its Route 53
# validation CNAME were deleted when the public-pages hosting moved to the
# nonprofit account (506221081911). The live *.jabaki.nl certificate is
# `aws_acm_certificate.jabaki_wildcard` in infrastructure/nonprofit-public-pages/.
# Spec: .kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit (task 7.2).
#
# The `removed` blocks drop the (already deleted) objects from state without
# Terraform trying to destroy anything. Delete these blocks once an apply has
# run with them.

removed {
  from = aws_acm_certificate.jabaki_wildcard
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_acm_certificate_validation.jabaki_wildcard
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53_record.jabaki_cert_validation
  lifecycle {
    destroy = false
  }
}
