# Kassensturz user manual

Version 1.2.0 · English

## Getting started

Kassensturz records expenses, refunds and income in EUR. Server runs in your browser, including as an iPhone home-screen app. Local runs on your computer. Android stores its own data on the device and works independently. These installations do not synchronize automatically.

On a shared server, sign in with your own account. When migrating the original shared-password installation, the first named account takes ownership of the existing private data and becomes administrator. Other users have separate data. Administrators can create accounts in Settings. Remembered login sessions reduce repeated sign-ins; changing a password invalidates existing Shortcut keys.

Use the dataset selector to switch between Private and Demo. Demo data is for trying features; it is separate from your private records. Always check the selected dataset before importing or restoring anything.

## Language and help

In Settings, choose Deutsch or English. Android offers a language switch in its settings. The choice is saved in this browser or Android installation, rather than applied to every device. Open User manual there to read this guide; Android includes it offline.

Language changes affect interface text and display formatting. They do not rename saved categories, payment methods, merchants, notes or imported bank descriptions. Those remain editable user data. Amounts remain EUR; changing language does not convert currencies. Bank CSV headers and API field names remain unchanged.

## Adding and editing entries

Choose New entry, or the cash shortcut on the overview to preselect the cash payment method. Enter a date, merchant or description, amount, category and payment method. Add optional notes for details you want to remember. Select an entry to edit or delete it.

An expense increases costs. A refund or another person's contribution reduces them: use a negative expense amount on the web, with the +/− button where needed. Android provides a refund/contribution entry type with a positive amount field. Use the Income type for salary, gifts and other income. Income is shown separately from spending; do not use it for refunds of a purchase.

In Settings you can add categories and rename them. Renaming updates existing entries and receipt items using that category. Payment methods can be cash, a bank account, or PayPal/other. Choose a clear name for each account. Bank settings include an optional IBAN and your percentage share; choose whether the share also applies to incoming amounts. Shares affect effective reports, not the recorded bank transaction. Review historic entries when changing these settings.

## Groups, split receipts and effective costs

Give a purchase and its related reimbursements the same group name. All entries remain individually visible. Switch the monthly view between all entries and effective costs to see the group's net cost. Each entry counts in its own month, even if a friend pays later. A group's purchase category is used for effective reporting.

Split a receipt into items when only part of a purchase belongs to a group. Each item can inherit the entry's group, have its own group, or have no group. Check that the item amounts add up to the receipt total. Use item categories for mixed purchases.

For a refund/contribution, you can record the agreed contribution separately from the amount actually received. For a €60 purchase, an agreed €30 contribution but an actual €35 payment reduces your effective cost to €25. The entry also shows the €5 overpayment and the agreed share. It does not silently replace the actual payment or create a debt or repayment. Add a note explaining the mistake. Receipt recognition suggestions must be checked: a receipt is not proof of how much money actually arrived.

Internal transfers between your own bank accounts have two corresponding entries. Matching uses account information, dates and amounts conservatively. Review suggested matches and confirm or assign them manually if necessary. Confirmed transfers disappear in effective mode, including across months, while their original entries remain available. A shared account's percentage share is applied in effective mode; for an equal shared account set 50%.

## Receipts

Scan or upload an image and review the extracted merchant, date, total and items before saving. OCR can make mistakes. The saved receipt image is converted to a compressed JPEG intended to remain readable; it is not a byte-for-byte copy of the original upload. Server supports HEIC conversion. Android HEIC support depends on the device's image decoder. Keep the original separately if you need original-file fidelity.

A saved receipt remains attached to the entry and is included in a full ZIP backup. Verify the picture after saving. Deleting an entry or replacing its picture removes the associated stored image as appropriate. CSV exports do not contain receipt pictures.

## Bank CSV import and undo

In Settings, choose a CSV and the payment method/account for this import. Review the recognized format, date, description and amount columns, sign convention, counterparty IBAN column and preview. Bank-format negative debits become expenses; credits become incoming amounts. Only EUR is supported. Common UTF-8 and Windows-1252 files are supported.

Trade Republic supports everyday card payments and transfers. Investment-related rows, including BUY, INTEREST_PAYMENT, DIVIDEND and BENEFITS_SAVEBACK, are currently excluded and listed in the import result. ING supports its statement preamble and booking/value-date layout; choose the transaction amount, not the running balance. Volksbank files may contain several source accounts: select the intended source account and import other accounts separately. Counterparty account information helps transfer recognition.

Check excluded rows, imported count and duplicate warnings. Duplicate recognition is scoped to the selected account and uses source identities or occurrence-aware matching. Importing the same history through a different generic mapping can have different identities; inspect the preview rather than assuming all previous imports will match.

Use Undo last CSV import to remove entries created by the most recent successful import in the current dataset. Skipped duplicates and failed imports do not replace that undo record. Later edits and receipt attachments on the removed entries are also lost. Older imports made before undo tracking cannot be undone this way. Entries linked to wealth operations must be unlinked before undo. There is no automatic redo; keep the original CSV and make a backup first when unsure.

## Reports

The overview and charts show monthly totals, trends and category breakdowns. Choose the month and all-entry or effective mode. Income remains separate. Effective mode combines grouped purchases and refunds, applies account shares and omits confirmed internal transfers. Wealth-linked bank entries are omitted from spending reports to avoid counting the same operation twice. For reconciliation, inspect the underlying entries as well as the charts.

## Wealth

Create products for cash, brokerage, building savings, fixed-term deposits, savings and other holdings. Record dated balance snapshots: bank balances are not inferred from the expense list. Record transfers between products separately from income and expenses.

For brokerage holdings, enter purchases and sales, units and prices. Purchases require sufficient product cash. Record actual interest, dividends and fees as their own operations. Recurring instructions provide a preview of due dates; confirm before booking. Month-end dates are adjusted, and already processed occurrences are not booked twice. A batch that cannot be funded is rejected instead of partially applied.

Link an imported bank transaction to the matching wealth operation to avoid duplication. Such links remove that bank entry from spending reports in both modes. Review and unlink before deleting or undoing an import containing linked entries.

Optional market quote retrieval requires an explicit request, a user-supplied free API key and confirmation of EUR prices. It does not fetch automatically. Errors leave existing values intact. Forecasts are scenarios based on entered balances, rates and instructions; they do not guarantee returns or automatically model every tax, fee or inflation effect.

## Backups and moving data

Use Full ZIP backup for the selected dataset. It includes entries, settings, receipt images and supported wealth data; it does not include server passwords, other users or every installation preference. Ordinary CSV export is a transaction table, not a complete backup.

Keep private backups outside GitHub. Portable ZIP files contain unencrypted financial data even if the server database is encrypted. Store them securely and keep separate copies. Restore validates the archive and replaces the selected dataset after confirmation, including its existing receipts and undo history. Check the dataset first.

Backup formats 1 and 2 cover older data; format 3 is required when agreed contributions are present. Older app versions may reject newer formats. Update the destination before restoring, and keep a backup before testing transfers between installations. Android and server are independent; server import-history metadata is not preserved through every Android backup round trip.

## iPhone Shortcuts API — server only

In Settings, create a Shortcut key for your account and a fixed dataset. Copy it immediately; the full key is shown once. Keep it secret. Use HTTPS and send it as an Authorization: Bearer header. Revoking the key or changing your password disables it.

Query /json-options for the current categories, banks and payment methods. Send new entries to /json-import with date, merchant and amount, plus the relevant optional category, payment_method, kind, group_name, notes or expected_contribution fields. Follow the live API documentation for exact field values and amount conventions. Use a stable request identifier for safe retries, and distinct identifiers for genuinely separate identical purchases. Keys cannot read your full transaction history or edit existing entries.

## Server security and troubleshooting

Server uses HTTPS by default. For a private LAN certificate, devices must trust the local certificate authority. Local's loopback-only development launcher is a separate setup. Keep your chosen port and deployment secrets in the local environment configuration, outside Git.

Optional database encryption is off by default and requires the documented SQLCipher setup and a safely backed-up encryption key. Losing that key can make the data unrecoverable. Enabling database encryption does not encrypt portable exports or automatically remove old plaintext copies. Consult the server security and installation guides before migrating. Android relies on its app storage and device security; this is not a promise of an extra encrypted database.

If an import or restore looks wrong, stop and export a backup before making further changes. Check the dataset, account, date range, sign convention and effective-mode setting. For OCR errors, correct the entry before saving. If login or HTTPS fails, check the hostname, port and certificate trust. When reporting bugs, use synthetic examples and omit receipts, account numbers, private server addresses and API keys. Android acceptance testing is on a real device; no automatic cloud build is required to use the server.
