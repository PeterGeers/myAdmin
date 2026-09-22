"""
Members module **repository layer** — the ONLY DynamoDB touch-point.

Per ``.kiro/steering/35-sam-module-architecture-sam.md`` and design C6, this layer is the
single place that talks to DynamoDB, and it is where **tenant isolation is enforced**:
every method takes ``tenant_id`` and every query is keyed by it (``tenant_id`` partition key
+ IAM ``dynamodb:LeadingKeys``), so no layer above can cross tenants even with a bug
(Property 1 — structural isolation). Data-level invariants (member-number uniqueness per
tenant) are enforced here via DynamoDB **conditional writes**, not by the domain layer.

The domain service depends on the **interface** defined here (``MembersRepository``), never
on a concrete DynamoDB client — keeping the domain storage-agnostic and testable.

Task 1.0 shipped the **interface + stubs**; task 1.4 adds the tenant-scoped **table design**
(:mod:`sam.members.repository.table_design`) and the concrete boto3-backed
:class:`DynamoDbMembersRepository` (member-number uniqueness via conditional writes, atomic
counters, every operation keyed by ``tenant_id``). Step 4 provisions the physical tables and
backfills h-dcn data.
"""

from sam.members.repository.members_repository import (
    DynamoDbMembersRepository,
    MemberNumberConflictError,
    MembersRepository,
)

__all__ = [
    "MembersRepository",
    "DynamoDbMembersRepository",
    "MemberNumberConflictError",
]

# Note: the Lidmaatschap Beheer catalog *entity* (MembershipTypeEntry) lives in the domain
# layer (sam.members.domain.membership_type_catalog); the repository only exposes the
# catalog persistence *methods* on MembersRepository (design C8 — repository is the sole
# DynamoDB touch-point, the entity is a domain type).
