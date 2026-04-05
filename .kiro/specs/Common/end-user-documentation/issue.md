Here's the summary of the production impact and what was fixed:

Railway Backend:

Dockerfile reverted to original (no mkdocs install) — no build time or image size impact
The docs/site/ folder is pre-built and committed to git. For Railway, you'll need to make sure the docs/site/ folder is accessible. Since Railway builds from ./backend/ context, the docs folder at the project root isn't included. Two options:
Copy docs/site/ into backend/docs-site/ before deploying (a build script)
Or add a Railway volume/mount config
GitHub Actions Frontend:

Added REACT_APP_DOCS_URL: /docs to the build env
The getFullDocsUrl() function will produce https://invigorating-celebration-production.up.railway.app/docs/... for the "Open in new tab" link
The drawer fetch will use relative /docs/... which will fail from GitHub Pages (different origin) — it'll gracefully fall back to opening the full Railway URL in a new tab. This is acceptable behavior.
Local Docker:

Works correctly with the ./docs/site:/app/docs-site volume mount
Drawer fetches content inline, "Open full docs" link points to the backend


What about HELP for limited scope FIN only or READ only