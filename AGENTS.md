# Kassensturz development agreement

These are standing user requirements for future work.

## Server, Local and Android

- Track every requested feature and relevant bug fix on `server`, `local` and
  `android-standalone`. Keep shared web changes synchronized into local. Explicitly
  server-only features do not add a network server to Android. Keep behavior and financial calculations consistent while
  using each platform's own storage, authentication and interface.
- Track completion separately for both branches. Report any platform-specific
  limitation or blocker explicitly; do not silently leave one implementation out.
- Keep the server deployment and standalone Android app independent. Port changes
  deliberately instead of merging all platform-specific files between branches.
- `android-standalone` is a native Android project at the repository root
  (`app/`, `gradlew`, `settings.gradle.kts`). Keep server runtime, Docker, web UI,
  server tests and server migration/export tools only on `server`. The server-to-
  Android exporter lives at `tools/export_android.py` on `server`.
- Repository/documentation-only restructuring keeps the existing release version
  and Android versionCode; it does not publish a new app-code release.

## Request tracking

- Create a GitHub issue summarizing each new development request before implementation.
- Link the implementing commits and release version, record checks/limitations,
  and close the request issue when the source work is delivered.
- Keep Android physical-device testing issues separate and open for the user to
  complete manually; closing an implementation issue does not certify testing.

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

## Shared release numbering

- The root `VERSION` file is the human-readable release number for server, local and Android. Keep its contents identical on all three branches.
- Android `versionName` reads this file; the server reads the packaged copy for
  its session metadata and visible version. Do not hardcode another UI version.
- Android `versionCode` is a separate, monotonically increasing installation
  counter. It is not a different public release name. Increase it for a new
  installable Android update; metadata-only changes do not rename old APKs.
- Name testing issues with the shared version and identify the exact APK build
  commit separately. Preserve any previous tester results when updating issues.
- Version alignment does not authorize a build, pipeline, deployment or charge.

- Assign a new shared version for every feature or fix: minor for new features
  (0.1.0 → 0.2.0), patch for fixes (0.2.0 → 0.2.1), major for breaking changes.
  Update VERSION on all three branches and the version-specific Android testing issue.
