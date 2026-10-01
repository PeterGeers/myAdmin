# Generic solution for database access
See an earlier attemt: .kiro\specs\Common\Database\database-abstraction-layer\requirements.md

We still encounter a lot of local (non-generic) database related functions.

Question 1: How is this possible
Question 2: How can we solve this. Below an approach from the session to solve the actual problem see .kiro\specs\Common\Database\get-connection-contextmanager-regression

## Good — approach B is the "solve it properly"

Good — approach B is the "solve it properly" route: make every caller use the context-managed API so the leaky get_connection() boundary stops being used at all. Let me scope it accurately so you know what you're signing up for. First I need the true count of call sites and the shapes they take, since the grep truncated. Let me get exact numbers.


1 tool call
Command
cd /home/peter/projects/myAdmin && echo "=== total raw get_connection assignment sites ===" && grep -rnE '=\s*(self\.)?db\.get_connection\(|=\s*DatabaseManager\([^)]*\)\.get_connection\(' backend/src --include='*.py' | grep -v '/tests/' | wc -l && echo "=== files affected ===" && grep -rlE '=\s*(self\.)?db\.get_connection\(|=\s*DatabaseManager\([^)]*\)\.get_connection\(' backend/src --include='*.py' | grep -v '/tests/' | sort && echo "=== files affected COUNT ===" && grep -rlE '=\s*(self\.)?db\.get_connection\(|=\s*DatabaseManager\([^)]*\)\.get_connection\(' backend/src --include='*.py' | grep -v '/tests/' | wc -l; printf '\n<<<DONE marker=%s>>>\n' "$?"
cd /home/peter/projects/myAdmin && echo "=== total raw get_connection assignment sites ===" && grep -rnE '=\s*(self\.)?db\.get_connection\(|=\s*DatabaseManager\([^)]*\)\.get_connection\(' backend/src --include='*.py' | grep -v '/tests/' | wc -l && echo "=== files affected ===" && grep -rlE '=\s*(self\.)?db\.get_connection\(|=\s*DatabaseManager\([^)]*\)\.get_connection\(' backend/src --include='*.py' | grep -v '/tests/' | sort && echo "=== files affected COUNT ===" && grep -rlE '=\s*(self\.)?db\.get_connection\(|=\s*DatabaseManager\([^)]*\)\.get_connection\(' backend/src --include='*.py' | grep -v '/tests/' | wc -l; printf '\n<<<DONE marker=%s>>>\n' "$?"

=== total raw get_connection assignment sites ===
56
=== files affected ===
backend/src/banking_checks.py
backend/src/banking_processor.py
backend/src/bnb_routes.py
backend/src/btw_processor.py
backend/src/business_pricing_model.py
backend/src/hybrid_pricing_optimizer.py
backend/src/pdf_decision_helpers.py
backend/src/pdf_validation.py
backend/src/report_generators/financial_report_generator.py
backend/src/reporting_routes.py
backend/src/routes/aangifte_ib_routes.py
backend/src/routes/banking_routes.py
backend/src/routes/financial_reporting_routes.py
backend/src/routes/str_routes.py
backend/src/services/banking_mutatie_service.py
backend/src/services/country_report_service.py
backend/src/services/year_end_service.py
backend/src/services/zzp_invoice_numbering.py
backend/src/str_channel_routes.py
backend/src/str_invoice_routes.py
backend/src/xlsx_export.py
=== files affected COUNT ===
21
<<<DONE marker=0>>>
(.venv) myAdmin
56 call sites across 21 files. Now let me understand the shapes these calls take, because that determines how mechanical vs. delicate the migration is. Let me sample a few representative patterns — a simple read, a commit/write, a generator, and the pdf_decision_helpers connectivity check (which just opens/closes to test).


4 tool calls
Read File

banking_routes.py
Read File

business_pricing_model.py
Read File

pdf_decision_helpers.py
Read File

reporting_routes.py
Now I have a clear picture of the shapes. This is what approach B involves.

What approach B takes to do right
Scope: 56 call sites across 21 files. But they aren't uniform — they fall into distinct shapes, and each shape needs a different (careful) transformation. This is why B is "large":

Shape 1 — plain read/write with cursor (the majority).

python

conn = db.get_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute(...); rows = cursor.fetchall()
cursor.close(); conn.close()
→ becomes with db.get_cursor() as (cursor, conn):. Mostly mechanical, but you must preserve dictionary=True vs plain cursor (some sites use conn.cursor() without dictionary), and preserve any explicit conn.commit() on writes. get_cursor doesn't auto-commit — transaction() does — so write sites must map to with db.transaction() or keep an explicit commit, or data silently won't persist. That's the highest-risk part.

Shape 2 — pandas pd.read_sql(query, conn, ...) (e.g. business_pricing_model.py, hybrid_pricing_optimizer.py). These pass the raw connection to pandas, not a cursor. get_cursor yields a cursor, so these need with db.get_cursor() as (_, conn): pd.read_sql(query, conn, ...) — using the conn from the pair, ignoring the cursor. Different transform from Shape 1.

Shape 3 — a class that wraps get_connection in its own @contextmanager get_cursor (reporting_routes.py line 27). This one is easy — its internal get_cursor just needs to delegate to self.db.get_cursor() and it fixes all its callers at once.

Shape 4 — connectivity check (pdf_decision_helpers.py): test_connection = db.get_connection(); if test_connection: test_connection.close(). Just probes that a connection opens. Needs with db.get_cursor(): pass or a dedicated health check.

Shape 5 — generators that yield mid-iteration (pdf_validation.py validate_pdf_urls_with_progress): the connection is held open across yields. Wrapping in with changes the lifetime — needs care that the connection stays open for the whole generator.

The steering-rule angle. You were told everything goes through one central manager — and it does, but get_connection() is a leaky method on that manager that returns inconsistent types. Approach B's real value is that after the migration, get_connection() should become private/removed so no caller can ever use the raw pattern again. That's the part that actually enforces "one centralised way." Without that final step, B just fixes today's symptoms and the pattern creeps back.

Verification burden. Each shape needs tests. There's already good scaffolding (test_database_pool_config.py, tenant-filtering integration tests). The migration needs: per-file unit/integration coverage that the endpoint returns 200 with data, that writes still commit, and a guard test asserting no = db.get_connection() raw-assignment pattern remains in backend/src (a lint/AST check) so it can't regress.

Rough effort: 21 files, 56 sites, ~5 distinct shapes, plus removing/privatizing get_connection, plus a regression-guard test and running the full backend suite against both local Docker and Railway. This is a multi-task spec, not a one-shot edit. It's very doable and mechanical for the bulk of it, with a handful of delicate sites (writes/commits, pandas, generators).

Important caveat — production is down now. Your data views are 500ing in production today. Approach B is the right long-term fix but it's a large change that needs careful review before deploy. Approach A (normalize get_connection() to always return a raw connection — a few lines in database.py) would restore production immediately and is fully compatible with doing B afterward.
