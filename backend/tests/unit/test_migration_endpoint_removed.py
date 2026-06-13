"""
Unit tests verifying migration endpoint has been removed.

After removing migration_routes.py and its blueprint registration,
the /api/migration/opening-balances/migrate path should return 404.

Requirements: 3.1, 3.3
Reference: .kiro/specs/security-hardening/design.md
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src directory to Python path
backend_dir = Path(__file__).parent.parent.parent
src_dir = backend_dir / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


@pytest.fixture
def app(mock_env):
    """Create Flask app for testing."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.role_cache.get_tenant_roles', return_value=['TenantAdmin']), \
         patch('database.DatabaseManager') as mock_db_class:

        mock_creds.return_value = ('test@example.com', ['TenantAdmin'], None)
        mock_db_class.return_value = MagicMock()

        from src.app import app as flask_app
        flask_app.config['TESTING'] = True
        yield flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    with app.test_client() as test_client:
        with app.app_context():
            yield test_client


@pytest.mark.unit
class TestMigrationEndpointRemoved:
    """Verify migration endpoint is no longer registered."""

    def test_migration_post_returns_404(self, client):
        """POST /api/migration/opening-balances/migrate returns 404."""
        response = client.post(
            '/api/migration/opening-balances/migrate',
            json={'secret': 'migrate-opening-balances-2026'}
        )
        assert response.status_code == 404

    def test_migration_get_returns_404(self, client):
        """GET /api/migration/opening-balances/migrate returns 404."""
        response = client.get('/api/migration/opening-balances/migrate')
        assert response.status_code == 404

    def test_no_migration_route_registered(self, app):
        """No route matches the migration path pattern."""
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        migration_routes = [r for r in rules if 'migration' in r]
        assert len(migration_routes) == 0, f"Found migration routes: {migration_routes}"

    def test_migration_module_not_importable_from_routes(self):
        """The migration_routes module no longer exists."""
        import importlib
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module('routes.migration_routes')
