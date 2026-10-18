# Kassensturz — Server

Ausgaben, Kategorien und aufgeteilte Rechnungen in einer gemeinsamen Web-App. Laptop und Handy greifen auf dieselbe SQLite-Datenbank zu. Installation mit Docker Compose auf einem NAS, Heimserver, VPS oder Mac mit Docker Desktop.

Der Branch `local` enthält weiterhin die ursprüngliche Mac-Version. Dieser Branch `server` verwendet Flask und Waitress sowie Tesseract statt Apple Vision. Alle angemeldeten Geräte teilen **ein Haushaltskonto**; es gibt keine getrennten Benutzer oder Berechtigungsstufen.

## Installation im privaten Netzwerk

Voraussetzung: Docker Engine mit Compose v2 oder Docker Desktop. Der Rechner mit Docker muss eingeschaltet bleiben.

```sh
git clone --branch server https://github.com/philipptillmann/kassensturz.git
cd kassensturz
cp .env.example .env
```

In `.env` ein eigenes, langes Passwort setzen (mindestens 12 Zeichen):

```dotenv
APP_PASSWORD='hier-ein-eigenes-langes-passwort-eintragen'
PORT=8080
BIND_ADDRESS=0.0.0.0
PUBLIC_URL=
DOMAIN=
```

Den Beispieltext durch ein echtes Passwort ersetzen. `.env` wird nicht in Git oder ins Docker-Image aufgenommen. Werte mit `$` oder `#` in einfache Anführungszeichen setzen.

```sh
docker compose up -d --build
docker compose ps
```

- Auf dem Docker-Rechner: `http://localhost:8080`
- Auf Laptop und Handy im gleichen Netzwerk: `http://SERVER-IP:8080`, z. B. `http://192.168.1.50:8080`
- Auf beiden Geräten mit demselben Passwort anmelden. Bei Bedarf Port 8080 in der Firewall für das private Netz erlauben.

Das Handy benötigt keine eigene App. „Rechnung scannen“ öffnet die Fotoauswahl bzw. Kamera. Fotos werden zum Server übertragen und für die Texterkennung verarbeitet. Beim Speichern der Buchung wird das Foto als komprimiertes JPEG in der Datenbank archiviert. Änderungen sind beim erneuten Öffnen der Seite bzw. Zurückkehren zum Browser-Tab sichtbar. Bei gleichzeitigem Bearbeiten derselben Buchung gilt die zuletzt gespeicherte Änderung.

Die Standard-Konfiguration verwendet HTTP und ist für ein vertrauenswürdiges privates Netzwerk gedacht. Für Zugriff über das Internet die folgende HTTPS-Variante verwenden. Keine HTTP-Portfreigabe ins Internet einrichten.

### App auf dem iPhone-Home-Bildschirm

In Safari die App-Adresse öffnen und über „Teilen“ → „Zum Home-Bildschirm“
hinzufügen. Name und Symbol sind als Kassensturz hinterlegt. Nach einem Update
ein bestehendes Home-Bildschirm-Symbol bei Bedarf entfernen und neu hinzufügen,
weil iOS das alte Symbol speichern kann. Das entfernt keine Serverdaten.
Die App benötigt weiterhin eine Verbindung zum Server; es gibt keinen Offline-Modus.
Für die reguläre PWA-Installation in anderen Browsern HTTPS verwenden.

## HTTPS mit eigener Domain

Die zusätzliche Compose-Datei enthält Caddy für automatische TLS-Zertifikate. Eine Domain muss auf den Server zeigen; TCP-Ports 80 und 443 müssen von außen erreichbar sein. Bei einem Heimserver sind dafür ggf. Router-Portweiterleitungen nötig.

In `.env` das Passwort und die Domain setzen:

```dotenv
APP_PASSWORD='dein-eigenes-langes-passwort'
DOMAIN=kassensturz.example.com
```

Dann **anstelle** der Standard-Konfiguration starten:

```sh
# Nur beim Wechsel von der HTTP-Installation: den bisherigen Stack anhalten.
docker compose down
docker compose -f compose.https.yaml up -d --build
```

Auf Laptop und Handy `https://kassensturz.example.com` öffnen. Diese Variante veröffentlicht ausschließlich den Reverse Proxy, nicht den App-Port. Beide Compose-Dateien nutzen denselben Projektnamen und dasselbe Daten-Volume. Bei weiteren Befehlen für die HTTPS-Variante immer `-f compose.https.yaml` ergänzen. Caddys Zertifikate liegen in eigenen persistenten Volumes.

Bei einem bereits vorhandenen Reverse Proxy stattdessen in der Standard-Konfiguration `BIND_ADDRESS=127.0.0.1` und `PUBLIC_URL=https://deine-domain.example` setzen. Der Proxy muss den ursprünglichen `Host`-Header erhalten und auf Port 8080 weiterleiten. `PUBLIC_URL` ist eine einzelne Adresse ohne Pfad; danach über genau diese Adresse zugreifen. Secure-Cookies und HSTS werden bei einer HTTPS-Adresse aktiviert. Ungeprüfte Forwarded-Header werden nicht vertraut.

## Funktionen

### Private Daten und Demo-Datensatz

Über „Datensatz“ im Kopfbereich zwischen **Privat** und **Demo · Testdaten**
wechseln. Die Auswahl gilt pro Browser-Tab; Buchungen, Kategorien, CSV-Importe
und Exporte gehören immer zum ausgewählten Datensatz. Vor einem Wechsel offene
Bearbeitungs- oder Importdialoge schließen. Beide Datensätze nutzen dieselbe
Anmeldung und sind für alle angemeldeten Haushaltsgeräte zugänglich.

Bestehende Daten bleiben unverändert im privaten Datensatz
(`/data/expenses.sqlite3`). Die Demo liegt separat in `/data/demo.sqlite3` im
gleichen persistenten Volume. Beim ersten Start werden Beispieldaten aus
`sample-data/demo.json` angelegt, datiert auf den aktuellen und vorherigen Monat.
Diese JSON-Datei enthält ausschließlich erfundene Daten und ist in Git enthalten.
Demo-Buchungen können bearbeitet werden; Updates und Neustarts überschreiben
diese Änderungen nicht und fügen gelöschte Beispiele nicht wieder hinzu.
Neue Beispielgruppen können bei einem Update einmalig ergänzt werden. Die
Diagramm-Beispiele erweitern auch bestehende Demo-Datensätze auf zwölf Monate,
ohne vorhandene Demo-Buchungen oder private Daten zu ändern.
Private Datenbanken und `.env` bleiben von Git ausgeschlossen. Für die Entwicklung
hier den Demo-Datensatz verwenden; private Daten verbleiben auf dem eigenen Server.
Das oben dokumentierte Backup sichert den privaten Datensatz. Für ein Demo-Backup
stattdessen `/data/demo.sqlite3` als Quelldatenbank verwenden.

- Monatsübersicht, Suche, eigene Kategorien und CSV-Export.
- Diagramme: monatliche Beträge, Kategorien, Kategorieverläufe und Händler.
  Zeitraum, Kategorie und Ausgaben/Gutschriften/Verrechnung sind wählbar.
  Aufgeteilte Buchungen werden anhand ihrer Positionen ausgewertet; Monate ohne
  Buchungen erscheinen mit null. Die Diagrammfilter sind unabhängig vom Monat
  auf der Übersichtsseite. Exakte Monatswerte stehen unter „Werte anzeigen“.
- CSV-Bankimport mit frei zugeordneten Spalten, UTF-8/Windows-1252 sowie deutscher Betrags- und Datumsdarstellung. Aktuell nur EUR.
- Eine Buchung lässt sich in einzelne Artikel mit verschiedenen Kategorien aufteilen. Die Positionssumme muss dem Buchungsbetrag entsprechen.
- OCR auf dem Server mit Tesseract, Deutsch und Englisch. JPEG, PNG, WebP und HEIC; maximal 12 MB und 25 Megapixel. Automatische Ausrichtung anhand der EXIF-Daten.
- Einfache Stichwortvorschläge für Kategorien. Erkannte Positionen und Beträge vor dem Speichern prüfen. Mehrspaltige Rechnungen benötigen ggf. manuelle Nacharbeit.
- Eine OCR-Anfrage gleichzeitig; weitere Anfragen erhalten einen Hinweis zum erneuten Versuch. Verarbeitung endet nach maximal 60 Sekunden. Keine Cloud-OCR und keine PDF-Erkennung. Belegfotos werden beim Speichern dauerhaft als JPEG archiviert.

Rechnungen für bereits importierte Umsätze **an der bestehenden Buchung** erfassen, um doppelte Ausgaben zu vermeiden. Bei CSV-Importen werden identische Buchungen anhand Datum, Händler, Betrag und Vorkommensnummer erkannt. Überlappende Teil-Exporte können ohne Bank-ID nicht immer eindeutig abgeglichen werden. Einnahmen werden als Gutschriften angezeigt; Kategorie-Auswertungen zählen positive Positionen vor Erstattungen.

`bank_providers.py` enthält weiterhin die vorbereitete Bankadapter-Schnittstelle. Es ist noch keine Bank direkt angebunden.

### Gruppen und effektive Kosten

In einer Buchung unter „Gruppe“ einen Namen eintragen oder eine vorhandene Gruppe
wählen. Kauf und Beiträge getrennt erfassen; erhaltene Beiträge sind negative
Beträge. Zum Beispiel: Amazon 120 €, Beitrag in bar −30 €, PayPal-Beitrag −40 €
mit dem Gruppennamen „Geburtstagsgeschenk“ ergeben effektiv 50 €.

Die Monatsansicht lässt sich zwischen „Einzelbuchungen“ und „Effektive Kosten“
umschalten. In der effektiven Ansicht werden die Buchungen einer Gruppe im
gewählten Monat zu einer Zeile verrechnet; die Monatsbeträge und Kategorieübersicht
verwenden diese Zeilen. Ungruppierte Buchungen bleiben einzeln sichtbar. Die
Kategorie einer Gruppe stammt aus ihrer chronologisch ersten positiven Ausgabe.
Ein Beitrag im Folgemonat bleibt im Folgemonat. Ohne Monatsfilter wird über alle
Monate verrechnet. Gruppen mit einem Überschuss erscheinen als Gutschrift.

Bei aufgeteilten Rechnungen hat jede Position eine Gruppenauswahl:
„Buchungsgruppe übernehmen“ erhält die bisherige Zuordnung der gesamten Buchung,
„Keine Gruppe“ lässt den Artikel einzeln zählen, „Eigene Gruppe“ ordnet nur diesen
Artikel einem Gruppennamen zu. Unterschiedliche Artikel dürfen in verschiedene
Gruppen gehören. Die Positionssumme muss weiterhin dem Buchungsbetrag entsprechen.

Beispiel: Amazon 150 € mit Geschenk 90 €, Fahrradlicht 35 € und Küchenzubehör 25 €.
Nur das Geschenk erhält eine Gruppe. Beiträge von 20 € und 30 € ergeben effektiv
40 € fürs Geschenk; die übrigen 60 € zählen unverändert separat. Die ursprüngliche
Amazon-Buchung bleibt in der Einzelansicht eine Buchung über 150 €. CSV exportiert
den jeweils wirksamen Gruppennamen pro Position.

Eine Gruppenzeile öffnen, um ihre Buchungen bzw. Positionen zu sehen und zu bearbeiten.
Ein leeres Gruppenfeld löst eine Buchung wieder aus der Gruppe. Namen gelten
innerhalb des ausgewählten Datensatzes; gleich geschriebene Namen bilden eine
Gruppe. Die Einzelbuchungen, CSV-Exporte und Diagramme bleiben erhalten; CSV
enthält zusätzlich den Gruppennamen. Demo enthält ein entsprechendes Geschenkbeispiel.

### Kategorien umbenennen und Zahlungsmittel

Unter „Einstellungen“ eine Kategorie auswählen und ihren Namen ändern. Das
aktualisiert die Zuordnung in allen Buchungen und Rechnungspositionen des
gewählten Datensatzes. Ein bereits vorhandener Zielname wird abgelehnt; Kategorien
werden nicht automatisch zusammengelegt. Auch die Standardkategorien einschließlich
„Unkategorisiert“ können umbenannt werden. Importe und OCR-Vorschläge verwenden
danach die umbenannten Standardkategorien.

Unter „Zahlungsmittel“ sind Bar und PayPal vorbereitet; weitere Namen wie ING,
Sparkasse oder eine bestimmte Karte selbst anlegen. Jede Buchung hat ein optionales
Zahlungsmittel, das auch für ihre Rechnungspositionen gilt. Alte Buchungen bleiben
bei „Nicht angegeben“. Beim CSV-Import kann ein Zahlungsmittel für alle neu
importierten Buchungen ausgewählt werden; übersprungene Duplikate bleiben
unverändert. Zahlungsmittel erscheinen in der Buchungsliste, Gruppenansicht und
im CSV-Export. Beide Datensätze haben eigene Listen und Zuordnungen.

### Einnahmen

Beim Erfassen „Buchungstyp → Einnahme“ wählen und den Betrag positiv eingeben.
Kategorien für Gehalt, Geschenke und sonstige Einnahmen sind vorbereitet und
können umbenannt oder ergänzt werden. Einnahmen haben ein eigenes Monatstotal und
eine eigene Auswahl in den Diagrammen. Sie reduzieren keine Ausgaben oder
Ausgabengruppen. Erstattungen und Kostenbeiträge bleiben „Ausgabe / Erstattung“
mit negativem Betrag. Bestehende Buchungen behalten diese bisherige Bedeutung;
importiertes Gehalt kann nachträglich auf Einnahme umgestellt werden. CSV-Exporte
enthalten den Buchungstyp; intern behalten eingehende Beträge das negative Vorzeichen.

### Notizen

Jede Buchung hat ein optionales Freitextfeld mit bis zu 4000 Zeichen. Notizen
lassen sich später bearbeiten oder löschen, werden durchsucht und als Text im
CSV-Export mitgeführt. Die Liste zeigt eine kurze Vorschau; die vollständige
Notiz steht im Buchungseditor. Notizen gehören zur ursprünglichen Buchung,
auch bei einer Rechnung mit mehreren Positionen oder Gruppen.

### Gespeicherte Belegfotos

Ein ausgewähltes Foto wird beim Speichern der Buchung als JPEG archiviert, auch
wenn die Texterkennung fehlschlägt und die Daten manuell eingegeben werden.
JPEG, PNG, WebP und HEIC werden unterstützt. Das vollständige Foto wird anhand
seiner EXIF-Ausrichtung gedreht, auf höchstens 3200 Pixel an der längsten Seite
verkleinert (kleine Bilder werden nicht vergrößert) und mit JPEG-Qualität 85 gespeichert.
Kamerametadaten werden entfernt. Es gibt keine automatische Beschneidung oder
starre Dateigrößengrenze nach der Konvertierung, die lange Belege unlesbar machen könnte.
Die archivierte JPEG-Kopie ersetzt die ursprüngliche Datei, kein unverändertes Original.

Im Buchungseditor „Gespeicherten Beleg ansehen“ wählen. Ein neues Foto ersetzt
den vorhandenen Beleg erst beim Speichern; „Beleg entfernen“ ebenfalls. Abbrechen
ändert den gespeicherten Beleg nicht. Pro Buchung wird ein Foto gespeichert.
Beim Löschen der Buchung wird auch ihr Beleg gelöscht. Bereits früher nur per OCR
verarbeitete Fotos können nicht nachträglich wiederhergestellt werden.

Fotos liegen mit der Buchung in der SQLite-Datenbank des gewählten Datensatzes.
Das dokumentierte SQLite-Backup enthält dadurch auch die Bilder; CSV enthält
keine Bilder. Die Datenbank und ihre Sicherungen benötigen entsprechend mehr Platz.

### Eigene Konten, Gemeinschaftskonten und Umbuchungen

Unter „Einstellungen → Eigene Bankkonten“ für jedes Konto das entsprechende
Zahlungsmittel auswählen/eintragen. Einzelkonto: 100 %; Gemeinschaftskonto z. B.
50 %. Eingehende Beträge werden standardmäßig ebenfalls anteilig berücksichtigt;
diese Option kann pro Konto ausgeschaltet werden. Optional die eigene IBAN
hinterlegen. Beim CSV-Import das richtige Quellkonto wählen und, falls vorhanden,
die Spalte mit der Gegenkonto-IBAN zuordnen. Keine Bank-Passwörter erforderlich.

Ein- und Ausgänge auf unterschiedlichen konfigurierten eigenen Konten werden
als Umbuchung erkannt, wenn ihre Beträge exakt entgegengesetzt sind, die Daten
höchstens drei Tage auseinanderliegen und die Gegenkonto-IBAN auf ein eigenes
Konto verweist oder beide Beschreibungen klare Umbuchungs-/Übertragsbegriffe
enthalten. Nur beidseitig eindeutige Paare werden automatisch bestätigt. Gleiche
Beträge allein reichen nicht. Unklare Paare erscheinen unter „Umbuchungen“ zur
Bestätigung. Falsche Zuordnungen dort als normale Buchungen behandeln; diese
Entscheidung bleibt gespeichert und kann mit „Erneut prüfen“ zurückgenommen werden. Bereits benannten Ausgabengruppen zugeordnete
Buchungen/Positionen werden nicht automatisch umgebucht.

Die Einzelansicht behält volle Beträge und zeigt bestätigte Umbuchungen an. In
„Effektive Kosten“ verschwinden beide Transferbuchungen, auch über Monatsgrenzen,
bevor Kontoanteile berechnet werden. Übrige Buchungen werden mit dem persönlichen
Anteil gewichtet. Beispiel: 80 € auf einem 50-%-Konto ergeben 40 € persönliche
Ausgaben. Die Originalbeträge ändern sich nicht. Cent-Rundung erfolgt je Buchung;
aufgeteilte Positionen werden so verteilt, dass ihre Summe exakt stimmt. Für die
Diagramme „Berechnung → Eigener Anteil ohne Umbuchungen“ wählen.

Ein noch nicht importiertes Gegenstück bleibt zunächst sichtbar. Kontoeinstellungen
und Zuordnungen gelten je Datensatz und sind im Datenbank-Backup enthalten.
Neue CSV-Importe werden je Zahlungsmittel/Konto auf Duplikate geprüft. Bei alten
Importen ohne Kontozuordnung zuerst die alten Buchungen zuordnen, damit ein
erneuter Import unter einem anderen Quellkonto keine zusätzlichen Einträge erzeugt.
Das Demo enthält eine Umbuchung und einen Einkauf auf einem 50-%-Konto.

## Betrieb und Daten

### Updates per SSH / Termius

Für die erste Installation den Branch `server` klonen und `.env` wie oben
einrichten. Docker Engine mit Compose v2 muss installiert sein; der SSH-Benutzer
benötigt Zugriff auf Docker. Danach in Termius auf dem Linux-Server ausführen:

```sh
~/kassensturz/update.sh
# Bei der HTTPS-Installation stattdessen immer:
~/kassensturz/update.sh --https
```

Den Pfad an den eigenen Installationsordner anpassen. Das Skript funktioniert
aus jedem Arbeitsverzeichnis, lädt `origin/server` mit Fast-forward-Prüfung,
baut das Image und wartet bis zu 120 Sekunden auf gesunde Container. Lokale
Quellcodeänderungen oder ein anderer Branch stoppen das Update. `.env` und das
Daten-Volume bleiben erhalten. Ein fehlgeschlagener Build lässt die laufende
App verfügbar; ein fehlgeschlagener Containerstart führt zu einem Fehler, ohne
automatisch auf die alte Version zurückzurollen. Zur Diagnose
`docker compose logs --tail=100 app` verwenden (bei HTTPS mit
`-f compose.https.yaml`). Vor größeren Änderungen ein Backup erstellen.

Entwicklungsablauf: Änderungen hier entwickeln und prüfen, eine funktionierende
Version nach GitHub auf `server` pushen, das Skript in Termius ausführen und die
vorhandene App-Adresse im Handy-Browser neu laden. Noch nicht gepushte Änderungen
sind auf dem Linux-Server nicht verfügbar. Beim ersten Wechsel zwischen HTTP und
HTTPS die oben beschriebenen Schritte verwenden; das Skript ist für Updates der
bereits gewählten Installation gedacht.

```sh
docker compose logs --tail=100 app
docker compose stop
# Nach Code-Updates:
git pull --ff-only
docker compose up -d --build
```

Daten liegen im Docker-Volume `kassensturz_data` unter `/data/expenses.sqlite3`. Container laufen ohne Root-Rechte, mit schreibgeschütztem Dateisystem und separatem temporären Speicher. Container-Neustarts und neue Images behalten die Daten. **`docker compose down --volumes` löscht die Daten-Volumes**; im normalen Betrieb nur `down` ohne diese Option verwenden.

Mit der standardmäßig aktivierten Option „Angemeldet bleiben“ gelten neue Sitzungen
90 Tage; ohne diese Option sieben Tage. Sitzungen überleben Neustarts und Updates
und lassen sich pro Gerät abmelden. Bestehende Sitzungen behalten ihre ursprüngliche
Laufzeit; für 90 Tage einmal abmelden und mit der aktivierten Option neu anmelden.
Der Browser speichert ein Sitzungscookie, nicht das Passwort. Immer dieselbe
Serveradresse verwenden: IP-Adresse und Hostname haben getrennte Cookies. Eine Änderung von `APP_PASSWORD` mit anschließendem `docker compose up -d` macht alte Sitzungen ungültig. Alle Geräte müssen sich neu anmelden. Als Alternative zur Umgebungsvariable unterstützt der Server `APP_PASSWORD_FILE`, z. B. für eine gemountete Docker-Secret-Datei. Daten und Passwortkonfiguration sind nicht für andere Benutzer des Servers bestimmt; die Datenbank ist nicht zusätzlich verschlüsselt.

### Konsistentes Backup im laufenden Betrieb

SQLite-Backup verwenden, damit laufende Schreibvorgänge und WAL-Daten berücksichtigt werden:

```sh
docker compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/data/expenses.sqlite3'); d=sqlite3.connect('/tmp/kassensturz-backup.sqlite3'); s.backup(d); d.close(); s.close()"
docker compose cp app:/tmp/kassensturz-backup.sqlite3 ./kassensturz-backup.sqlite3
```

Das Backup außerhalb des Servers aufbewahren. Ein CSV-Export ersetzt kein vollständiges Backup.

### Vorhandene lokale Daten übernehmen oder Backup wiederherstellen

In einer **neuen Installation mit leerem Daten-Volume**, vor dem ersten Start:

```sh
docker compose run --rm --no-deps -T app python -c "import pathlib,sys; p=pathlib.Path('/data/expenses.sqlite3'); assert not p.exists(), 'Datenbank existiert bereits'; p.write_bytes(sys.stdin.buffer.read()); p.chmod(0o600)" < /pfad/zum/kassensturz-backup.sqlite3
docker compose up -d --build
```

Vor dem Import muss das Image gebaut sein: `docker compose build`. Für Daten aus dem Branch `local` zuerst die lokale App beenden und deren `data/expenses.sqlite3` sichern. Bestehende Serverdaten nicht überschreiben: zur Wiederherstellung eine separate, leere Installation verwenden und nach der Prüfung umstellen. Die Session-Tabelle wird beim Start ergänzt; vorhandene Buchungen und Kategorien bleiben erhalten.

## Entwicklung und Tests

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node --check static/login.js
```

Ohne Docker kann die App mit `APP_PASSWORD='ein-langes-testpasswort' .venv/bin/python server.py` gestartet werden. Tesseract samt Sprachpaketen muss dafür separat installiert sein. Die `.env` wird ausschließlich durch Compose eingelesen.

Die GitHub-Actions-Pipeline baut das Docker-Image und prüft Anmeldung, CSRF-Schutz, Sitzungsablauf, Passwortwechsel, zwei Geräte, Import, echte Tesseract-OCR, HEIC-Decodierung, Nicht-Root-Ausführung sowie Datenpersistenz nach einem Container-Neustart. Es wird kein Image in eine Registry veröffentlicht; `docker compose up --build` baut es auf dem Zielserver.

Technische Referenzen: [Waitress-Konfiguration](https://docs.pylonsproject.org/projects/waitress/en/latest/arguments.html), [Pillow EXIF-Ausrichtung](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html).

### Mehrere Benutzer und bestehende Daten übernehmen

Nach dem Update zunächst wie bisher mit dem `APP_PASSWORD` anmelden. Unter
**Einstellungen → Benutzerkonto** einen Benutzernamen und ein neues Passwort
(mindestens 12 Zeichen) wählen und **Bestehende Daten diesem Konto zuordnen**
anklicken. Dieses erste Konto wird Administrator und übernimmt unverändert alle
bisherigen Buchungen, Belege, Kategorien, Kontoeinstellungen und den bisherigen
Demo-Datensatz. Es ist kein CSV-Import nötig. Vorher eine Sicherung erstellen.
Alle bisherigen Sitzungen werden beendet; anschließend mit Benutzername und dem
neu gewählten Passwort anmelden. Die Zuordnung ist einmalig.

Unter **Einstellungen → Benutzer verwalten** kann der Administrator weitere
Konten anlegen. Jedes Konto hat eigene private Daten und eigene Demo-Daten;
auch der Administrator sieht in der Finanzansicht ausschließlich seine eigenen
Daten. Es gibt keine öffentliche Registrierung oder gemeinsame Finanzansicht.
Benutzernamen sind unabhängig von Groß-/Kleinschreibung. Neue Benutzer erhalten
keine Kopie der privaten Daten des Administrators.

Nach der Umstellung dient `APP_PASSWORD` nicht mehr zur Anmeldung und ist kein
Notfallpasswort. Die Variable für die bestehende Compose-Konfiguration beibehalten;
eine Änderung daran ändert keine Benutzerpasswörter. Eigene Passwörter können
unter Einstellungen geändert werden; dabei werden die Sitzungen dieses Kontos
beendet. Vergessene Passwörter kann der Serverbetreiber interaktiv zurücksetzen:

```sh
docker compose exec app python users.py BENUTZERNAME
```

Das neue Passwort wird verdeckt abgefragt und nicht als Kommandozeilenargument
übergeben. Benutzerpasswörter werden nur als gesalzene Hashes gespeichert.

### Vollständiges Backup mit mehreren Benutzern

Die oben beschriebene Sicherung von `expenses.sqlite3` allein enthält nur die
Daten des ersten Kontos und die Benutzerverwaltung. Weitere Konten liegen unter
`/data/users/`, Demo-Daten ebenfalls in eigenen Datenbanken. Für eine vollständige
Sicherung **das gesamte Datenvolume** sichern. Beispielsweise mit kurzem Stopp
(wie üblich im Repository-Verzeichnis, gegebenenfalls die HTTPS-Compose-Datei ergänzen):

```sh
umask 077
docker compose stop app
docker compose run --rm --no-deps -T --entrypoint python app -c "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); t.add('/data',arcname='data'); t.close()" > kassensturz-all-users.tar.gz
docker compose start app
```

Exitstatus und Archiv prüfen, bevor die Sicherung extern aufbewahrt wird. Das
Archiv enthält private Finanzdaten, Belege und Passwort-Hashes. Zur vollständigen
Wiederherstellung bei gestoppter Anwendung den Inhalt von `data/` aus diesem
Archiv in ein leeres Datenvolume zurückspielen (Eigentümer UID/GID 10001). Die
Verzeichnisstruktur einschließlich `users/` muss erhalten bleiben. Eine einzelne
CSV-Datei ersetzt dieses Backup nicht.

### Entwicklung auf beiden Plattformen und Freigabe von Kosten

Neue Funktionen werden auf den Branches `server` und `android-standalone`
umgesetzt. Die GitHub-Actions-Workflows sind ausschließlich manuell startbar;
Pushes und Pull Requests starten keine Builds oder Tests. Vor jedem potenziell
kostenpflichtigen Lauf ist eine ausdrückliche Zustimmung erforderlich, auch bei
vorhandenem Freikontingent. Server-Tests kann der Betreiber selbst durchführen.

Für jede veröffentlichte Android-App-Version legt der veröffentlichende Assistent
ein GitHub-Issue mit Version, Build-Commit, APK-Link bzw. ausstehendem Build und
einer Testliste an. Die Erstellung erfolgt über die GitHub-API und benötigt keine
Actions-Minuten. Getestet wird auf einem echten Gerät. Das Issue bleibt offen,
bis der Benutzer es nach dem Test manuell abschließt.

### Gemeinsame Versionsnummer

Aktueller gemeinsamer Versionsname: **0.6.0**. Die Datei `VERSION` im Repository-
Stamm ist die Quelle für Docker/Server und Android und wird auf beiden Branches
gleich gehalten. Das Docker-Image enthält diese Datei; die Web-App zeigt die
Version unter Einstellungen an. Android verwendet sie als `versionName`. Der
interne Android-`versionCode` zählt installierbare Updates unabhängig davon.

### Barausgabe per Schnellwahl (0.2.0)

Auf der Startseite öffnet **Barausgabe** mit Münzsymbol eine neue Ausgabe mit
vorausgewähltem Zahlungsmittel **Bar**. Betrag und Beschreibung ergänzen und
speichern. Die Schnellwahl verwendet den ausgewählten Privat-/Demo-Datensatz;
beim bloßen Öffnen oder Abbrechen wird keine Buchung gespeichert. Das
Zahlungsmittel kann vor dem Speichern weiterhin geändert werden.

### Kategorie Ausgehen (0.3.0)

**Ausgehen** ist eine Standardkategorie für Getränke in Bar oder Club sowie
Restaurantbesuche. Sie steht nach dem Update auch in bestehenden Privat- und
Demo-Datensätzen aller Benutzer zur Auswahl. Bestehende Buchungen werden nicht
automatisch umkategorisiert. Ein späteres Umbenennen bleibt erhalten.


### Export one account to Android

The native app is maintained as a root-level Android project on the separate
[`android-standalone` branch](https://github.com/philipptillmann/kassensturz/tree/android-standalone).
The server-side migration tool stays here, at `tools/export_android.py`. It uses
only Python's standard library, opens source databases read-only and captures a
consistent SQLite snapshot. It exports exactly one account's financial records
and receipts, without password hashes or sessions.

Run against the complete data directory on the server host or a restored backup:

```sh
python3 tools/export_android.py --data-dir /path/to/kassensturz-data \
  --username YOUR_USERNAME --output /private/path/kassensturz-phone.zip
```

Use `--legacy` instead of `--username` only for an installation that has never
migrated to named accounts. `--dataset demo` selects that account's demo dataset;
private is the default. Existing output files are never overwritten. The data
directory must include `expenses.sqlite3` and, for additional users, `users/` with
its original structure. When using a copy, restore a consistent complete backup
instead of copying live SQLite files while writes are active. The script may
also be copied and run independently; no Android checkout is needed on the server.

Transfer the ZIP to Android and use **Privat → Mehr → Sicherung wiederherstellen**.
Restoring replaces the selected local dataset; back up existing phone data first.
Compare counts, balances, split groups and receipts, and retain the original
server data. This is a one-time copy, not synchronization. Server CSV import keys
are preserved but differ from Android's newly generated keys; check duplicates
before re-importing overlapping statements. The ZIP contains unencrypted private
data; keep it outside Git and protect its storage and transfer.

Exporter checks now live in `tests/test_android_export.py` and are included in
the existing server unittest discovery. The export tool itself needs no server
Python dependencies. As usual, request approval before potentially metered tests
or workflows; the repository move does not authorize running them.


### Datumsfeld auf mobilen Geräten (0.3.1)

Datums- und Monatsfelder bleiben innerhalb ihrer verfügbaren Formularbreite,
auch bei der nativen Darstellung in Safari. Formularspalten und Beschriftungen
können schrumpfen, sodass das Datumsfeld den Buchungseditor nicht seitlich
verbreitert. Der native Android-Editor verwendet ein einzeiliges Datumsfeld in
Dialogbreite. Gespeicherte Daten und das Datumsformat bleiben unverändert.


### CSV duplicate preview (0.4.0)

Before committing a CSV import, the app reports new and already imported entries
for the selected account and dataset. Cancelling changes nothing; saving rechecks
against the latest data. Identical genuine purchases within one statement keep
their occurrence counts. Other accounts remain independent. Matching uses the
existing date/description/amount/account import identity, not fuzzy guesses:
changed bank descriptions or overlapping partial exports without stable bank IDs
can remain ambiguous. Manually entered lookalikes are not automatically removed.


### File backup and restore (0.5.0)

Server: under Einstellungen → Sicherung & Wiederherstellung, download a full ZIP
for the currently selected user's private/demo dataset. It includes entries,
splits, categories and renamed default aliases, payment/account settings, groups,
transfer links/ignored pairs, CSV import identities and JPEG receipts. Credentials,
sessions and other users are excluded; use the existing whole-volume procedure
for an administrator's complete server/disaster-recovery backup.

Select a ZIP to validate and preview its counts before confirming replacement of
the current dataset. Validation uses isolated temporary storage; invalid archives
leave live data unchanged. A valid restore replaces only financial tables in one
transaction. Existing login accounts/sessions remain intact. Back up first.

Android: Mehr → Vollständige Sicherung erstellen / Sicherung wiederherstellen.
New ZIPs record source dataset/time; restore shows entry/receipt counts before
confirmation. The complete archive is validated during transactional restore.
Older native and server-account exports remain supported. Server ZIPs use the
same portable format. Android ZIPs have no server category-alias history: on
server restore missing standard aliases/default names are added without changing
existing entry categories. No automatic two-way synchronization is performed.

Limits: 50,000 entries, 2,000 categories/payment methods, 16 MB JSON metadata,
4 MB per JPEG, 512 MB receipt data; server ZIP uploads at most 544 MB. Large
server backups use temporary space in the writable data volume (not the 256 MB
/tmp tmpfs); leave roughly three times the archive size free for upload, staging
and transactional replacement. A reverse proxy may need a corresponding
upload limit/timeout. ZIPs contain unencrypted private financial data: protect
them and keep them outside Git. CSV is a spreadsheet export, not a full backup.


### iPhone-Kurzbefehls-API (0.6.0)

Wie in Friss speichert **POST /json-import** eine Ausgabe in einem Aufruf mit
Bearer-Schlüssel und den Feldern `timestamp`, `original_message`, `ai` (Text oder
Objekt). **Einstellungen → iPhone-Kurzbefehle** erstellt/widerruft Schlüssel für
je einen Benutzer und festen Privat-/Demo-Datensatz. Beträge werden geprüft;
identische Retries erzeugen keine doppelte Buchung. Originale sind im Editor
unter Kurzbefehlsquelle sichtbar und in Server-ZIP-Sicherungen enthalten.

Die vollständige [iPhone-Anleitung mit Format und Beispiel](docs/AI_SHORTCUT.md)
und der [deutsche AI-Prompt](docs/AI_PROMPT_DE.txt) liegen im Projekt. Der Server
ruft kein Modell auf. Diese Integration ist ausdrücklich serverseitig; die
Standalone-Android-App bleibt offline und erhält nur die gemeinsame Versions-
und Build-Metadatenanpassung für 0.6.0.

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
