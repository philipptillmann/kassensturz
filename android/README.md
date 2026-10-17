# Kassensturz for Android

[Installationsanleitung auf Deutsch](INSTALL.md)

Branch: `android-standalone`. Native Kotlin Android app, Android 9 (API 28) or
newer. It runs without Docker, a server, an account or an internet connection.
The server application continues separately on branch `server`.

## Current app

- German native interface, monthly overview and twelve-month/category charts.
- Local SQLite transactions: expense, reimbursement/contribution and income,
  categories, payment methods, notes, editing and deletion.
- Category renaming also updates saved entries and receipt positions.
- Private and demo databases are separate. Demo includes twelve months of data;
  deleted demo entries do not reappear on restart.
- Split receipt positions can inherit a transaction group, have their own group,
  or explicitly stay outside groups. Position totals must equal the transaction.
- Effective costs combine group contributions in each transaction's own month.
  Income is reported separately. Shared-account percentages preserve cent totals
  and can optionally apply to incoming amounts.
- Internal account transfers: conservative automatic matching when there is
  unique amount/date/account evidence plus an IBAN or transfer-text hint;
  ambiguous matches require confirmation. Confirmed legs disappear in effective
  mode, even across months. A removed match stays ignored until reconsidered.
- Bank CSV import: comma/semicolon/tab, quoted text, German or ISO dates,
  German decimal amounts, UTF-8/Windows-1252, column mapping and preview.
  Deduplication includes the selected account and repeated identical rows.
  Incoming bank amounts default to reimbursements; classify salary etc. as income
  explicitly or enable the income option for that import.
- Original receipt content is kept as JPEG (longest edge at most 3200 px,
  quality 85, alpha flattened on white). Android ImageDecoder handles rotation
  and HEIF/HEIC on supported devices. Camera and document-picker imports work
  without broad photo-library/storage permissions. Originals are replaced by
  the compressed JPEG, not also retained as a second file.
- Bundled ML Kit Latin text recognition works offline. OCR text can be reviewed
  and added to notes; a detected total is optional. OCR does not automatically
  create item lines, assign categories or infer all receipt fields in this version.
- Full ZIP backup/restore includes entries, splits, settings, groups, transfer
  links, ignored pairs and JPEG receipts. Restore is validated in a database
  transaction; a failed restore leaves the old dataset intact. CSV export is a
  spreadsheet export, not a complete backup and not a lossless re-import format.

No Internet permission is granted to the application. No server login or
multi-user sharing is implemented in this local, single-owner version. Android
cloud backup and device transfer are excluded; use explicit in-app backups.

## Build and install

Install JDK 17 and Android SDK platform/build tools 35. Set `ANDROID_HOME` or
create ignored `local.properties` with `sdk.dir=/path/to/Android/Sdk`.

```sh
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`. Transfer to the phone and open
it, allowing installation from that source when Android asks. This is a debug
build for testing. A permanent release signing key and store distribution have
not been configured. Builds signed with different keys cannot update one another;
back up before uninstalling a test build. Keep signing keys outside Git.

GitHub Actions **Android standalone** is manual-only. Request explicit cost
approval before running it; pushes do not start a build. Download
`kassensturz-android-debug` from the completed run's Artifacts section and unzip
it to get `app-debug.apk`. CI runs unit tests, lint and the APK build; device
testing is done on a physical Android phone. Follow the checklist in
[INSTALL.md](INSTALL.md#auf-dem-telefon-testen). Camera behavior and HEIC
readability should be checked on that phone.

## Backups

Under **Mehr**, choose **Vollständige Sicherung erstellen**, select a destination,
and keep the ZIP outside the app. Restore replaces only the currently selected
private/demo dataset after confirmation. The archive contains private data and
is not encrypted. Uninstalling the app removes its local databases and receipts.

Format v1 bounds: 50,000 entries, 2,000 categories/payment methods each, 16 MB
metadata, 4 MB per compressed JPEG, 512 MB receipt data per dataset. Oversized
exports fail explicitly; imports use the same limits. Image input is limited to
24 MB; bank CSV input to 8 MB. ZIP entries are read in memory-bounded chunks,
never extracted to caller-controlled filesystem paths.

## Move one existing server account to Android

`export_server.py` uses only Python's standard library. Run it as the server
operator against the data directory, or against a complete restored backup.
It opens source databases read-only, captures a consistent SQLite snapshot,
selects exactly one account and writes no sessions or password hashes.

```sh
python3 android/export_server.py --data-dir /path/to/kassensturz-data \
  --username YOUR_USERNAME --output /private/path/kassensturz-phone.zip
```

For a server that has never migrated to named accounts, use `--legacy` instead
of `--username`. `--dataset demo` explicitly exports that account's demo data;
private is the default. Existing output files are never overwritten.

The data directory must include `expenses.sqlite3` and, for additional users,
the `users/` directory with its original structure. If using a copy, use a
consistent server backup instead of copying SQLite files while writes are active.
The script can also be copied to the server and run independently; switching
your server's Git branch or deploying the Android branch is unnecessary.

Move the resulting ZIP to the phone, select **Privat → Mehr → Sicherung
wiederherstellen**, and compare transaction counts, balances, split groups and
receipts before relying on the import. Keep your original server data. This is
a one-time copy, not synchronization. Server-specific CSV deduplication hashes
are preserved but differ from newly generated Android import keys; avoid
re-importing overlapping server bank statements without checking duplicates.

## Verification

```sh
# Repository root, with the existing Python dependencies installed:
python -m unittest discover -s android/tests -v
# Optional instrumented checks: Android project, physical device connected with USB debugging:
./gradlew connectedDebugAndroidTest
```

Unit tests cover money parsing, groups, month boundaries, partial grouping,
rounding, shared accounts, CSV parsing and conservative transfer matching.
Instrumented tests cover real SQLite CRUD, rename, persistence, dataset isolation,
receipt backup/restore, rollback, CSV deduplication and transfer consistency.

## Feature delivery and acceptance

Feature requests are implemented on both `server` and `android-standalone`.
For every Android app version the publishing assistant creates a GitHub testing
issue through the GitHub API, including the exact build commit and a checklist
tailored to the changes. Build retries reuse the issue; documentation-only pushes
do not create new version issues. If a build is not approved, its APK link remains
pending. The user completes/closes the issue after physical-device testing.
This process does not use an Actions job or automatically mark tests as passed.

## Shared release version

The current Docker/server and Android release name is **0.1.1**. Both branches
carry the same root `VERSION` file. Android Gradle reads it for `versionName`;
the installed app displays its package version. `versionCode` is Android's
internal upgrade counter and remains separate. The 0.1.1 source uses versionCode 2. Its APK build is pending explicit cost
approval; the previously published APK remains 0.1.0.

### 0.1.1 — reimbursement entry on mobile keyboards

The web editor offers a +/− button beside totals and split-item amounts. Android
uses Art → Erstattung / Beitrag with a positive total; split-item amounts now
also have a +/− button. No minus key is needed. Existing signed transactions,
groups and income accounting retain their meaning.
