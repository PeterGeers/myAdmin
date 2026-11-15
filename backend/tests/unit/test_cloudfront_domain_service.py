"""
Unit Tests for CloudFrontDomainService

Tests custom domains as CloudFront distribution tenants (multi-tenant
distribution), the embed-origins KeyValueStore, and the cross-account role.
Uses unittest.mock to mock boto3 clients.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


@pytest.fixture
def mock_env(monkeypatch):
    """Set environment variables for CloudFrontDomainService."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID", "E1234DISTRIBUTION")
    monkeypatch.setenv(
        "CLOUDFRONT_KVS_ARN",
        "arn:aws:cloudfront::123456789:key-value-store/test-kvs",
    )
    monkeypatch.setenv(
        "CLOUDFRONT_EMBED_ORIGINS_KVS_ARN",
        "arn:aws:cloudfront::123456789:key-value-store/embed-origins-kvs",
    )
    monkeypatch.setenv("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "d1234abcd.cloudfront.net")
    monkeypatch.setenv("CLOUDFRONT_CUSTOM_DOMAINS_DISTRIBUTION_ID", "EMULTITENANT")
    monkeypatch.delenv("PUBLIC_PAGES_AWS_ROLE_ARN", raising=False)


@pytest.fixture
def mock_boto3(mock_env):
    """Create CloudFrontDomainService with mocked boto3 clients."""
    with patch("boto3.client") as mock_client_factory:
        mock_cloudfront = MagicMock()
        mock_acm = MagicMock()
        mock_kvs = MagicMock()

        def client_factory(service_name, **kwargs):
            if service_name == "cloudfront":
                return mock_cloudfront
            elif service_name == "acm":
                return mock_acm
            elif service_name == "cloudfront-keyvaluestore":
                return mock_kvs
            return MagicMock()

        mock_client_factory.side_effect = client_factory

        from services.cloudfront_domain_service import CloudFrontDomainService

        service = CloudFrontDomainService()

        yield service, mock_cloudfront, mock_acm, mock_kvs


# Application-form public host used as the embed-origins KVS key.
FORM_HOST = "tenant-member-application.jabaki.nl"
# Must match CLOUDFRONT_EMBED_ORIGINS_KVS_ARN in the mock_env fixture.
EMBED_KVS_ARN = "arn:aws:cloudfront::123456789:key-value-store/embed-origins-kvs"


class TestFormatFrameAncestorsValue:
    """Tests for the application_embed_origins → CSP value formatter (Task 5.2)."""

    def test_list_joined_space_separated(self):
        from services.cloudfront_domain_service import CloudFrontDomainService

        value = CloudFrontDomainService._format_frame_ancestors_value(
            ["https://www.acme.nl", "https://portal.acme.nl"]
        )
        assert value == "https://www.acme.nl https://portal.acme.nl"

    def test_blanks_and_whitespace_dropped(self):
        from services.cloudfront_domain_service import CloudFrontDomainService

        value = CloudFrontDomainService._format_frame_ancestors_value(
            ["  https://a.nl  ", "", "   ", "https://b.nl"]
        )
        assert value == "https://a.nl https://b.nl"

    def test_empty_list_returns_empty(self):
        from services.cloudfront_domain_service import CloudFrontDomainService

        assert CloudFrontDomainService._format_frame_ancestors_value([]) == ""
        assert CloudFrontDomainService._format_frame_ancestors_value(None) == ""

    def test_prejoined_string_normalised(self):
        from services.cloudfront_domain_service import CloudFrontDomainService

        value = CloudFrontDomainService._format_frame_ancestors_value(
            "https://a.nl   https://b.nl"
        )
        assert value == "https://a.nl https://b.nl"


class TestPutApplicationEmbedOrigins:
    """Tests for CloudFrontDomainService.put_application_embed_origins (Task 5.2)."""

    def test_put_origins_success(self, mock_boto3):
        """A configured origins list is written to the embed-origins KVS."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "E_ORIG1"}
        mock_kvs.put_key.return_value = {}

        result = service.put_application_embed_origins(
            FORM_HOST, ["https://www.acme.nl", "https://portal.acme.nl"]
        )

        assert result is True
        mock_kvs.put_key.assert_called_once_with(
            KvsARN=EMBED_KVS_ARN,
            Key=FORM_HOST,
            Value="https://www.acme.nl https://portal.acme.nl",
            IfMatch="E_ORIG1",
        )

    def test_empty_origins_deletes_mapping_standalone(self, mock_boto3):
        """No origins (standalone) clears the key instead of writing an empty value."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "E_ORIG2"}
        mock_kvs.delete_key.return_value = {}

        result = service.put_application_embed_origins(FORM_HOST, [])

        assert result is True
        mock_kvs.put_key.assert_not_called()
        mock_kvs.delete_key.assert_called_once_with(
            KvsARN=EMBED_KVS_ARN,
            Key=FORM_HOST,
            IfMatch="E_ORIG2",
        )

    def test_put_origins_uses_embed_kvs_not_domain_kvs(self, mock_boto3):
        """The embed path targets the dedicated embed-origins KVS ARN, not the domain KVS."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "E_ORIG3"}
        mock_kvs.put_key.return_value = {}

        service.put_application_embed_origins(FORM_HOST, ["https://www.acme.nl"])

        assert mock_kvs.put_key.call_args[1]["KvsARN"] == EMBED_KVS_ARN

    def test_put_origins_no_kvs_arn_is_noop_success(self, mock_boto3, monkeypatch):
        """When the embed-origins KVS ARN is unset, the put is a non-fatal no-op."""
        service, _, _, mock_kvs = mock_boto3
        service.embed_origins_kvs_arn = ""

        result = service.put_application_embed_origins(
            FORM_HOST, ["https://www.acme.nl"]
        )

        assert result is True
        mock_kvs.put_key.assert_not_called()

    def test_put_origins_client_error_returns_false(self, mock_boto3):
        """A KVS API error surfaces as False."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "E_ORIG4"}
        mock_kvs.put_key.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid"}},
            "PutKey",
        )

        result = service.put_application_embed_origins(
            FORM_HOST, ["https://www.acme.nl"]
        )

        assert result is False


class TestDeleteApplicationEmbedOrigins:
    """Tests for CloudFrontDomainService.delete_application_embed_origins (Task 5.2)."""

    def test_delete_origins_success(self, mock_boto3):
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "E_ORIG5"}
        mock_kvs.delete_key.return_value = {}

        result = service.delete_application_embed_origins(FORM_HOST)

        assert result is True
        mock_kvs.delete_key.assert_called_once_with(
            KvsARN=EMBED_KVS_ARN,
            Key=FORM_HOST,
            IfMatch="E_ORIG5",
        )

    def test_delete_origins_not_found_idempotent(self, mock_boto3):
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "E_ORIG6"}
        mock_kvs.delete_key.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "missing"}},
            "DeleteKey",
        )

        result = service.delete_application_embed_origins(FORM_HOST)

        assert result is True

    def test_delete_origins_no_kvs_arn_is_noop_success(self, mock_boto3):
        service, _, _, mock_kvs = mock_boto3
        service.embed_origins_kvs_arn = ""

        result = service.delete_application_embed_origins(FORM_HOST)

        assert result is True
        mock_kvs.delete_key.assert_not_called()


def _client_error(code, op="Op"):
    return ClientError({"Error": {"Code": code, "Message": code}}, op)


class TestCreateDomainTenant:
    """Custom domain -> distribution tenant with a CloudFront-managed cert."""

    def test_create_tenant_success_returns_routing_endpoint(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.create_distribution_tenant.return_value = {
            "DistributionTenant": {"Id": "dt_1", "ConnectionGroupId": "cg_1"}
        }
        mock_cf.get_connection_group.return_value = {
            "ConnectionGroup": {"RoutingEndpoint": "d999.cloudfront.net"}
        }

        result = service.create_domain_tenant("www.acme.nl", "acme")

        assert result == {
            "success": True,
            "tenant_id": "dt_1",
            "routing_endpoint": "d999.cloudfront.net",
        }
        kwargs = mock_cf.create_distribution_tenant.call_args[1]
        assert kwargs["DistributionId"] == "EMULTITENANT"
        assert kwargs["Name"] == "www.acme.nl"
        assert kwargs["Domains"] == [{"Domain": "www.acme.nl"}]
        assert kwargs["Parameters"] == [{"Name": "slug", "Value": "acme"}]
        assert (
            kwargs["ManagedCertificateRequest"]["ValidationTokenHost"] == "cloudfront"
        )
        assert kwargs["ManagedCertificateRequest"]["PrimaryDomainName"] == "www.acme.nl"
        mock_cf.get_connection_group.assert_called_once_with(Identifier="cg_1")

    def test_create_tenant_cname_taken_returns_clear_error(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.create_distribution_tenant.side_effect = _client_error(
            "CNAMEAlreadyExists", "CreateDistributionTenant"
        )

        result = service.create_domain_tenant("www.acme.nl", "acme")

        assert result["success"] is False
        assert "already connected" in result["error"]

    def test_create_tenant_not_configured_returns_error(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        service.custom_domains_distribution_id = ""

        result = service.create_domain_tenant("www.acme.nl", "acme")

        assert result["success"] is False
        mock_cf.create_distribution_tenant.assert_not_called()


class TestGetDomainStatus:
    """Managed-cert status is mapped to ISSUED / PENDING_VALIDATION / FAILED."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("issued", "ISSUED"),
            ("pending-validation", "PENDING_VALIDATION"),
            ("validation-timed-out", "FAILED"),
            ("failed", "FAILED"),
            ("revoked", "FAILED"),
            ("expired", "FAILED"),
            ("inactive", "FAILED"),
        ],
    )
    def test_status_mapping(self, mock_boto3, raw, expected):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.return_value = {
            "DistributionTenant": {"Id": "dt_1"},
            "ETag": "E1",
        }
        mock_cf.get_managed_certificate_details.return_value = {
            "ManagedCertificateDetails": {
                "CertificateStatus": raw,
                "CertificateArn": "arn:cert",
            }
        }

        result = service.get_domain_status("www.acme.nl")

        assert result == {
            "success": True,
            "status": expected,
            "certificate_arn": "arn:cert",
        }
        mock_cf.get_distribution_tenant_by_domain.assert_called_once_with(
            Domain="www.acme.nl"
        )
        mock_cf.get_managed_certificate_details.assert_called_once_with(
            Identifier="dt_1"
        )

    def test_status_tenant_missing_returns_not_found(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.side_effect = _client_error(
            "EntityNotFound"
        )

        result = service.get_domain_status("www.acme.nl")

        assert result["success"] is False

    def test_status_api_error_returns_failure(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.side_effect = _client_error(
            "AccessDenied"
        )

        assert service.get_domain_status("www.acme.nl")["success"] is False


class TestUpdateDomainTenantSlug:
    def test_update_slug_sets_parameter_with_etag(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.return_value = {
            "DistributionTenant": {"Id": "dt_1"},
            "ETag": "E1",
        }

        assert service.update_domain_tenant_slug("www.acme.nl", "acme-new") is True
        mock_cf.update_distribution_tenant.assert_called_once_with(
            Id="dt_1",
            IfMatch="E1",
            Parameters=[{"Name": "slug", "Value": "acme-new"}],
        )

    def test_update_slug_missing_tenant_returns_false(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.side_effect = _client_error(
            "EntityNotFound"
        )

        assert service.update_domain_tenant_slug("www.acme.nl", "x") is False
        mock_cf.update_distribution_tenant.assert_not_called()


class TestDeleteDomainTenant:
    def test_delete_enabled_tenant_disables_then_deletes(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.return_value = {
            "DistributionTenant": {"Id": "dt_1", "Enabled": True},
            "ETag": "E1",
        }
        mock_cf.update_distribution_tenant.return_value = {"ETag": "E2"}

        assert service.delete_domain_tenant("www.acme.nl") is True
        mock_cf.update_distribution_tenant.assert_called_once_with(
            Id="dt_1", IfMatch="E1", Enabled=False
        )
        mock_cf.delete_distribution_tenant.assert_called_once_with(
            Id="dt_1", IfMatch="E2"
        )

    def test_delete_missing_tenant_is_idempotent(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.side_effect = _client_error(
            "EntityNotFound"
        )

        assert service.delete_domain_tenant("www.acme.nl") is True
        mock_cf.delete_distribution_tenant.assert_not_called()

    def test_delete_refused_returns_false(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.return_value = {
            "DistributionTenant": {"Id": "dt_1", "Enabled": False},
            "ETag": "E1",
        }
        mock_cf.delete_distribution_tenant.side_effect = _client_error(
            "ResourceNotDisabled", "DeleteDistributionTenant"
        )

        assert service.delete_domain_tenant("www.acme.nl") is False
        mock_cf.update_distribution_tenant.assert_not_called()


class TestCrossAccountRole:
    """PUBLIC_PAGES_AWS_ROLE_ARN makes every client use assumed-role creds."""

    def test_role_arn_set_clients_use_assumed_credentials(self, mock_env, monkeypatch):
        monkeypatch.setenv(
            "PUBLIC_PAGES_AWS_ROLE_ARN", "arn:aws:iam::506221081911:role/test-role"
        )
        with patch("boto3.client") as factory:
            sts = MagicMock()
            sts.assume_role.return_value = {
                "Credentials": {
                    "AccessKeyId": "AK",
                    "SecretAccessKey": "SK",
                    "SessionToken": "ST",
                }
            }
            factory.side_effect = lambda name, **kw: (
                sts if name == "sts" else MagicMock()
            )

            from services.cloudfront_domain_service import CloudFrontDomainService

            service = CloudFrontDomainService()

        assert sts.assume_role.call_args[1]["RoleArn"].endswith("role/test-role")
        for name in ("cloudfront", "acm"):
            call = next(c for c in factory.call_args_list if c[0][0] == name)
            assert call[1]["aws_session_token"] == "ST"
        assert service._cli_env()["AWS_SESSION_TOKEN"] == "ST"

    def test_role_arn_unset_uses_default_credentials(self, mock_boto3):
        service, _, _, _ = mock_boto3
        assert service._client_kwargs == {}
        assert service._cli_env() is None


class TestTenantDnsPrerequisite:
    """Tenant creation needs the CNAME in place; the target is known up front."""

    def test_create_tenant_ownership_not_verified_is_dns_not_ready(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.create_distribution_tenant.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InvalidArgument",
                    "Message": "The provided Domain Name is not valid. Could not "
                    "verify Domain Name ownership.",
                }
            },
            "CreateDistributionTenant",
        )

        result = service.create_domain_tenant("www.acme.nl", "acme")

        assert result["success"] is False
        assert result["dns_not_ready"] is True

    def test_get_routing_endpoint_returns_default_group(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.list_connection_groups.return_value = {
            "ConnectionGroups": [
                {"IsDefault": False, "RoutingEndpoint": "dother.cloudfront.net"},
                {"IsDefault": True, "RoutingEndpoint": "ddefault.cloudfront.net"},
            ]
        }

        assert service.get_routing_endpoint() == "ddefault.cloudfront.net"

    def test_get_routing_endpoint_error_returns_none(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.list_connection_groups.side_effect = _client_error("AccessDenied")

        assert service.get_routing_endpoint() is None

    def test_status_without_tenant_flags_not_found(self, mock_boto3):
        service, mock_cf, _, _ = mock_boto3
        mock_cf.get_distribution_tenant_by_domain.side_effect = _client_error(
            "EntityNotFound"
        )

        result = service.get_domain_status("www.acme.nl")

        assert result["success"] is False
        assert result["not_found"] is True
