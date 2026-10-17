# Android-App installieren

Voraussetzung: Android 9 oder neuer. Die App speichert ihre Daten auf dem Telefon
und funktioniert auch im Flugmodus.

## APK herunterladen

1. Auf GitHub [Actions → Android standalone](https://github.com/philipptillmann/kassensturz/actions/workflows/android.yml) öffnen und gegebenenfalls anmelden.
2. Den neuesten erfolgreichen Lauf für den Branch **android-standalone** öffnen.
3. Unter **Artifacts** die Datei **kassensturz-android-debug** herunterladen.
4. Das ZIP entpacken. Darin liegt **app-debug.apk**.

## Auf dem Telefon installieren

1. Die APK auf das Telefon übertragen oder dort herunterladen.
2. In der Dateien-App **app-debug.apk** antippen.
3. Falls Android fragt, für diese Dateien-App bzw. den Browser **Apps aus dieser Quelle installieren** erlauben.
4. **Installieren** wählen und anschließend **Kassensturz** öffnen.

Es wird keine Serveradresse und kein Serverpasswort benötigt. Oben rechts
zwischen **Privat** und **Demo** wechseln. **Demo** enthält Beispieldaten;
**Privat** beginnt leer. Über **+ Buchung** den ersten eigenen Eintrag anlegen.

## Daten sichern und Updates installieren

Unter **Mehr → Vollständige Sicherung erstellen** eine ZIP-Datei außerhalb der
App speichern. Sie enthält den ausgewählten Datensatz einschließlich Belegen.
Privat und Demo werden getrennt gesichert.

Eine neue APK über die vorhandene App installieren. Bei gleicher Signatur bleiben
die Daten erhalten. Die aktuellen APKs sind Testversionen mit Debug-Signatur.
Falls Android wegen einer abweichenden Signatur ein Update ablehnt, zuerst mit
der noch installierten App sichern. Eine Deinstallation löscht lokale Daten;
nach einer Neuinstallation die Sicherung über **Mehr → Sicherung wiederherstellen**
einlesen. Eine dauerhafte Release-Signatur wird vor einer regulären Veröffentlichung eingerichtet.

## Bisherige Serverdaten übernehmen

Die Anleitung und das Exportkommando stehen im Abschnitt
[Move one existing server account to Android](README.md#move-one-existing-server-account-to-android).
Der Export wählt genau einen Benutzer aus und erzeugt eine ZIP-Datei mit dessen
Finanzdaten und Belegen. Die ZIP auf das Telefon übertragen und in **Privat**
unter **Mehr → Sicherung wiederherstellen** auswählen. Dieser Vorgang ersetzt
den ausgewählten lokalen Datensatz; vorher vorhandene lokale Daten sichern.
Anschließend Beträge, Gruppen und Belege prüfen. Server und Android-App arbeiten
danach unabhängig; es gibt keine automatische Synchronisierung.

## Belege

In einer Buchung **Beleg fotografieren** oder **Belegfoto auswählen** wählen.
Das Foto wird als komprimiertes JPEG mit der Buchung gespeichert.
**Text aus Beleg lesen** erkennt Text lokal. Ergebnis prüfen und in die Notizen
übernehmen; ein erkannter Gesamtbetrag kann optional übernommen werden.
HEIC-Unterstützung hängt vom Bilddecoder des Android-Geräts ab.
