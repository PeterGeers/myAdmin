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
Here are the realistic options, from simplest to most complex:

Option 1: CSS injection in the iframe (easiest, 1 hour)

Hide MkDocs nav items based on user roles by injecting CSS after the iframe loads. The nav items have predictable CSS selectors. A Finance_Read user would see Banking, Invoices, Reports, Tax docs but not STR, Admin, or Tenant Admin.

Pros: No backend changes, no MkDocs rebuild, works with current setup Cons: Only works same-origin (local Docker), not on GitHub Pages → Railway (cross-origin). Nav items are hidden but still accessible via direct URL.

Option 2: Pass roles as URL parameter, filter server-side (moderate, 3-4 hours)

Add a query parameter like /docs/?roles=Finance_Read,Finance_CRUD. The Flask route reads the roles and serves a modified HTML page with nav items stripped server-side using BeautifulSoup or similar.

Pros: Works everywhere, truly removes content from HTML Cons: Requires backend changes, adds complexity to the docs route, needs role validation

Option 3: Multiple MkDocs builds per role profile (complex, 8+ hours)

Build separate doc sites: /docs/fin/, /docs/str/, /docs/full/. Each contains only the relevant modules. The helpLinks.ts maps roles to the correct site.

Pros: Clean separation, no runtime filtering Cons: Triple the build output, triple the maintenance, content duplication

Option 4: Keep current approach + improve context (zero effort)

The ? button already opens the correct page for the current module. The user sees relevant help immediately. The full navigation sidebar is visible but users naturally stay on the page they opened. This is how most SaaS help systems work (Notion, Slack, etc. — help is contextual but the full docs are browsable).

Pros: Already done, no maintenance overhead Cons: Users can browse docs for modules they don't have access to (not a security issue, just noise)

My recommendation: Option 1 for now, Option 2 later if needed.

Option 1 gives you role-based nav filtering locally with minimal effort. For production (GitHub Pages → Railway cross-origin), the CSS injection silently fails and users see the full nav — which is acceptable since the help button already opens the right page contextually.

Want me to implement Option 1?