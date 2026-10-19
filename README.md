# Kassensturz for Android

[Installationsanleitung auf Deutsch](INSTALL.md)

Branch: `android-standalone`. Native Kotlin Android app, Android 9 (API 28) or
newer. It runs without Docker, a server, an account or an internet connection.
The server application continues separately on branch `server`.

## Repository layout

Open this repository's root directly in Android Studio. No `android/` subfolder
is needed. `app/` contains the native source, resources and tests; `gradle/`,
`gradlew`, `build.gradle.kts` and `settings.gradle.kts` configure the build.
`VERSION` is the shared release name, and [INSTALL.md](INSTALL.md) explains phone
installation. Only the manual Android workflow is included in this branch.
Docker, Python server code, the web UI, server tests and migration/export tools
are maintained on `server`.

For an existing developer checkout, remove the `android/` prefix from local build
commands and APK paths. Put `local.properties` in the repository root, or keep
using `ANDROID_HOME`. The source move leaves the application ID, database names,
backup format and signing configuration unchanged; it does not migrate or delete
installed app data. The repository reorganization retains version 0.3.0/code 4.

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
# Run from the repository root (or open it directly in Android Studio).
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

The export utility belongs to the separate `server` branch at
[`tools/export_android.py`](https://github.com/philipptillmann/kassensturz/blob/server/tools/export_android.py).
Follow the [server export instructions](https://github.com/philipptillmann/kassensturz/blob/server/README.md#export-one-account-to-android)
to export exactly one account, read-only, without password hashes or sessions.
It uses only Python's standard library and can run independently on the server;
do not switch a running server installation to the Android branch.

Move the resulting ZIP to the phone, select **Privat → Mehr → Sicherung
wiederherstellen**, and compare transaction counts, balances, split groups and
receipts before relying on the import. Keep your original server data. This is
a one-time copy, not synchronization. Server-specific CSV deduplication hashes
are preserved but differ from newly generated Android import keys; avoid
re-importing overlapping server bank statements without checking duplicates.

## Verification

```sh
# Repository root, only after approval for any potentially metered run:
./gradlew testDebugUnitTest lintDebug
# Optional instrumented checks: physical device connected with USB debugging:
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

The current Docker/server and Android release name is **0.6.0**. Both branches
carry the same root `VERSION` file. Android Gradle reads it for `versionName`;
the installed app displays its package version. `versionCode` is Android's
internal upgrade counter and remains separate. The 0.6.0 source uses versionCode 8. Its APK build is pending explicit cost
approval; the previously published APK remains 0.1.0.

### 0.1.1 — reimbursement entry on mobile keyboards

The web editor offers a +/− button beside totals and split-item amounts. Android
uses Art → Erstattung / Beitrag with a positive total; split-item amounts now
also have a +/− button. No minus key is needed. Existing signed transactions,
groups and income accounting retain their meaning.

### 0.2.0 — cash expense shortcut

On Übersicht, the coin-button **Barausgabe** opens a new expense with **Bar**
preselected. Enter the amount and description, then save. The selected private/
demo dataset is retained; opening or cancelling the editor does not create an
entry. Normal new entries and edits keep their usual payment selection.
The corresponding server/iPhone overview has the same shortcut.

### 0.3.0 — Ausgehen category

**Ausgehen** covers drinks at bars/clubs and meals at restaurants. It is added
to new databases and to existing private/demo databases during upgrade. Existing
entries retain their categories; the user can reclassify them manually.
Legacy backups receive the new default during restore. New backups mark the
default-category migration so a renamed Ausgehen category stays renamed on
restore. Server exports retain the same migration marker when the source
database already knows this default, including a renamed category alias.


### 0.3.1 — date field fits the editor

The server/iPhone form bounds date and month controls to their available width,
including native Safari rendering, so they cannot stretch the editor sideways.
The native Android date field already uses the dialog width; it is now explicitly
single-line with date input. Dates, stored records and backups are unchanged.
The APK build and physical-device acceptance remain pending.


### CSV duplicate preview (0.4.0)

Before committing a CSV import, the app reports new and already imported entries
for the selected account and dataset. Cancelling changes nothing; saving rechecks
against the latest data. Identical genuine purchases within one statement keep
their occurrence counts. Other accounts remain independent. Matching uses the
existing date/description/amount/account import identity, not fuzzy guesses:
changed bank descriptions or overlapping partial exports without stable bank IDs
can remain ambiguous. Manually entered lookalikes are not automatically removed.


### File backup and restore (0.5.0)

Under **Mehr**, create a full ZIP for the selected private/demo dataset or choose
**Sicherung wiederherstellen**. Before confirming replacement, the app now shows
entry and receipt counts plus the source dataset/time when available. New ZIPs
record that metadata; older ZIPs remain supported. Cancelling the preview leaves
local data unchanged. The complete archive is validated during transactional
restore; invalid data rolls back without replacing the existing dataset.

Backups include entries, splits, categories, payment/account settings, groups,
transfer decisions, import identities and JPEG receipts. Keep private ZIPs outside
Git and back up the current dataset before replacement. CSV is not a full backup.
The existing limits and installation instructions above still apply.

The server now provides matching financial ZIP export/restore on its separate
branch. For server-side operation and limits, see the
[server instructions](https://github.com/philipptillmann/kassensturz/blob/server/README.md#file-backup-and-restore-050).
The common portable format supports a one-time data copy, not synchronization;
server-specific category aliases cannot be reconstructed from an Android-only
backup that has never stored them.


### Server-only iPhone Shortcut API (0.11.0)

The separate server accepts direct Kassensturz entry fields at **POST /json-import**:
`date`, `merchant`, `amount`, with optional `kind`, category, payment method, notes,
groups and split items. See the [server Shortcut guide](https://github.com/philipptillmann/kassensturz/blob/server/docs/SHORTCUT_API.md).
The standalone Android app retains local storage and has no HTTP server or API keys.
Its runtime is unchanged; VERSION/versionCode align to 0.11.0/13 for future builds.
Android backup round trips preserve common financial entries and import keys, but
not server-only Shortcut sources or deleted-request history. No APK was built.

### Trade Republic CSV (0.7.0)

Semicolon exports with `datetime;date;account_type;category;type;…;transaction_id`
are detected automatically. Select the actual Trade Republic payment account.
Booking `date` and signed EUR `amount` are used; original-currency fields are not
converted again. Supported cash types: CARD_TRANSACTION, TRANSFER_INSTANT_OUTBOUND,
TRANSFER_INSTANT_INBOUND, TRANSFER_OUTBOUND, TRANSFER_INBOUND. Card credits remain
refunds; transfers remain uncategorized expenses/refunds until classified or matched
as internal transfers. Investment, Saveback, interest, tax and unknown types are
explicitly excluded in the preview, rather than guessed from incomplete semantics.
Review exclusions before importing. Interest/tax support and other bank formats
remain follow-up work under #7.

Repeat detection uses provider, selected account, account_type and transaction_id.
Keep the same payment account name on repeat imports. Older generic CSV imports
have different keys: do not reimport their date ranges without checking/removing
existing entries. No fuzzy deduplication against manually entered records occurs.
The supplied personal CSV is not included in the repository.

### Undo CSV import (0.8.0)

Under Import / Settings, choose **Letzten CSV-Import rückgängig machen**.
The confirmation shows the latest import time and remaining entry count. Undo
removes only entries newly inserted by that import, including subsequent edits,
split items and receipts. Pre-existing duplicates and other entries remain.
A failed or all-duplicate import does not replace the previous undo. Undo survives
restart and is separate per dataset/user; it is one level, with no redo. Reverting
also removes associated transfer links, leaving their other entries intact.
Only imports made from this release onward can be undone. Restoring a full backup
clears undo history; undo history is not exported in backups.

### ING CSV (0.9.0)

The supplied ING Umsatzanzeige layout is recognized by its exact 10-column
booking header, with or without an account-information preamble (not imported).
Select the actual ING payment account. Booking date (not value date), signed EUR
amount and counterparty name are mapped automatically; booking text, purpose and
reference are retained as notes. Balance is never treated as a transaction. Both
currency columns must be EUR. Explicit positive Gehalt/Rente credits are income;
other credits remain refunds until manually classified. Zero amounts are listed
as exclusions. Invalid dates, amounts, currency or row widths abort the import.

This variant has no unique transaction ID. Repeat detection uses the account,
booking/value dates, name, type, purpose, reference, signed amount and occurrence
number. Balance and preamble changes do not affect matching. Identical repeated
rows are retained, but partial exports containing only some indistinguishable
transactions cannot be resolved uniquely: review the duplicate preview. Existing
generic CSV imports use different keys; review overlapping date ranges manually.
The last-import undo also applies to ING. Only synthetic fixtures are committed.

### Volksbank CSV (0.10.0)

The supplied 18-column semicolon format is detected automatically. Choose the
source IBAN from the file and the matching payment account in Kassensturz. Each
import covers one source account; other source accounts are explicitly excluded
in preview. Import them separately into their own payment accounts. Booking day
and signed EUR amount are mapped; value date and balance do not replace these.
Counterparty IBAN is retained for transfer reconciliation. Booking text, purpose,
remark, creditor ID and mandate reference are saved as notes. Credits remain
refunds until manually classified as income; the sample has no salary marker.

No unique booking ID is supplied. Deduplication includes source IBAN, selected
payment account, booking/value dates, party/IBAN, booking text/purpose, creditor ID,
mandate, signed cents and occurrence number. Balance/flags/remarks do not change
identity. Indistinguishable partial exports need manual review; older generic CSV
imports use different keys. Preview and last-import undo apply normally. EUR only;
invalid selected-account rows abort atomically, zeros are explicitly excluded.
Only synthetic fixtures are committed; the supplied CSV is kept out of GitHub.
