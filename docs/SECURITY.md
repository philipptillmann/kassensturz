# HTTPS und optionale Serververschlüsselung (1.0.0)

## Geltungsbereich

`server` und `local` teilen den Web-Code; `local` hat bewusst einen Loopback-Start
für die Entwicklung. `android-standalone` bleibt eine unabhängige App. Diese
Funktion verschlüsselt die **Server-Datenbanken**, nicht das Android-Gerät und
nicht nachträglich den gesamten Datenträger. Verschlüsselung ist standardmäßig AUS.

## HTTPS ist der Serverstandard

`compose.yaml` startet Caddy und die App in einem privaten Docker-Netz. Nur Caddy
veröffentlicht Ports. HTTP liefert ausschließlich eine Weiterleitung auf HTTPS;
die App-Seite, Anmeldung und Shortcut-Endpunkte immer mit `https://` verwenden.
Der interne App-Port 8080 darf nicht zusätzlich ins LAN/Internet freigegeben werden.
Nur der private Reverse Proxy darf `X-Forwarded-Proto` setzen; Waitress übernimmt
nur diesen Forwarded-Header und Flask vertraut genau einem Proxy für das Schema.
Ohne HTTPS-PUBLIC_URL startet die Produktionsanwendung nicht. Direkte unsichere
GET-Aufrufe werden auf die feste HTTPS-Adresse umgeleitet, schreibende HTTP-Aufrufe
mit 426 abgewiesen. Healthchecks auf dem internen Port bleiben möglich.

In `.env` eintragen (Beispielnamen, keine echten Serverdaten):

```dotenv
APP_PASSWORD='LANGES-EIGENES-PASSWORT'
DOMAIN=kassensturz.example.com
HTTPS_PORT=443
HTTP_PORT=80
CADDY_CONFIG=./Caddyfile
```

`DOMAIN` ist nur Hostname/IP, ohne Schema, Pfad oder Port. Für öffentliche
Zertifikate müssen DNS und ACME-Erreichbarkeit passen. Eigene Portbelegung bleibt
möglich: `HTTPS_PORT=8082`. Wenn HTTPS_PORT fehlt, wird vorhandenes `PORT` als
Fallback verwendet; danach Standard 443. HTTP_PORT darf angepasst werden, falls
Port 80 bereits belegt ist. Ein öffentlicher ACME-HTTP-Nachweis benötigt trotzdem
Erreichbarkeit über Port 80 oder einen passend konfigurierten vorhandenen Proxy.

Für reine LAN-Namen oder IP-Adressen `CADDY_CONFIG=./Caddyfile.internal` wählen.
Caddy erstellt dann eine **lokale** CA; HTTPS ist erst nach einmaliger Installation
und Vertrauenseinstellung ihres öffentlichen Root-Zertifikats ohne Warnung nutzbar:

```sh
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./kassensturz-root.crt
```

Nur diese öffentliche `.crt` auf die Geräte übertragen, niemals private CA-Dateien.
Auf iPhone/iPad: Zertifikatsprofil installieren, danach unter Einstellungen →
Allgemein → Info → Zertifikatsvertrauenseinstellungen vollständiges Vertrauen
aktivieren. Auf Linux/macOS/Android die jeweilige Vertrauensverwaltung verwenden;
Browser können einen eigenen Zertifikatsspeicher haben. Die CA nur auf Geräten
installieren, die deinem Server vertrauen. Kein Umgehen von Zertifikatsprüfungen.

`./update.sh` verwendet nun HTTPS; `--https` bleibt als kompatibler Alias.
Bestehende Installation **vor dem Update** sichern, DOMAIN/Ports/CA einrichten und
in `.env` übernehmen. Die Konfiguration wird vor dem Ersetzen der laufenden App
validiert. `.env` wird nicht überschrieben; bisherige HTTP-Bookmarks und Shortcuts
auf HTTPS umstellen. An der neuen HTTPS-Adresse erneut anmelden. Das Daten-Volume
behält den bisherigen Namen. `compose.https.yaml` ist dieselbe sichere Alternative.

Die lokale Entwicklung verwendet dagegen `run_local.py` oder `compose.local.yaml`
ausschließlich über 127.0.0.1 und ausdrücklich `ALLOW_HTTP=1`. Dies ist keine
Konfiguration für die Freigabe im Netzwerk.

## Optional: Datenbanken mit SQLCipher verschlüsseln

Die Linux-Server-Image-Abhängigkeiten enthalten `sqlcipher3==0.6.4`. Bei direkten
Python-Installationen zusätzlich `requirements-encryption.txt` installieren.
Ohne `DATA_ENCRYPTION_KEY_FILE` wird unverändert SQLite verwendet. Mit dieser
Variable sind Authentifizierung, Sitzungen/API-Schlüssel-Hashes, alle Privat-/Demo-
und Benutzerdatenbanken, Vermögen und darin gespeicherte JPEG-Belege vollständig
SQLCipher-verschlüsselt. Ein falscher/fehlender Schlüssel oder fehlender Treiber
führt zum Fehler, niemals zum Rückfall auf Klartext oder zum automatischen Ersetzen.
Dateinamen, Größen und Zugriffszeiten bleiben sichtbar.

Schlüssel: exakt 32 zufällige Bytes als 64 Hexzeichen in einer Datei, außerhalb
von Git und außerhalb des Datenverzeichnisses. Für Python-Quellbetrieb:

```sh
python tools/encrypt_data.py --key-file /SICHERER-PFAD/data.key --generate-key
```

Die Datei wird exklusiv mit Modus 0600 angelegt, niemals überschrieben oder auf
dem Terminal ausgegeben. Separat und geschützt sichern; bei Verlust ist keine
Wiederherstellung möglich. Keine Schlüsselwerte in `.env`, Kommandozeilen oder
Issues schreiben. Für Docker müssen Schlüsseldatei (0400/0600) und Datenverzeichnis
für Container-UID 10001 lesbar bzw. schreibbar sein. Der Schlüssel darf keine
Gruppen-/Weltleserechte haben. Berechtigungen gezielt als Administrator setzen,
z. B. `chown 10001:10001 /SICHERER-PFAD/data.key` und `chmod 400 ...`. Die lokale
Schlüsselgenerierung/Migration muss unter einem Benutzer laufen, der ihn lesen darf.

### Bestehende Daten: explizite Offline-Kopie

1. Vollständige Sicherung erstellen und den Server anhalten. Keine gleichzeitigen
   Zugriffe, Updates oder Schreibvorgänge während der gesamten Kopie.
2. Das komplette bisherige Datenverzeichnis aus dem Docker-Volume in ein geschütztes
   Arbeitsverzeichnis übernehmen (einschließlich Unterverzeichnissen und SQLite-WALs).
3. Mit installiertem SQLCipher-Treiber in ein **neues**, nicht vorhandenes Verzeichnis
   außerhalb der Quelle kopieren:

```sh
python tools/encrypt_data.py --source /ARBEIT/alte-daten \
  --destination /SERVER/verschluesselte-daten --key-file /SICHERER-PFAD/data.key
```

Jede Datenbank wird exportiert und auf Integrität geprüft; keine Quelldatei wird
ersetzt. Unbekannte Dateien/Symlinks oder ein Fehler führen zum Abbruch und Entfernen
des neuen Ziels. Das alte Verzeichnis und vorhandene Sicherungen bleiben **Klartext**;
sie müssen nach erfolgreicher Prüfung nach deinem Sicherungskonzept geschützt oder
entfernt werden. Nicht gleichzeitig verschlüsselte und alte Installation benutzen.
Für eine neue/leere Installation ein leeres Zielverzeichnis mit UID 10001 vorbereiten.

In `.env` nur die absoluten Pfade ergänzen:

```dotenv
DATA_KEY_FILE=/SICHERER-PFAD/data.key
ENCRYPTED_DATA_DIR=/SERVER/verschluesselte-daten
```

Danach starten/aktualisieren:

```sh
./update.sh --encrypted
# oder für den ersten Start:
docker compose -f compose.yaml -f compose.encrypted.yaml up -d --build
```

Das Overlay ersetzt den `/data`-Mount durch das explizite verschlüsselte Verzeichnis;
der Schlüssel wird als Secret nur lesbar eingebunden. **Jedes weitere Update** mit
`--encrypted` starten. Das Updateskript verweigert einen versehentlichen Wechsel
auf Klartext, solange ENCRYPTED_DATA_DIR oder die lokale Markierungsdatei
`.encrypted-deployment` gesetzt sind. Diese erst nach einer geplanten Rückmigration entfernen. WAL-Daten bleiben verschlüsselt; SQLite-Temporärtabellen im
RAM. OCR sowie hoch-/heruntergeladene ZIP-Zwischendateien liegen bei aktivierter
Verschlüsselung nur im geprüften tmpfs `/tmp`. Der Container benötigt dafür den
konfigurierten RAM; zu große Vorgänge dürfen fehlschlagen statt auf Platte auszuweichen.
Host-Swap muss deaktiviert oder separat verschlüsselt sein, wenn auch ausgelagerte
RAM-Seiten geschützt werden sollen. Für Quellbetrieb `ENCRYPTED_TMPDIR` explizit
auf ein ausreichend großes tmpfs setzen; normale Festplattenpfade werden abgelehnt.

Nur den Schalter ausschalten funktioniert bei vorhandenen verschlüsselten Daten
nicht. Bei Bedarf mit derselben Offline-Kopie und zusätzlichem `--decrypt` in ein
neues Klartextziel exportieren; dies erzeugt absichtlich unverschlüsselte Dateien.
Vor einem Rollback die alte, unveränderte Installation und ihre Sicherung nutzen.
Schlüsselrotation erfordert ebenfalls einen geplanten Offline-Export; kein
automatischer Schlüsselwechsel beim App-Start.

## Grenzen und Sicherungen

Download-/Android-ZIPs sind weiterhin portable **Klartext-Exporte** und müssen nach
Download geschützt aufbewahrt werden. Auch Quellcode, `.env`, Schlüsseldateien,
Caddy-Zertifikatsmaterial und andere Host-Dateien werden durch SQLCipher nicht
verschlüsselt. Dafür Host-/Datenträgerverschlüsselung und Dateiberechtigungen nutzen.
SQLCipher schützt ruhende Datenbankdateien, nicht vor einem kompromittierten laufenden
Server mit Zugriff auf seinen Schlüssel. Keine eigene Kryptografieimplementierung.

Referenzen: [SQLCipher](https://www.zetetic.net/sqlcipher/),
[sqlcipher3](https://github.com/coleifer/sqlcipher3),
[Caddy HTTPS](https://caddyserver.com/docs/automatic-https).
