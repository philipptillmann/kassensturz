# Kassensturz: Buchungen per iPhone-Kurzbefehl erstellen (0.11.0)

**POST /json-import** erstellt eine Buchung direkt aus deren Feldern.

## API-Schlüssel

Unter **Einstellungen → iPhone-Kurzbefehle** einen Schlüssel mit Name und festem
Datensatz (Privat oder Demo) erstellen. Dafür zuerst ein eigenes Benutzerkonto
anlegen bzw. die bestehenden Daten diesem Konto zuordnen. Den einmal angezeigten
Schlüssel im Kurzbefehl aufbewahren. Der Server speichert nur seinen Hash.
Bestehende Schlüssel bleiben gültig. Widerruf und Passwortwechsel sperren sie.
Ein Schlüssel darf nur Buchungen für seinen Benutzer und festen Datensatz anlegen;
er erlaubt keinen Lese-, Änderungs-, Lösch- oder Backup-Zugriff.

## Anfrage

URL: `http://DEIN-SERVER:8082/json-import` (eigene Adresse/Port anpassen).
Vom iPhone erreichbare LAN-/VPN-Adresse oder HTTPS verwenden.
In **Inhalt von URL abrufen** die Methode **POST** und den Anfragetext **JSON** wählen.

Header:

- `Authorization: Bearer DEIN_KASSENSTURZ_SCHLUESSEL`
- `Content-Type: application/json`

Die Buchungsfelder stehen direkt im JSON-Objekt:

```json
{
  "date": "2026-10-19",
  "merchant": "Restaurant",
  "amount": "24.50",
  "kind": "expense",
  "category": "Ausgehen",
  "payment_method": "Bar",
  "notes": ""
}
```

| Feld | Pflicht | Bedeutung |
| --- | --- | --- |
| `date` | Ja | Buchungstag als Text `JJJJ-MM-TT` |
| `merchant` | Ja | Händler/Beschreibung, 1–200 Zeichen |
| `amount` | Ja | Betrag in **Euro**, nicht Cent; Zahl oder Text `"24.50"`/`"24,50"`; maximal zwei Nachkommastellen, nicht null |
| `kind` | Nein | `expense` (Standard): Ausgaben positiv, Erstattungen/Beiträge negativ. `income`: Einnahme; Betrag wird wie im Buchungsformular als positiver Eingabebetrag erfasst und intern negativ gespeichert |
| `category` | Nein | Vorhandene Kategorie; Standard ist die aktuelle Unkategorisiert-Kategorie. Gespeicherte Aliase umbenannter Standardkategorien funktionieren ebenfalls |
| `payment_method` | Nein | Vorhandenes Zahlungsmittel wie `Bar`, `PayPal` oder ein eigener Bankname; Standard leer („Nicht angegeben“) |
| `notes` | Nein | Freitext, bis 4.000 Zeichen |
| `group_name` | Nein | Gruppenname, bis 80 Zeichen |
| `items` | Nein | Bis 200 Positionen; siehe unten |
| `currency` | Nein | Nur `EUR` (Standard); keine Währungsumrechnung |
| `request_id` | Nein | UUID für sichere Wiederholungen und zwei ansonsten identische echte Buchungen; siehe unten |

Unbekannte Felder werden abgelehnt. IDs gespeicherter Einträge, Benutzer und Datensatz
werden vom Server bestimmt. Bilder werden hier nicht hochgeladen; Belege in der App
an die gespeicherte Buchung anhängen. Es wird kein externer Dienst aufgerufen.

## Positionen

Optional `items` als JSON-Liste mit `name`, `amount`, optional `category` und
`group_name` angeben. Fehlende Kategorie übernimmt die Buchungskategorie. Fehlende
oder `null`-Gruppe übernimmt die Buchungsgruppe; `""` bleibt ungruppiert. Die Summe
muss exakt dem Gesamtbetrag entsprechen. Bei Einnahmen werden die Positionsbeträge
wie im Formular als positive Eingabebeträge angegeben. Es entsteht eine Buchung,
keine zusätzlichen Einzelbuchungen für die Positionen.

## Wiederholungen und Antworten

Für einen Retry dieselben Felder unverändert senden; die JSON-Schlüsselreihenfolge
ist egal. Optional einmal pro echter Buchung eine UUID im Kurzbefehl erzeugen und
als `request_id` mitsenden. Diese UUID beim Retry behalten. Für zwei echte identische
Buchungen unterschiedliche UUIDs verwenden. Ohne `request_id` zählt ein vollständig
identisches JSON-Objekt als Retry und erzeugt keine zweite Buchung. Verschiedene
Schreibweisen von Zahlen oder optionale Zusatzfelder gelten als geänderte Daten.
Dies ist kein Update-Endpunkt; ein Retry überschreibt keine späteren Änderungen.

- **201**, `duplicate: false`: neue Buchung, ID in `entry_ids`.
- **200**, `duplicate: true`: bereits verarbeitet, gleiche IDs.
- **400**: äußerer JSON-Anfragetext ungültig.
- **401**: Schlüssel fehlt, falsch, widerrufen oder nach Passwortwechsel ungültig.
- **403**: fremder Ursprung oder anderer ausdrücklich angefragter Datensatz.
- **409**: Eintrag gelöscht oder `request_id` bereits mit anderen Daten verwendet.
- **422**: ungültige Buchungsfelder, nichts gespeichert.
- **413**: Anfrage über 256 KiB.

Das gesendete JSON ist im Buchungseditor unter **Kurzbefehlsquelle** sichtbar.
Server-ZIP-Sicherungen enthalten diese Quellen und Retry-Historie, keine API-Schlüssel.
Eine Wiederherstellung setzt die Retry-Historie auf den Stand der Sicherung zurück.
Android übernimmt gemeinsame Finanzdaten/Import-IDs, keine serverseitige Quellenhistorie.
Fehlt nach einer solchen Übernahme die Quelle einer bereits benutzten `request_id`,
wird ein erneuter Aufruf mit **409** abgelehnt; die bestehende Buchung in der App prüfen.

## Beispiel mit curl

```sh
curl http://DEIN-SERVER:8082/json-import \
  -H 'Authorization: Bearer DEIN_KASSENSTURZ_SCHLUESSEL' \
  -H 'Content-Type: application/json' \
  --data-binary @docs/examples/shortcut-expense.json
```
