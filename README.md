# Ausgabenbuch

Eine lokale Ausgaben-App für macOS mit SQLite, CSV-Bankimport und Apple-Vision-Texterkennung. Keine Cloud, keine externen Webfonts, keine Python-Paketinstallation.

## Start auf dem Mac

Python 3.10 oder neuer erforderlich. `start.command` doppelklicken oder im Projektordner ausführen:

```sh
python3 app.py --open
```

Die App läuft auf Port 8765. Der persönliche Verbindungslink steht im Terminal. Zum Beenden Ctrl+C drücken. Bei belegtem Port `--port 8766` ergänzen. Nach jedem Neustart den neuen Link verwenden.

## Rechnungen vom Handy

```sh
python3 app.py --lan --open
```

Mac und Handy müssen im gleichen privaten WLAN sein. Den im Terminal angezeigten Handy-Link auf dem Handy öffnen. Bei Bedarf den Netzwerkzugriff in der macOS-Firewall erlauben. Unter „Rechnung scannen“ kann die Kamera oder Fotomediathek ausgewählt werden; das Bild wird an den Mac übertragen und dort verarbeitet. Die App verwendet HTTP und sollte daher ausschließlich im vertrauenswürdigen privaten WLAN verwendet werden. Sie ist nicht für eine Freigabe ins Internet ausgelegt. Beim normalen Start bleibt der Server auf den Mac beschränkt.

## Rechnungen und Kategorien

1. Neue Ausgabe anlegen oder eine bestehende Kontobuchung anklicken.
2. Foto auswählen. Apple Vision liest den Text lokal aus; dafür sind funktionierende Xcode Command Line Tools (`xcode-select --install`) erforderlich.
3. Erkannte Positionen, Betrag, Datum und Händler prüfen. Kategorien pro Position auswählen. Positionen können jederzeit manuell erfasst werden.
4. Versand, Rabatte oder weitere fehlende Positionen ergänzen. Positionssumme und Buchungsbetrag müssen exakt übereinstimmen.

OCR erkennt Text und schlägt einfache Zeilen mit abschließenden Preisen vor. Es handelt sich nicht um eine semantische Rechnungserkennung: mehrspaltige Amazon-Rechnungen, Mengen, Steuern und Summenzeilen können Nacharbeit benötigen. Einfache Stichwortregeln schlagen Kategorien vor, etwa „Fahrradlicht“ → Fahrrad und „Kochtopf“ → Küche & Haushalt. Unbekannte Artikel bleiben unkategorisiert; alle Vorschläge sind manuell korrigierbar. Fotos werden nur temporär für OCR verarbeitet und danach gelöscht; es gibt noch kein Belegarchiv und keine PDF-Erkennung. Foto an einer bestehenden Buchung erfassen, um diese aufzuteilen, statt eine zweite Ausgabe anzulegen.

## Bankimport

Unter „Kategorien & Import“ eine CSV auswählen und Datum, Händler/Verwendungszweck sowie Betrag zuordnen. UTF-8 und Windows-1252 werden unterstützt. Bankformat bedeutet: negative Beträge werden zu positiven Ausgaben, positive Beträge zu Gutschriften. Die App unterstützt in dieser Version EUR. Vor dem Import Währung im Bankexport prüfen. Die Vorschau zeigt Originalwerte. Bei Fehlern wird der gesamte Import zurückgerollt.

Identische Buchungen werden anhand Datum, Händler, Betrag und Vorkommensnummer erkannt. Das verhindert doppelte vollständige Importe und erhält mehrere identische Buchungen innerhalb derselben Datei. Bei überlappenden Teil-Exporten ohne stabile Bank-ID ist diese Heuristik nicht eindeutig; solche Exporte prüfen. Nach Import oben den passenden Monat wählen. Ausgaben und Gutschriften werden getrennt dargestellt; Kategorie-Balken zählen positive Positionen vor Erstattungen.

`bank_providers.py` enthält das Protokoll für spätere Bankadapter und ein einheitliches Datenmodell. Noch keine Bank ist verbunden; Autorisierung, Abruf, Synchronisation und bankspezifische Umsetzung sind zu implementieren. Stabile externe IDs für Bankimporte nutzen und Zugangsdaten im macOS-Schlüsselbund speichern.

## Speicherung und Backup

Alle Buchungen und Kategorien liegen in `data/expenses.sqlite3`. Für ein vollständiges Backup die App beenden und diese Datei sichern. Zum Wiederherstellen bei beendeter App zurückkopieren. Der CSV-Export enthält aufgeteilte Positionen, ist aber kein vollständiges Backup und sollte nicht direkt wieder als Bankimport verwendet werden. Die Datenbank ist nicht separat verschlüsselt; Dateirechte begrenzen den Zugriff auf den macOS-Benutzer.

## Prüfung

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Die erste Version ist eine lokale Browser-App, kein signiertes natives macOS-App-Bundle. Automatische Kategorisierung, Belegarchiv, Bank-Synchronisierung und HTTPS-Handy-Pairing sind mögliche nächste Ausbaustufen.
