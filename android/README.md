# Kassensturz for Android

Development branch: `android-standalone`, based on server commit
`120ccba5d10927f6fc66cefb6f79bc3227363813`.

## Goal

An installable Android application that works without Docker, a server, or an
internet connection. The existing server application remains on branch `server`.
This branch currently contains the server source and this development plan;
there is no Android application or APK yet.

## Proposed implementation

- Kotlin with Jetpack Compose for the German interface.
- Room over SQLite for transactions, split items, categories, payment methods,
  expense groups, account shares, transfer matches and dataset metadata.
- App-private files for compressed JPEG receipts, with database references and
  transactional cleanup. OCR must run on device with bundled recognition models
  so first-use scanning also works offline.
- Android photo picker / camera integration; verify HEIC decoding on supported
  Android versions, normalize orientation, and check compression readability.
- Private and synthetic demo datasets stored separately.
- No server login dependency. Android device security protects the initial
  single-owner installation. Multiple local profiles or a separate app lock
  require a deliberate design; server account passwords must not be copied.
- Explicit user-controlled export, backup and restore through Android's document
  picker. Full backups must include receipts, schema version and all local data;
  CSV alone is not a complete backup. Decide and configure Android automatic
  backup behavior before distributing builds with real data.

## Delivery milestones

1. Buildable Android project and installable debug APK: local database,
   transaction create/edit/delete, categories, payment methods, separate
   income/expenses, notes, monthly totals and demo/private selection.
2. Port and test split receipts, expense groups, effective costs, shared-account
   percentages, transfer matching and charts against the existing synthetic
   Python/JavaScript fixtures. Keep cents as integers and preserve rounding and
   cross-month rules.
3. Local receipt capture, JPEG conversion/storage and bundled offline OCR.
4. Bank CSV import with account-scoped deduplication, full backup/restore and
   migration from a selected server account.
5. Device testing, stable package identifier and release signing, then a
   release APK. Signing secrets stay outside Git.

## Existing data migration

Do not copy a complete multi-user server database into the phone: the root
SQLite database also contains authentication data. Implement an authenticated
export restricted to the selected account, including its private data, settings,
splits, receipt images and schema metadata. Exclude other accounts, sessions and
password hashes. Validate the archive and import atomically into a new local
dataset, preserving IDs/links and comparing counts, totals and receipt checksums.
Retain the server data until the user verifies the import. No migration code
exists yet.

## Acceptance criteria

- Installation and everyday operation require no server address or Docker.
- Airplane-mode tests cover entering/editing transactions, charts and receipt OCR.
- Effective totals match the existing grouping, refund, income, transfer and
  shared-account tests, including month boundaries.
- Full backup/restore reproduces totals, settings, links and readable receipts.
- The server deployment workflow and branch remain independent.
