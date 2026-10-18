# iPhone-Kurzbefehl: Ausgabe in einem Aufruf speichern (0.6.0)

Der Ablauf entspricht [Friss' One-step-Import](https://github.com/philipptillmann/Friss/blob/server/docs/AI_SHORTCUT.md):
`POST /json-import`, Bearer-Schlüssel und genau `timestamp`, `original_message`,
`ai`. Für Kassensturz enthält `ai` Ausgabenfelder statt Nährstoffen.

## Schlüssel einrichten

1. In Kassensturz mit deinem eigenen Benutzerkonto anmelden. Falls noch das
   ursprüngliche App-Passwort verwendet wird, zuerst die bestehenden Daten einem
   Benutzerkonto zuordnen.
2. **Einstellungen → iPhone-Kurzbefehle** öffnen. Einen Namen und ausdrücklich
   **Privat** oder **Demo** wählen und einen Schlüssel erstellen.
3. Den einmal angezeigten Schlüssel kopieren. Im Kurzbefehl als Geheimnis
   aufbewahren, nicht in Git, Screenshots, URLs oder öffentlich geteilten
   Kurzbefehlen. Der Server speichert nur dessen Hash. Nach dem Ausblenden kann
   der vollständige Schlüssel nicht erneut angezeigt werden; bei Verlust einen
   neuen erstellen und den alten widerrufen.

Jeder Schlüssel gilt nur für seinen Benutzer und festen Datensatz und darf nur
Ausgaben/Erstattungen anlegen. Er erlaubt weder Lesen noch Ändern/Löschen,
Benutzerverwaltung oder Zugriff auf Backups. Ein Passwortwechsel/Reset macht
die bisherigen Schlüssel ungültig; Abmelden im Browser widerruft sie nicht.
Es können höchstens 20 aktive Schlüssel je Benutzer bestehen.

Wie bei Friss die eigene LAN-/VPN-Adresse oder eine HTTPS-Adresse verwenden.
Der Server muss vom iPhone erreichbar sein. Das normale Kontopasswort und ein
Friss-Schlüssel sind keine Kassensturz-API-Schlüssel.

## Kurzbefehl

1. Beschreibung abfragen, z. B. „24,50 Euro im Restaurant, bar bezahlt“.
   Diesen Originaltext in einer Variable behalten.
2. Das tatsächliche Buchungsdatum mit Uhrzeit wählen und als **ISO 8601 mit
   Zeitzone** formatieren. Kassensturz verwendet dessen Kalendertag in der
   angegebenen Zeitzone, ohne eine Verschiebung zum UTC-Vortag.
3. Optional den Text und ein Foto mit dem [deutschen Prompt](AI_PROMPT_DE.txt)
   an das Modell im bestehenden Kurzbefehl übergeben. Die komplette Antwort
   als Text behalten. Manuell erstelltes JSON funktioniert ebenfalls; der
   Server ruft kein Modell und keinen anderen Dienst auf.
4. **Inhalt von URL abrufen**:
   - URL: `http://DEIN-SERVER:8082/json-import` (Adresse/Port ggf. anpassen).
   - Methode: **POST**.
   - Header: `Authorization` = `Bearer DEIN_KASSENSTURZ_SCHLUESSEL`.
   - Header: `Content-Type` = `application/json`.
   - Anfragetext **JSON**, mit genau drei Feldern:

| Feld | Typ in Kurzbefehle | Inhalt |
| --- | --- | --- |
| `timestamp` | Text | Gewähltes Datum als ISO 8601 mit Zeitzone |
| `original_message` | Text | Unveränderte ursprüngliche Beschreibung |
| `ai` | Text | Komplette JSON-Antwort des Modells |

Kurzbefehle übernimmt das Escaping des Antworttexts. Keine UUID erzeugen,
keinen JSON-Text von Hand zusammensetzen, keinen Preview-/Commit-Aufruf starten.
Andere Clients können `ai` auch direkt als JSON-Objekt senden. Ein einzelner
Markdown-JSON-Codeblock um den Antworttext wird toleriert.

## Ausgabenformat

`ai.title` (1–200 Zeichen) und `ai.amount` sind erforderlich. `amount` ist der
**Gesamtbetrag in EUR**, nicht Cent: z. B. `"24.50"` oder `"24,50"`. Höchstens
zwei Nachkommastellen, ungleich null. Positive Werte sind Ausgaben, negative
Werte Erstattungen/Beiträge. Der Endpunkt erfasst keine Gehaltseinnahmen.

Optionale Felder:

- `currency`: nur `"EUR"` (Standard). Keine automatische Währungsumrechnung.
- `category`: vorhandener Kategoriename. Standard: die aktuelle
  Unkategorisiert-Kategorie; umbenannte Standardkategorien werden über ihre
  gespeicherten Aliase erkannt. Unbekannte Namen werden abgelehnt.
- `payment_method`: vorhandenes Zahlungsmittel, z. B. `"Bar"` oder `"PayPal"`.
  Weglassen bedeutet „Nicht angegeben“. Eigene Banknamen vorher in der App anlegen.
- `notes`: bis 2.000 Zeichen, erscheint als Buchungsnotiz.
- `group_name`: bis 80 Zeichen, z. B. für Kauf und Beiträge zu einem Geschenk.
- `items`: bis 200 Positionen mit `name`, `amount`, optional `category` und
  `group_name`. Die Positionssumme muss exakt dem Gesamtbetrag entsprechen.
  Fehlende Positionskategorie übernimmt die Buchungskategorie. Fehlende oder
  `null`-Positionsgruppe übernimmt die Buchungsgruppe; `""` bleibt ungruppiert.

Es entsteht **eine** Buchung; Positionen werden nicht nochmals als separate
Buchungen gespeichert. Datum, IDs, Datensatz und Benutzer kommen vom
Kurzbefehl/Server, nicht vom Modell. Unbekannte Felder werden abgelehnt.
Fotos werden von diesem Endpunkt nicht hochgeladen oder gespeichert; Belegbilder
weiterhin in der App an die gespeicherte Buchung anhängen.

Der unveränderte Originaltext (bis 10.000 Zeichen), die AI-Antwort und der
Zeitstempel werden zusätzlich gespeichert. Im Buchungseditor unter
**Kurzbefehlsquelle** sind sie einsehbar. Server-ZIP-Sicherungen enthalten diese
Quellen und Retry-Historie, aber keine API-Schlüssel. Eine Android-Sicherung nach
einer plattformübergreifenden Datenübernahme behält nur die gemeinsamen
Finanzdaten und Import-IDs, nicht diese serverseitige Quellen-/Löschhistorie.

## Antworten und Wiederholungen

- **201** + `status: "completed"`, `duplicate: false`: neue Buchung gespeichert.
- **200** + `duplicate: true`: identischer Aufruf bereits verarbeitet; dieselbe
  `id` und `entry_ids`, keine zweite Buchung und kein Überschreiben späterer Änderungen.
- **422**: inhaltlich ungültig, nichts gespeichert. AI-JSON-Syntaxfehler nennen
  Zeile/Spalte. **400** bedeutet ungültigen äußeren JSON-Anfragetext.
- **401**: Schlüssel fehlt, ist falsch, widerrufen oder nach Passwortwechsel ungültig.
- **403**: fremder Ursprung oder ein ausdrücklich angefragter anderer Datensatz.
- **409**: der Eintrag dieses Aufrufs wurde gelöscht; ein Retry legt ihn nicht neu an.
- **413**: gesamte Anfrage über 256 KiB.

Für einen Retry alle drei Felder unverändert behalten: nicht nochmals das Modell
aufrufen und keinen neuen aktuellen Zeitstempel erzeugen. Objekt-Schlüsselreihenfolge
spielt keine Rolle; bei `ai` als Text gehört dessen genaue Formatierung zum
Aufruf. Geänderter Text/Zeitstempel bedeutet einen neuen Import. Für zwei echte
identische Ausgaben unterschiedliche tatsächliche Zeitstempel verwenden.
Dies ist kein Update-Endpunkt. Eine finanzielle ZIP-Wiederherstellung setzt auch
die darin enthaltene Retry-Historie auf den Stand der Sicherung zurück.

## Beispiel

[Vollständige Anfrage](examples/shortcut-expense.json), für einen Demo-Schlüssel:

```sh
curl http://DEIN-SERVER:8082/json-import \
  -H 'Authorization: Bearer DEIN_KASSENSTURZ_SCHLUESSEL' \
  -H 'Content-Type: application/json' \
  --data-binary @docs/examples/shortcut-expense.json
```

Beim iPhone-Kurzbefehl stattdessen `ai` als **Text** mit der Modellantwort füllen.
