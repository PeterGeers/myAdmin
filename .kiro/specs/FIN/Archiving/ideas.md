# Archiving — Ideas & Decisions

## Original Requirements

- Enable archive function for transactions
- Store records that may not be changed anymore in a read-only datastore
- Enable reporting the archived data in the same way as the non-archived data
- Trigger: most recent closed year minus 1 year
- Data should appear in reports (based on vw_mutaties) but NOT in the Banking Transactions tab
- Un-archive (restore) per financial year should be possible
- After year closure the previous year should be added to the archive
- Tenant can request to remove (purge) records before a certain year

## Approach: Parquet Archive of vw_mutaties + mutaties superset

### Key Insight

`vw_mutaties` already denormalizes everything — it joins `mutaties` with `rekeningschema` and produces a flat row with Aangifte, AccountName, Parent, VW, etc. Archiving the view output (not raw `mutaties` rows) creates a self-contained snapshot that doesn't depend on `rekeningschema` at query time.

### What Gets Archived

A superset of `vw_mutaties` columns PLUS extra `mutaties` columns needed for restore:

| From vw_mutaties                             | From mutaties (extra)    |
| -------------------------------------------- | ------------------------ |
| Aangifte, TransactionNumber, TransactionDate | ID (original)            |
| TransactionDescription, Amount, Reknum       | Ref1, Ref2, Ref4         |
| AccountName, Parent, VW                      | Debet, Credit (original) |
| jaar, kwartaal, maand, week                  |                          |
| ReferenceNumber, administration, Ref3        |                          |

This gives:

- Full reporting compatibility (use the vw_mutaties columns)
- Full restore capability (use the extra columns to reconstruct mutaties rows)
- One Parquet file per tenant per year

### Storage

- S3 bucket (AWS stack already in place) or local filesystem for Docker
- Path: `archive/{tenant}/{year}.parquet`
- Compression: ~11K transactions/year → ~200-500KB per file

### Reporting Merge

```python
def get_combined_mutaties(tenant, years):
    live_df = query_vw_mutaties(tenant, years)
    archive_df = read_parquet_archive(tenant, archived_years)
    return pd.concat([live_df, archive_df])
```

### Pros

- Self-contained: archived rows have account names, parent, VW, tax category baked in
- No joins needed. If rekeningschema changes later, archived data still reflects the state at archive time
- Reporting is trivial: same DataFrame shape as vw_mutaties, just pd.concat and done
- Restore is possible: Parquet contains original Debet/Credit, ID, Ref1/2/4
- No MySQL overhead: archived years don't consume DB connections, don't need indexes
- Compression: tiny files, cheap S3 storage
- Immutable by design: Parquet files are write-once, perfect for read-only archives

### Cons / Watch Items

- vw_mutaties has two rows per transaction (debet + credit side via UNION ALL). Restore needs to deduplicate back to one mutaties row. Solved by storing original ID
- Reporting endpoints need to query MySQL for live years + read Parquet for archived years + concat
- No ad-hoc SQL across live + archived. Need Python/DuckDB for that
- vw_mutaties doesn't have Ref1, Ref2, Ref4, original Debet/Credit — solved by storing the superset

### Decision

✅ Agreed: Parquet archive of vw_mutaties superset, stored per tenant per year.

---

## Open Questions (to discuss before requirements)

### 1. Storage Location

S3 is the obvious choice since we're on AWS, but local Docker development needs a fallback.

Options:

- **S3 for production, local `archive/` folder for Docker** — mirrors the Google Drive pattern already used
- **Local filesystem everywhere** — simpler, Railway has persistent storage too
- **S3 everywhere** — even local dev uses S3 (needs AWS credentials locally, which are already configured)

### 2. When to Archive — User Choice vs Automatic

"Most recent closed year minus 1" means if you close 2025, then 2024 and earlier become eligible.

- Should the user **pick which years** to archive (e.g., a checklist of eligible years)?
- Or should it **archive all eligible years at once** automatically?
- Or a **prompt after year closure**: "Year 2025 is closed. Would you like to archive 2024 and earlier?"

### 3. Restore and rekeningschema Drift

Since `vw_mutaties` has two rows per transaction (debet + credit side), restoring back to `mutaties` means deduplicating. The original `ID` in the Parquet solves this — group by ID, take the debet row's Reknum as Debet, credit row's Reknum as Credit.

But: what if `rekeningschema` changed since archiving? The restored row might reference an account that was renamed or deleted. The FK constraint would block the insert.

Options:

- **Validate against current rekeningschema** and warn about mismatches before restoring
- **Force-insert** by temporarily disabling FK checks (risky)
- **Store the original mutaties row separately** in the Parquet (not just the view output) — cleanest for restore, slightly larger files

### 4. Purge and Legal Retention

With Parquet, purging is literally deleting a file. Simple.

But should there be a **minimum retention period**? Dutch tax law (Belastingdienst) requires 7 years of financial records.

Options:

- Enforce a hard minimum (e.g., cannot purge records less than 7 years old)
- Warn but allow (soft limit with confirmation)
- Leave it to the tenant (no enforcement, just audit log)

### 5. BNB Tables

`bnb`, `bnbplanned`, `bnbfuture` tables exist for STR data. Should those be part of the same archiving strategy?

- **Yes**: archive everything together per year — one Parquet per table per tenant per year
- **No**: keep it strictly `mutaties` for now, add BNB archiving later
- **Partial**: archive `bnb` (realized bookings) but not planned/future

### 6. Reporting Performance — Full Parquet vs Summary Table

Right now reports query `vw_mutaties` via SQL. With Parquet archives, the reporting code needs to merge DataFrames in Python. This changes every reporting endpoint.

Alternative: keep a lightweight `archive_summary` MySQL table with pre-aggregated totals:

| tenant | year | account | parent | vw  | aangifte | total_amount |
| ------ | ---- | ------- | ------ | --- | -------- | ------------ |

This would allow:

- Dashboard/P&L queries to stay in pure SQL (fast, no code changes)
- Only drill-down into specific transactions reads from Parquet
- Summary table is tiny (~200 rows per tenant per year)

Trade-off: two sources of truth (summary + Parquet), but summary is derived and can be rebuilt from Parquet.

### 7. Archive Metadata

Should we track archive operations in a MySQL table?

```
archive_log:
  id, tenant, year, action (archive/restore/purge),
  record_count, file_path, created_by, created_at
```

This gives the frontend a quick way to show archive status per year without scanning S3/filesystem.

---

## Reconsidering Parquet — Is It the Right Fit?

### The Scale Problem

Parquet's strengths are columnar compression and predicate pushdown on large datasets (millions of rows). Current data volumes:

- GoodwinSolutions: ~11K transactions/year
- PeterPrive: ~38K total (all years)
- InterimManagement: ~3K total
- Total across all tenants: ~52K

Per-tenant-per-year Parquet files would have ~500-2000 rows each (after debet/credit doubling in vw_mutaties). At that scale:

- Columnar compression barely matters — Parquet metadata overhead (footer, row group info, column chunk headers) can exceed the actual data savings
- Predicate pushdown is irrelevant — pandas reads the whole file into memory anyway at this size
- Row group statistics (min/max per column for skipping) are useless when the entire file fits in one row group

### Alternative Approaches

#### Option A: Single Parquet per tenant (all years combined)

Bigger file, better compression, actual columnar benefits. Partition by year column internally.

- Pro: leverages Parquet properly
- Con: "purge year X" means rewriting the whole file

#### Option B: SQLite file per tenant

Gives SQL queries on archived data, supports indexes, single file per tenant. Restore is trivial (SELECT and INSERT back). Python has built-in support.

- Pro: SQL queries on archived data, no new dependencies, simple file management
- Con: not columnar, but at this scale that doesn't matter

#### Option C: DuckDB file per tenant

Like SQLite but columnar. Best of both worlds: SQL queries + columnar efficiency.

- Pro: SQL + columnar, fast analytical queries
- Con: adds a dependency (duckdb pip package)

#### Option D: Plain CSV/gzip per tenant per year

Simplest possible. pandas reads it natively, tiny files, human-readable.

- Pro: zero complexity, anyone can inspect the files
- Con: no schema enforcement, no indexes, no SQL

#### Option E: MySQL archive table (original approach)

A second MySQL table (`mutaties_archive`) with the same schema as `mutaties`. Views use UNION ALL to combine active + archived data transparently.

- Pro: simplest, keeps everything in SQL, no reporting code changes needed, UNION ALL view handles it transparently
- Con: doubles DB storage for archived data (but at 52K rows that's negligible), archived data stays in MySQL

### Revised Assessment

At current data volumes (~52K total transactions), the MySQL archive table is probably the simplest and most practical approach:

- No new dependencies or storage systems
- Reporting views stay pure SQL (UNION ALL)
- No changes needed in reporting endpoints
- Restore is just moving rows between tables
- Purge is a DELETE statement
- Multi-tenant isolation works the same way (administration column)

Parquet/S3 becomes worthwhile if:

- Transaction volume grows to 100K+ per year per tenant
- Multiple tenants with large datasets
- Need for long-term cold storage with minimal cost
- Want to offload historical data from the database entirely

### Decision Needed

Which approach to go with:

- **MySQL archive table** — simplest, no code changes in reporting, good enough for current scale
- **Parquet (single file per tenant)** — future-proof, offloads DB, but requires reporting code changes
- **Hybrid** — MySQL archive table now, with an export-to-Parquet option for long-term cold storage later
