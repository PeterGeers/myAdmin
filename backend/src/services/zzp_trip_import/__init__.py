"""zzp_trip_import: cohesive helpers for the ZZP trip CSV/Excel importer.

This sub-package splits the (formerly ~1100-line) ``zzp_trip_import_service``
module into cohesion-named stages while keeping the public import surface at
``services.zzp_trip_import_service`` fully stable:

- ``constants`` — column mappings, required fields, Excel error markers, the
  downloadable-template columns, and the ``_SheetSelectionError`` signal.
- ``parsing`` — the parse stage: extension detection, DataFrame reading /
  sheet selection, Excel error-marker recovery, and row cleaning.
- ``validation`` — the validate stage: per-row checks (required fields, date
  normalization, odometer, category/purpose) plus the cross-row continuity and
  duplicate checks.

``TripImportService`` (in ``zzp_trip_import_service``) owns the DB-bound
orchestration (``parse_file`` / ``validate_import`` / ``commit_import`` /
``get_template_csv`` / preset seeding) and delegates the pure parse and
validation logic to these modules. Behavior is unchanged — this is a pure move.
"""
