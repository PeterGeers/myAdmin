"""
Unit tests for EmailTemplateService

Tests template rendering logic, variable substitution, and template retrieval.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.email_template_service import EmailTemplateService


@pytest.mark.unit
class TestEmailTemplateServiceInit:
    """Test EmailTemplateService initialization"""

    def test_init_sets_template_dir(self):
        """Template dir should point to backend/templates/email/"""
        service = EmailTemplateService()
        assert service.template_dir.endswith(os.path.join('templates', 'email'))

    def test_init_without_administration(self):
        """Should initialize with None administration"""
        service = EmailTemplateService()
        assert service.administration is None

    def test_init_with_administration(self):
        """Should store administration for tenant-specific template loading"""
        service = EmailTemplateService(administration='TestTenant')
        assert service.administration == 'TestTenant'


@pytest.mark.unit
class TestRenderTemplate:
    """Test render_template method — variable substitution and fallback logic"""

    def setup_method(self):
        self.service = EmailTemplateService()

    def test_substitutes_single_variable(self, tmp_path):
        """Should replace a single {{variable}} placeholder"""
        template = tmp_path / "greeting.html"
        template.write_text("Hello {{name}}!", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('greeting', {'name': 'Alice'}, format='html')
        assert result == "Hello Alice!"

    def test_substitutes_multiple_variables(self, tmp_path):
        """Should replace all placeholders in a single pass"""
        template = tmp_path / "msg.html"
        template.write_text("Hi {{name}}, welcome to {{tenant}}.", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('msg', {'name': 'Bob', 'tenant': 'Acme'})
        assert result == "Hi Bob, welcome to Acme."

    def test_substitutes_repeated_variable(self, tmp_path):
        """Should replace all occurrences of the same variable"""
        template = tmp_path / "repeat.html"
        template.write_text("{{x}} and {{x}} again", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('repeat', {'x': 'OK'})
        assert result == "OK and OK again"

    def test_unmatched_placeholders_remain(self, tmp_path):
        """Placeholders not in variables dict should remain unchanged"""
        template = tmp_path / "partial.html"
        template.write_text("{{known}} and {{unknown}}", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('partial', {'known': 'yes'})
        assert result == "yes and {{unknown}}"

    def test_empty_variables_dict(self, tmp_path):
        """Template should remain unchanged if no variables are provided"""
        template = tmp_path / "empty.html"
        template.write_text("Hello {{name}}", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('empty', {})
        assert result == "Hello {{name}}"

    def test_variable_value_converted_to_string(self, tmp_path):
        """Non-string values should be converted via str()"""
        template = tmp_path / "num.html"
        template.write_text("Count: {{count}}", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('num', {'count': 42})
        assert result == "Count: 42"

    def test_returns_none_when_template_not_found(self, tmp_path):
        """Should return None if the template file does not exist"""
        self.service.template_dir = str(tmp_path)
        result = self.service.render_template('nonexistent', {'x': 'y'})
        assert result is None

    def test_txt_format_uses_txt_extension(self, tmp_path):
        """format='txt' should load .txt file"""
        template = tmp_path / "note.txt"
        template.write_text("Plain: {{msg}}", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('note', {'msg': 'hello'}, format='txt')
        assert result == "Plain: hello"

    def test_special_characters_in_values(self, tmp_path):
        """Values with HTML/special characters should be inserted as-is"""
        template = tmp_path / "special.html"
        template.write_text("<p>{{content}}</p>", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('special', {'content': '<b>Bold & "Quoted"</b>'})
        assert result == '<p><b>Bold & "Quoted"</b></p>'


@pytest.mark.unit
class TestRenderTemplateLanguageFallback:
    """Test language-specific template loading and fallback"""

    def setup_method(self):
        self.service = EmailTemplateService()

    def test_loads_localized_template_when_exists(self, tmp_path):
        """Should load template_nl.html when language='nl'"""
        (tmp_path / "greet_nl.html").write_text("Hallo {{name}}!", encoding='utf-8')
        (tmp_path / "greet.html").write_text("Hello {{name}}!", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('greet', {'name': 'Jan'}, language='nl')
        assert result == "Hallo Jan!"

    def test_falls_back_to_english_when_localized_missing(self, tmp_path):
        """Should fall back to base template when localized version not found"""
        (tmp_path / "greet.html").write_text("Hello {{name}}!", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('greet', {'name': 'Jan'}, language='nl')
        assert result == "Hello Jan!"

    def test_english_language_loads_base_template(self, tmp_path):
        """language='en' should directly load the base template (no _en suffix)"""
        (tmp_path / "greet.html").write_text("Hello {{name}}!", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('greet', {'name': 'Alice'}, language='en')
        assert result == "Hello Alice!"

    def test_default_language_is_nl(self, tmp_path):
        """When language is None, should default to 'nl' and try localized first"""
        (tmp_path / "greet_nl.html").write_text("Hallo {{name}}!", encoding='utf-8')
        (tmp_path / "greet.html").write_text("Hello {{name}}!", encoding='utf-8')
        self.service.template_dir = str(tmp_path)

        result = self.service.render_template('greet', {'name': 'Piet'}, language=None)
        assert result == "Hallo Piet!"


@pytest.mark.unit
class TestLoadFromGoogleDrive:
    """Test _load_from_google_drive — tenant-specific template loading from storage"""

    def test_returns_none_without_administration(self):
        """Should return None immediately if no administration set"""
        service = EmailTemplateService(administration=None)
        result = service._load_from_google_drive('user_invitation')
        assert result is None

    @patch('database.DatabaseManager')
    def test_returns_template_content_from_db(self, mock_db_cls):
        """Should return template_content directly if stored in DB"""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [
            {'template_content': '<h1>Custom Template</h1>', 'template_file_id': None}
        ]
        mock_db_cls.return_value = mock_db

        service = EmailTemplateService(administration='TestTenant')
        result = service._load_from_google_drive('user_invitation')
        assert result == '<h1>Custom Template</h1>'

    @patch('database.DatabaseManager')
    def test_returns_none_when_no_db_results(self, mock_db_cls):
        """Should return None if no custom template found in DB"""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []
        mock_db_cls.return_value = mock_db

        service = EmailTemplateService(administration='TestTenant')
        result = service._load_from_google_drive('user_invitation')
        assert result is None

    @patch('database.DatabaseManager')
    def test_returns_none_on_exception(self, mock_db_cls):
        """Should return None and not raise if DB query fails"""
        mock_db_cls.side_effect = Exception("DB connection failed")

        service = EmailTemplateService(administration='TestTenant')
        result = service._load_from_google_drive('user_invitation')
        assert result is None

    @patch('database.DatabaseManager')
    def test_queries_correct_template_type(self, mock_db_cls):
        """Should query the DB with the correct administration and template_type"""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []
        mock_db_cls.return_value = mock_db

        service = EmailTemplateService(administration='AcmeBV')
        service._load_from_google_drive('tenant_added')

        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('params')
        assert params == ['AcmeBV', 'tenant_added']


@pytest.mark.unit
class TestRenderTemplateWithGoogleDrive:
    """Test render_template prioritizes Google Drive templates over local files"""

    def test_uses_google_drive_template_when_available(self, tmp_path):
        """Should use Drive template content instead of local file"""
        (tmp_path / "invite.html").write_text("Local: {{name}}", encoding='utf-8')

        service = EmailTemplateService(administration='TestTenant')
        service.template_dir = str(tmp_path)

        with patch.object(service, '_load_from_google_drive', return_value="Custom: {{name}}"):
            result = service.render_template('invite', {'name': 'Bob'})

        assert result == "Custom: Bob"

    def test_falls_back_to_local_when_drive_returns_none(self, tmp_path):
        """Should use local template if Drive returns None"""
        (tmp_path / "invite.html").write_text("Local: {{name}}", encoding='utf-8')

        service = EmailTemplateService(administration='TestTenant')
        service.template_dir = str(tmp_path)

        with patch.object(service, '_load_from_google_drive', return_value=None):
            result = service.render_template('invite', {'name': 'Bob'})

        assert result == "Local: Bob"


@pytest.mark.unit
class TestRenderUserInvitation:
    """Test the render_user_invitation convenience method"""

    def test_renders_with_all_variables(self, tmp_path):
        """Should pass all variables to the template"""
        template_content = (
            "Email: {{email}}, Pass: {{temporary_password}}, "
            "Tenant: {{tenant}}, URL: {{login_url}}"
        )
        (tmp_path / "user_invitation.html").write_text(template_content, encoding='utf-8')

        service = EmailTemplateService()
        service.template_dir = str(tmp_path)

        result = service.render_user_invitation(
            email='user@example.com',
            temporary_password='Temp123!',
            tenant='AcmeBV',
            login_url='https://app.example.com',
            language='en'
        )

        assert 'user@example.com' in result
        assert 'Temp123!' in result
        assert 'AcmeBV' in result
        assert 'https://app.example.com' in result

    @patch('services.email_template_service.EmailTemplateService._detect_user_language')
    def test_detects_language_when_not_provided(self, mock_detect, tmp_path):
        """Should call _detect_user_language when language is None"""
        mock_detect.return_value = 'nl'
        (tmp_path / "user_invitation_nl.html").write_text("NL: {{email}}", encoding='utf-8')

        service = EmailTemplateService()
        service.template_dir = str(tmp_path)

        service.render_user_invitation(
            email='user@example.com',
            temporary_password='pass',
            tenant='Acme',
            login_url='https://app.example.com',
            language=None
        )

        mock_detect.assert_called_once_with('user@example.com', 'Acme')

    @patch('utils.frontend_url.get_frontend_url', return_value='https://default.example.com')
    def test_uses_frontend_url_when_login_url_not_provided(self, mock_url, tmp_path):
        """Should use get_frontend_url() as default login_url"""
        (tmp_path / "user_invitation.html").write_text("URL: {{login_url}}", encoding='utf-8')

        service = EmailTemplateService()
        service.template_dir = str(tmp_path)

        result = service.render_user_invitation(
            email='user@example.com',
            temporary_password='pass',
            tenant='Acme',
            login_url=None,
            language='en'
        )

        assert 'https://default.example.com' in result


@pytest.mark.unit
class TestDetectUserLanguage:
    """Test _detect_user_language priority logic"""

    def setup_method(self):
        self.service = EmailTemplateService()

    @patch('services.user_language_service.get_user_language', return_value='en')
    def test_returns_user_language_from_cognito(self, mock_lang):
        """Priority 1: user's preferred language from Cognito"""
        result = self.service._detect_user_language('user@example.com', 'Acme')
        assert result == 'en'

    @patch('services.user_language_service.get_user_language', return_value=None)
    @patch('services.tenant_language_service.get_tenant_language', return_value='en')
    def test_falls_back_to_tenant_language(self, mock_tenant_lang, mock_user_lang):
        """Priority 2: tenant's default language"""
        result = self.service._detect_user_language('user@example.com', 'Acme')
        assert result == 'en'

    @patch('services.user_language_service.get_user_language', side_effect=Exception("Service error"))
    @patch('services.tenant_language_service.get_tenant_language', side_effect=Exception("Service error"))
    def test_defaults_to_nl_on_errors(self, mock_tenant_lang, mock_user_lang):
        """Priority 3: defaults to 'nl' when both services fail"""
        result = self.service._detect_user_language('user@example.com', 'Acme')
        assert result == 'nl'

    @patch('services.user_language_service.get_user_language', return_value='fr')
    @patch('services.tenant_language_service.get_tenant_language', return_value='en')
    def test_ignores_unsupported_user_language(self, mock_tenant_lang, mock_user_lang):
        """Should ignore user language if not in ['nl', 'en']"""
        result = self.service._detect_user_language('user@example.com', 'Acme')
        assert result == 'en'

    @patch('services.user_language_service.get_user_language', return_value=None)
    @patch('services.tenant_language_service.get_tenant_language', return_value='de')
    def test_ignores_unsupported_tenant_language(self, mock_tenant_lang, mock_user_lang):
        """Should ignore tenant language if not in ['nl', 'en'] and default to nl"""
        result = self.service._detect_user_language('user@example.com', 'Acme')
        assert result == 'nl'


@pytest.mark.unit
class TestGetInvitationSubject:
    """Test get_invitation_subject for language-specific subject lines"""

    def setup_method(self):
        self.service = EmailTemplateService()

    def test_dutch_subject(self):
        """Should return Dutch subject line"""
        result = self.service.get_invitation_subject('AcmeBV', language='nl')
        assert result == "Welkom bij myAdmin - AcmeBV Uitnodiging"

    def test_english_subject(self):
        """Should return English subject line"""
        result = self.service.get_invitation_subject('AcmeBV', language='en')
        assert result == "Welcome to myAdmin - AcmeBV Invitation"

    def test_none_language_returns_english(self):
        """When language is None, should default to English"""
        result = self.service.get_invitation_subject('AcmeBV', language=None)
        assert result == "Welcome to myAdmin - AcmeBV Invitation"

    def test_subject_includes_tenant_name(self):
        """Subject should include the tenant name"""
        result = self.service.get_invitation_subject('MyCompany', language='en')
        assert 'MyCompany' in result
