# Interface languages

The interface supports German (default) and English. Web Settings and the login
page save `kassensturz-language` in localStorage. A non-secret SameSite cookie
selects server validation-message language. Android uses its own `language`
SharedPreferences and recreates the activity with the selected resource locale.
The choice is per browser or installation, not an account setting or backup item.
EUR is explicit in both locales; changing locale must never change the currency.

`static/locales/en.json` maps developer-owned German source strings to English.
Android includes the same catalog at `app/src/main/assets/locales/en.json` on its
branch. Keep catalogs and user manuals aligned when adding features.

Use `I18n.t('developer text')` for static JavaScript UI text and `I18n.tpl` tagged
templates for interpolated messages/HTML. Only literal template parts are
translated; interpolated user values are left untouched. Initial HTML is
translated once, before application scripts render any saved data. Never run a
translation pass over rendered transaction/category/payment/asset content.

Native Kotlin likewise translates literal segments with `L10n.t(...)` before
concatenating user values. Do not translate editable names, notes, CSV header
identities, database values, API keys or model discriminators. Wealth product
labels are translated while product identifiers remain stable. Server errors
translate exact known messages or known prefixes ending in a colon, preserving
any user-supplied suffix. Unknown messages fall back to German.

User manuals live in `docs/USER_MANUAL_EN.md` and `docs/USER_MANUAL_DE.md`, with
standalone HTML copies in `static/manual/` and Android `assets/manual/`. HTML
contains only escaped headings and paragraphs, inline layout CSS and no scripts
or external dependencies. When changing manuals, update those offline copies too.

Checks: `node tests/test_i18n.cjs`, Python `test_localization.py`, and optional
`python tests/browser_language.py` with Playwright and Chromium. Browser checks
use disposable local data. Native `LanguageTest` needs an approved device build
and is not a substitute for the release's manual physical-device testing issue.
