---
name: Android version testing
about: Manual physical-device acceptance for one published Android app version
title: '[Android testing] <version> · <app commit>'
---

## Build

- Version / versionCode:
- Branch: `android-standalone`
- Exact app/build commit:
- APK download:
- Build/cost approval status:
- Installation guide: [INSTALL.md](https://github.com/philipptillmann/kassensturz/blob/android-standalone/INSTALL.md)

## Changes in this version

<!-- Summarize the changes and add a concrete unchecked acceptance step for each. -->

- [ ] Requested behavior verified on a physical device

## Essential regression checks

Use Demo data first; do not include private data in screenshots or reports.

- [ ] Install/update and launch successfully; existing local data is retained
- [ ] Demo and private datasets remain separate
- [ ] Create, edit and delete an expense, reimbursement and income
- [ ] Monthly totals, categories and charts are correct
- [ ] Groups, split positions and effective costs are correct
- [ ] Shared-account percentages and internal transfers are correct
- [ ] Capture/import a receipt, save it, reopen it and check readability
- [ ] On-device OCR works in airplane mode
- [ ] Full backup/restore retains entries, settings and receipt images

## Tester and results

- Tester:
- Device/model:
- Android version:
- Tested app version/commit:
- Installation type (fresh/update):
- Result (not tested/pass/fail): **Not tested**
- Bugs / linked follow-up issues:
- Notes:

Keep this issue open until the user manually completes it after testing.
