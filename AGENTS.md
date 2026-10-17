# Kassensturz development agreement

These are standing user requirements for future work.

## Both applications

- Implement every requested feature and relevant bug fix on both `server` and
  `android-standalone`. Keep behavior and financial calculations consistent while
  using each platform's own storage, authentication and interface.
- Track completion separately for both branches. Report any platform-specific
  limitation or blocker explicitly; do not silently leave one implementation out.
- Keep the server deployment and standalone Android app independent. Port changes
  deliberately instead of merging all platform-specific files between branches.

## Cost approval and testing

- Obtain explicit user approval before starting any action that could incur
  additional charges: GitHub Actions, hosted builds, emulators, paid services,
  deployments or other metered jobs. Included/free allowances are not approval.
- Approval applies only to the specific action/scope approved. A feature request,
  permission to commit or push, or approval of a previous build does not authorize
  a new potentially billable run or retry.
- Build/test workflows must remain manual-only (`workflow_dispatch`). Do not add
  push, pull-request, issue, schedule or workflow-run triggers without explicit
  approval. Before pushing, inspect all workflows in the resulting commit and
  check that the push will not trigger a potentially billable job.
- Do not dispatch a manual workflow without explicit cost approval either.
- The user can run server tests. Android acceptance testing is on a physical
  device; do not start an emulator unless explicitly requested and cost-approved.
- Read-only inspection and non-metered local file/configuration checks can proceed.
  Describe checks accurately; never report unexecuted tests as passing.

## Android testing issue for every published app version

- After publishing an Android app-code version, create a GitHub testing issue
  directly through the connected GitHub API. This uses no Actions runner. This is
  the assistant's publishing responsibility, not a push-triggered automation.
- Search for an existing issue for the same app/build commit first. Reuse it for
  build retries; do not duplicate it. Documentation-only or process-only pushes
  do not constitute a new app version.
- Use `.github/ISSUE_TEMPLATE/android-testing.md` as the structure. Include the
  versionName/versionCode, exact app commit, branch, APK/build link when available,
  changes, targeted acceptance steps and essential regression checks.
- If an APK build has not been approved or is not yet available, create the issue
  with APK/build status pending. Update that issue after an approved build.
- Leave all manual checks unchecked. Include fields for tester, device, Android
  version, results and discovered bugs. Never put private financial data in it.
- The user manually completes/closes the issue after a person has tested the app.
  Do not auto-close issues, mark manual checks passed, or treat an APK build as
  physical-device acceptance. Reference issues without auto-closing keywords.
- In the delivery message link both branch commits and the Android testing issue;
  state which checks ran and which still need the user's testing/approval.
