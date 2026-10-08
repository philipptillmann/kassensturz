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

Das Handy benötigt keine eigene App. „Rechnung scannen“ öffnet die Fotoauswahl bzw. Kamera. Fotos werden zum Server übertragen, dort verarbeitet und danach gelöscht. Änderungen sind beim erneuten Öffnen der Seite bzw. Zurückkehren zum Browser-Tab sichtbar. Bei gleichzeitigem Bearbeiten derselben Buchung gilt die zuletzt gespeicherte Änderung.

Die Standard-Konfiguration verwendet HTTP und ist für ein vertrauenswürdiges privates Netzwerk gedacht. Für Zugriff über das Internet die folgende HTTPS-Variante verwenden. Keine HTTP-Portfreigabe ins Internet einrichten.

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

- Monatsübersicht, Suche, eigene Kategorien und CSV-Export.
- CSV-Bankimport mit frei zugeordneten Spalten, UTF-8/Windows-1252 sowie deutscher Betrags- und Datumsdarstellung. Aktuell nur EUR.
- Eine Buchung lässt sich in einzelne Artikel mit verschiedenen Kategorien aufteilen. Die Positionssumme muss dem Buchungsbetrag entsprechen.
- OCR auf dem Server mit Tesseract, Deutsch und Englisch. JPEG, PNG, WebP und HEIC; maximal 12 MB und 25 Megapixel. Automatische Ausrichtung anhand der EXIF-Daten.
- Einfache Stichwortvorschläge für Kategorien. Erkannte Positionen und Beträge vor dem Speichern prüfen. Mehrspaltige Rechnungen benötigen ggf. manuelle Nacharbeit.
- Eine OCR-Anfrage gleichzeitig; weitere Anfragen erhalten einen Hinweis zum erneuten Versuch. Verarbeitung endet nach maximal 60 Sekunden. Keine Cloud-OCR, kein dauerhaftes Fotoarchiv, keine PDF-Erkennung.

Rechnungen für bereits importierte Umsätze **an der bestehenden Buchung** erfassen, um doppelte Ausgaben zu vermeiden. Bei CSV-Importen werden identische Buchungen anhand Datum, Händler, Betrag und Vorkommensnummer erkannt. Überlappende Teil-Exporte können ohne Bank-ID nicht immer eindeutig abgeglichen werden. Einnahmen werden als Gutschriften angezeigt; Kategorie-Auswertungen zählen positive Positionen vor Erstattungen.

`bank_providers.py` enthält weiterhin die vorbereitete Bankadapter-Schnittstelle. Es ist noch keine Bank direkt angebunden.

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

Sitzungen gelten sieben Tage, überleben Neustarts und lassen sich pro Gerät abmelden. Eine Änderung von `APP_PASSWORD` mit anschließendem `docker compose up -d` macht alte Sitzungen ungültig. Alle Geräte müssen sich neu anmelden. Als Alternative zur Umgebungsvariable unterstützt der Server `APP_PASSWORD_FILE`, z. B. für eine gemountete Docker-Secret-Datei. Daten und Passwortkonfiguration sind nicht für andere Benutzer des Servers bestimmt; die Datenbank ist nicht zusätzlich verschlüsselt.

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
