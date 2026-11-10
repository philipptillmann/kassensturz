# Interface languages

Settings switches German/English per installation using the `language`
SharedPreferences. MainActivity recreates with the selected resource locale; EUR
remains explicit. `L10n.kt` loads `app/src/main/assets/locales/en.json`.
Translate developer-owned literal segments before concatenating user values.
Never translate stored names/notes, CSV headers, API/model identifiers or seed
data. Keep the catalog and bilingual manuals aligned with the web branches.

User manuals are in `docs/USER_MANUAL_EN.md` and `docs/USER_MANUAL_DE.md`, with
standalone escaped HTML in `app/src/main/assets/manual/`. The native help view
loads these offline, with JavaScript and network loads disabled. Update both
Markdown and offline HTML when documenting new features.

`LanguageTest` covers saved language, locale, catalog and offline assets. Running
it needs an approved build/device test; no build or physical-device acceptance
is implied by adding the test source.
