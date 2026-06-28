"""
Test: Validate that the git pre-commit hook keeps backend/docs-site in sync with docs/site.

This test verifies that:
1. The pre-commit hook exists and contains mkdocs build + copy logic
2. The backend/docs-site directory exists (Railway deployment target)
3. The docs source (docs/docs/) and built output (backend/docs-site/) are in sync
4. Key documentation pages exist in both source and built output

These checks catch cases where:
- The hook was accidentally removed or broken
- Someone committed docs changes without the hook running
- The built site is stale compared to the source
"""

import os
import pytest

# Resolve project root (3 levels up from backend/tests/unit/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


@pytest.mark.skipif(os.getenv('CI') == 'true', reason="Pre-commit hook not present in CI environment")
class TestDocsPreCommitHook:
    """Validate the pre-commit hook that builds and syncs MkDocs to backend/docs-site."""

    def test_pre_commit_hook_exists(self):
        """The pre-commit hook file must exist."""
        hook_path = os.path.join(PROJECT_ROOT, '.git', 'hooks', 'pre-commit')
        assert os.path.isfile(hook_path), (
            f"Pre-commit hook not found at {hook_path}. "
            "This hook is required to rebuild MkDocs and sync to backend/docs-site on commit."
        )

    def test_pre_commit_hook_contains_mkdocs_build(self):
        """The hook must contain the mkdocs build command."""
        hook_path = os.path.join(PROJECT_ROOT, '.git', 'hooks', 'pre-commit')
        if not os.path.isfile(hook_path):
            pytest.skip("Pre-commit hook not found")

        content = open(hook_path, 'r', encoding='utf-8').read()
        assert 'mkdocs' in content.lower(), (
            "Pre-commit hook does not reference mkdocs. "
            "The hook should run 'mkdocs build' when docs/ files change."
        )

    def test_pre_commit_hook_copies_to_backend(self):
        """The hook must copy built docs to backend/docs-site for Railway."""
        hook_path = os.path.join(PROJECT_ROOT, '.git', 'hooks', 'pre-commit')
        if not os.path.isfile(hook_path):
            pytest.skip("Pre-commit hook not found")

        content = open(hook_path, 'r', encoding='utf-8').read()
        assert 'backend/docs-site' in content, (
            "Pre-commit hook does not copy to backend/docs-site. "
            "Railway serves docs from backend/docs-site/ — the hook must sync this folder."
        )

    def test_pre_commit_hook_stages_docs_site(self):
        """The hook must git-add the updated backend/docs-site."""
        hook_path = os.path.join(PROJECT_ROOT, '.git', 'hooks', 'pre-commit')
        if not os.path.isfile(hook_path):
            pytest.skip("Pre-commit hook not found")

        content = open(hook_path, 'r', encoding='utf-8').read()
        assert 'git add' in content and 'docs-site' in content, (
            "Pre-commit hook does not stage backend/docs-site after copying. "
            "Without 'git add backend/docs-site', the rebuilt docs won't be committed."
        )

    def test_pre_commit_hook_is_executable(self):
        """The hook file must be executable (on Unix-like systems)."""
        hook_path = os.path.join(PROJECT_ROOT, '.git', 'hooks', 'pre-commit')
        if not os.path.isfile(hook_path):
            pytest.skip("Pre-commit hook not found")

        # On Windows, file permissions work differently — check shebang instead
        if os.name == 'nt':
            content = open(hook_path, 'r', encoding='utf-8').read()
            assert content.startswith('#!'), (
                "Pre-commit hook is missing shebang line (#!/bin/sh). "
                "Git needs this to execute the hook."
            )
        else:
            assert os.access(hook_path, os.X_OK), (
                f"Pre-commit hook at {hook_path} is not executable. "
                "Run: chmod +x .git/hooks/pre-commit"
            )


class TestDocsSiteSync:
    """Validate that backend/docs-site is in sync with docs source."""

    def test_backend_docs_site_exists(self):
        """backend/docs-site/ must exist for Railway deployment."""
        docs_site = os.path.join(PROJECT_ROOT, 'backend', 'docs-site')
        assert os.path.isdir(docs_site), (
            "backend/docs-site/ directory not found. "
            "Railway serves docs from this folder. Run the pre-commit hook or "
            "'mkdocs build -f docs/mkdocs.yml && cp -r docs/site backend/docs-site' to create it."
        )

    def test_docs_source_exists(self):
        """docs/docs/ source directory must exist."""
        docs_source = os.path.join(PROJECT_ROOT, 'docs', 'docs')
        assert os.path.isdir(docs_source), (
            "docs/docs/ source directory not found. "
            "MkDocs source files should be in docs/docs/."
        )

    def test_mkdocs_config_exists(self):
        """docs/mkdocs.yml must exist."""
        mkdocs_yml = os.path.join(PROJECT_ROOT, 'docs', 'mkdocs.yml')
        assert os.path.isfile(mkdocs_yml), (
            "docs/mkdocs.yml not found. "
            "MkDocs configuration is required to build the documentation site."
        )

    def test_key_pages_exist_in_built_site(self):
        """Key documentation pages must exist in the built site."""
        docs_site = os.path.join(PROJECT_ROOT, 'backend', 'docs-site')
        if not os.path.isdir(docs_site):
            pytest.skip("backend/docs-site/ not found")

        expected_pages = [
            'index.html',
            os.path.join('getting-started', 'first-login', 'index.html'),
            os.path.join('banking', 'index.html'),
            os.path.join('tenant-admin', 'index.html'),
        ]

        missing = []
        for page in expected_pages:
            if not os.path.isfile(os.path.join(docs_site, page)):
                missing.append(page)

        assert not missing, (
            f"Missing pages in backend/docs-site/: {missing}. "
            "The built site may be stale. Rebuild with: "
            "'mkdocs build -f docs/mkdocs.yml && rm -rf backend/docs-site && cp -r docs/site backend/docs-site'"
        )

    def test_source_pages_have_both_languages(self):
        """Each docs source page should have both NL (.md) and EN (.en.md) versions."""
        docs_source = os.path.join(PROJECT_ROOT, 'docs', 'docs')
        if not os.path.isdir(docs_source):
            pytest.skip("docs/docs/ not found")

        missing_translations = []
        for root, dirs, files in os.walk(docs_source):
            nl_files = {f for f in files if f.endswith('.md') and not f.endswith('.en.md')}
            en_files = {f.replace('.en.md', '.md') for f in files if f.endswith('.en.md')}

            for nl_file in nl_files:
                if nl_file not in en_files:
                    rel_path = os.path.relpath(os.path.join(root, nl_file), docs_source)
                    en_version = nl_file.replace('.md', '.en.md')
                    missing_translations.append(f"{rel_path} (missing {en_version})")

        assert not missing_translations, (
            f"NL pages without EN translation: {missing_translations}. "
            "Each documentation page should have both .md (NL) and .en.md (EN) versions."
        )

    def test_built_site_not_empty(self):
        """The built site should contain a reasonable number of files."""
        docs_site = os.path.join(PROJECT_ROOT, 'backend', 'docs-site')
        if not os.path.isdir(docs_site):
            pytest.skip("backend/docs-site/ not found")

        html_count = 0
        for root, dirs, files in os.walk(docs_site):
            html_count += sum(1 for f in files if f.endswith('.html'))

        # With ~40 source pages × 2 languages, expect at least 50 HTML files
        assert html_count >= 50, (
            f"Only {html_count} HTML files in backend/docs-site/. "
            "Expected at least 50. The built site may be incomplete or stale."
        )
