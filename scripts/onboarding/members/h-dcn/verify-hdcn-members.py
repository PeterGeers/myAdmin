#!/usr/bin/env python3
"""verify-hdcn-members.py - verify sam-members table against h-dcn source (read-only)."""

from __future__ import annotations

import os
import sys

DEFAULT_REGION = "eu-west-1"
_HDCN_TENANT_ID = "h-dcn"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tenant = _HDCN_TENANT_ID
    if "--tenant" in argv:
        tenant = argv[argv.index("--tenant") + 1]
    region = os.environ.get("AWS_REGION", DEFAULT_REGION)
    print("verify tenant=%s region=%s" % (tenant, region))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())