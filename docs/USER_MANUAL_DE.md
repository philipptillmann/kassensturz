# Kassensturz Benutzerhandbuch

Version 1.2.0 · Deutsch

## Einstieg

Kassensturz erfasst Ausgaben, Erstattungen und Einnahmen in EUR. Die Server-Version läuft im Browser, auch als Startbildschirm-App auf dem iPhone. Local läuft auf deinem Rechner. Android speichert seine eigenen Daten auf dem Gerät und arbeitet unabhängig. Zwischen diesen Installationen findet keine automatische Synchronisation statt.

Melde dich auf einem gemeinsam genutzten Server mit deinem eigenen Konto an. Bei der Umstellung einer alten Installation mit gemeinsamem Passwort übernimmt das erste persönliche Konto die bisherigen privaten Daten und wird Administrator. Weitere Benutzer erhalten getrennte Daten. Administratoren können unter Einstellungen Benutzer anlegen. Eine gespeicherte Anmeldung reduziert erneute Anmeldungen; ein Passwortwechsel macht vorhandene Kurzbefehl-Schlüssel ungültig.

Über die Datensatzauswahl wechselst du zwischen Privat und Demo. Demo dient zum Ausprobieren und bleibt von privaten Einträgen getrennt. Prüfe vor jedem Import und jeder Wiederherstellung den ausgewählten Datensatz.

## Sprache und Hilfe

Wähle unter Einstellungen Deutsch oder English. Android bietet dort einen Sprachwechsel an. Die Auswahl wird in diesem Browser beziehungsweise dieser Android-Installation gespeichert und gilt nicht automatisch auf anderen Geräten. Dort öffnest du auch dieses Benutzerhandbuch; unter Android ist es offline enthalten.

Der Sprachwechsel betrifft die Oberfläche und Anzeigeformate. Gespeicherte Kategorien, Zahlungsmittel, Händler, Notizen und Banktexte werden nicht umbenannt. Sie bleiben bearbeitbare Benutzerdaten. Beträge bleiben EUR; die Sprache ändert keine Währung. CSV-Spalten und API-Feldnamen bleiben unverändert.

## Buchungen anlegen und bearbeiten

Wähle Neue Buchung oder die Bargeld-Schnellwahl auf der Übersicht. Letztere setzt das Zahlungsmittel auf Bar. Trage Datum, Händler oder Beschreibung, Betrag, Kategorie und Zahlungsmittel ein. Ergänze bei Bedarf Notizen. Öffne einen Eintrag zum Bearbeiten oder Löschen.

Eine Ausgabe erhöht die Kosten. Eine Erstattung oder der Beitrag einer anderen Person reduziert sie: Verwende im Web einen negativen Ausgabenbetrag, gegebenenfalls über die +/−-Taste. Android bietet den Buchungstyp Erstattung / Beitrag mit einem positiven Betragsfeld. Für Gehalt, Geschenke und andere Einnahmen verwendest du den Typ Einnahme. Einnahmen werden getrennt von Ausgaben ausgewiesen; verwende sie nicht für die Erstattung eines Einkaufs.

Unter Einstellungen lassen sich Kategorien anlegen und umbenennen. Eine Umbenennung aktualisiert auch vorhandene Buchungen und Rechnungspositionen mit dieser Kategorie. Zahlungsmittel können Bargeld, Bankkonto oder PayPal / Sonstiges sein. Gib jedem Konto einen eindeutigen Namen. Für Bankkonten gibt es eine optionale IBAN und deinen prozentualen Anteil; wähle auch, ob dieser für eingehende Beträge gilt. Anteile wirken in der effektiven Ansicht, nicht auf den erfassten Bankbetrag. Prüfe nach Änderungen auch historische Einträge.

## Gruppen, Rechnungspositionen und effektive Kosten

Gib einem Einkauf und den zugehörigen Erstattungen denselben Gruppennamen. Alle Buchungen bleiben einzeln sichtbar. Wechsle die Monatsansicht zwischen allen Buchungen und effektiven Kosten, um die verbleibenden Gruppenkosten zu sehen. Jede Buchung zählt in ihrem eigenen Monat, auch wenn jemand später zahlt. Für die effektive Auswertung wird die Kategorie des Einkaufs verwendet.

Teile eine Rechnung in Positionen auf, wenn nur ein Teil zu einer Gruppe gehört. Jede Position kann die Gruppe der Buchung übernehmen, eine eigene Gruppe haben oder ohne Gruppe bleiben. Prüfe, dass die Positionsbeträge zur Rechnungssumme passen. Verwende unterschiedliche Positionskategorien für gemischte Einkäufe.

Bei einer Erstattung oder einem Beitrag kannst du den vereinbarten Beitrag getrennt vom tatsächlich erhaltenen Betrag erfassen. Bei einem Einkauf über 60 €, vereinbarten 30 € und tatsächlich erhaltenen 35 € betragen deine effektiven Kosten 25 €. Der Eintrag zeigt zusätzlich die Überzahlung von 5 € und den vereinbarten Anteil. Er ersetzt nicht den tatsächlichen Zahlungseingang und erzeugt keine automatische Schuld oder Rückzahlung. Ergänze eine Notiz zur Verwechslung. Prüfe Vorschläge aus der Belegerkennung: Eine Rechnung belegt nicht, wie viel Geld tatsächlich eingegangen ist.

Umbuchungen zwischen eigenen Bankkonten bestehen aus zwei Gegenbuchungen. Die Erkennung nutzt Kontoinformationen, Datum und Betrag zurückhaltend. Prüfe Vorschläge und bestätige oder ordne sie bei Bedarf selbst zu. Bestätigte Umbuchungen verschwinden in der effektiven Ansicht, auch über Monatsgrenzen hinweg. Die Originalbuchungen bleiben erhalten. Bei Gemeinschaftskonten wirkt dein Anteil in der effektiven Ansicht; für eine hälftige Aufteilung stellst du 50 % ein.

## Belege

Scanne oder lade ein Bild hoch und prüfe Händler, Datum, Summe und Positionen vor dem Speichern. Die Texterkennung kann Fehler machen. Das gespeicherte Belegbild wird in ein komprimiertes, weiterhin lesbares JPEG umgewandelt; es ist keine unveränderte Kopie der hochgeladenen Originaldatei. Der Server unterstützt HEIC-Konvertierung. Unter Android hängt HEIC-Unterstützung vom Bilddecoder des Geräts ab. Bewahre das Original separat auf, wenn du die unveränderte Datei benötigst.

Ein gespeicherter Beleg bleibt mit der Buchung verbunden und ist in der vollständigen ZIP-Sicherung enthalten. Prüfe das Bild nach dem Speichern. Beim Löschen einer Buchung oder Ersetzen ihres Bildes wird das bisherige zugehörige Bild entsprechend entfernt. CSV-Exporte enthalten keine Belegbilder.

## Bank-CSV importieren und rückgängig machen

Wähle unter Einstellungen eine CSV-Datei und das Zahlungsmittel beziehungsweise Konto für diesen Import. Prüfe erkanntes Format, Datums-, Beschreibungs- und Betragsspalte, Vorzeichen, Gegenkonto-Spalte und Vorschau. Negative Bankabbuchungen werden zu Ausgaben, Gutschriften zu eingehenden Beträgen. Unterstützt wird nur EUR. Übliche UTF-8- und Windows-1252-Dateien werden unterstützt.

Trade Republic unterstützt alltägliche Kartenzahlungen und Überweisungen. Anlagebezogene Zeilen wie BUY, INTEREST_PAYMENT, DIVIDEND und BENEFITS_SAVEBACK werden derzeit ausgeschlossen und im Ergebnis aufgelistet. ING unterstützt den Vorspann und die Buchungs-/Valutadatum-Struktur des Auszugs; wähle den Buchungsbetrag, nicht den Kontostand. Volksbank-Dateien können mehrere Quellkonten enthalten: Wähle das gewünschte Konto und importiere weitere Konten separat. Gegenkonto-Informationen helfen bei der Umbuchungserkennung.

Prüfe ausgeschlossene Zeilen, Anzahl importierter Einträge und Duplikatwarnungen. Die Duplikaterkennung gilt pro ausgewähltem Konto und verwendet Quellkennungen oder berücksichtigt wiederholte Vorkommen. Bei einem erneuten Import über eine andere generische Zuordnung können andere Kennungen entstehen. Verlasse dich deshalb nicht ungeprüft auf die Erkennung früherer Importe.

Mit Letzten CSV-Import rückgängig machen entfernst du die Einträge des zuletzt erfolgreich ausgeführten Imports im aktuellen Datensatz. Übersprungene Duplikate und fehlgeschlagene Importe ersetzen diesen Rückgängig-Eintrag nicht. Spätere Änderungen und Belege der entfernten Buchungen gehen ebenfalls verloren. Ältere Importe vor Einführung der Funktion lassen sich so nicht zurücknehmen. Mit Vermögensvorgängen verknüpfte Einträge müssen zuerst gelöst werden. Es gibt kein automatisches Wiederholen; bewahre die CSV auf und erstelle bei Unsicherheit zuerst eine Sicherung.

## Auswertungen

Übersicht und Diagramme zeigen Monatssummen, Entwicklungen und Kategorien. Wähle Monat und normale oder effektive Ansicht. Einnahmen bleiben getrennt. Die effektive Ansicht verrechnet gruppierte Einkäufe und Erstattungen, berücksichtigt Kontoanteile und blendet bestätigte interne Umbuchungen aus. Mit Vermögensvorgängen verknüpfte Bankbuchungen werden aus Ausgabenauswertungen ausgeschlossen, damit sie nicht doppelt zählen. Prüfe zur Abstimmung neben Diagrammen auch die einzelnen Buchungen.

## Vermögen

Lege Produkte für Bargeld, Depot, Bausparen, Festgeld, Sparen und sonstige Bestände an. Erfasse datierte Bestandswerte: Kontostände werden nicht aus der Ausgabenliste berechnet. Umbuchungen zwischen Produkten sind getrennte Vorgänge und weder Einnahmen noch Ausgaben.

Für Depotpositionen erfasst du Käufe, Verkäufe, Stückzahlen und Kurse. Käufe benötigen ausreichendes Produktguthaben. Tatsächliche Zinsen, Dividenden und Gebühren sind eigene Vorgänge. Regelmäßige Anweisungen zeigen fällige Termine zunächst als Vorschau; bestätige sie vor der Buchung. Monatsenden werden berücksichtigt, bereits verarbeitete Termine nicht doppelt gebucht. Eine nicht finanzierbare Serie wird abgelehnt statt teilweise ausgeführt.

Verknüpfe eine importierte Bankbuchung mit dem passenden Vermögensvorgang, um Doppelbuchungen zu vermeiden. Verknüpfte Bankeinträge erscheinen in keiner der beiden Ausgabenansichten. Prüfe und löse Verknüpfungen vor dem Löschen oder Rückgängigmachen betroffener Importe.

Optionale Kursabfragen benötigen einen ausdrücklichen Aufruf, einen eigenen kostenlosen API-Schlüssel und die Bestätigung von EUR-Kursen. Es gibt keine automatische Abfrage. Bei Fehlern bleiben vorhandene Werte bestehen. Prognosen sind Szenarien aus eingegebenen Beständen, Zinsen und Anweisungen; sie garantieren keine Rendite und bilden nicht automatisch alle Steuern, Gebühren oder Inflationseffekte ab.

## Sicherungen und Datenübertragung

Die vollständige ZIP-Sicherung enthält den ausgewählten Datensatz mit Buchungen, Einstellungen, Belegbildern und unterstützten Vermögensdaten. Server-Passwörter, andere Benutzer und sämtliche Installationsvorlieben sind nicht enthalten. Ein normaler CSV-Export ist nur eine Buchungstabelle und keine vollständige Sicherung.

Bewahre private Sicherungen außerhalb von GitHub auf. Portable ZIP-Dateien enthalten unverschlüsselte Finanzdaten, auch bei verschlüsselter Server-Datenbank. Speichere sie sicher und halte getrennte Kopien vor. Eine Wiederherstellung prüft das Archiv und ersetzt nach Bestätigung den ausgewählten Datensatz einschließlich bisheriger Belege und Rückgängig-Historie. Prüfe vorher den Datensatz.

Die Sicherungsformate 1 und 2 decken ältere Daten ab; vereinbarte Beiträge benötigen Format 3. Ältere App-Versionen können neue Formate ablehnen. Aktualisiere das Ziel vor dem Wiederherstellen und sichere Daten vor Tests zwischen Installationen. Android und Server sind unabhängig; Server-Importhistorie bleibt nicht bei jeder Übertragung über Android-Sicherungen erhalten.

## iPhone-Kurzbefehle-API — nur Server

Erstelle unter Einstellungen einen Kurzbefehl-Schlüssel für dein Konto und einen festen Datensatz. Kopiere ihn sofort; vollständig wird er nur einmal angezeigt. Halte ihn geheim. Verwende HTTPS und übertrage ihn im Authorization: Bearer-Header. Widerruf oder Passwortwechsel machen ihn ungültig.

Über /json-options erhältst du aktuelle Kategorien, Banken und Zahlungsmittel. An /json-import sendest du neue Einträge mit date, merchant und amount sowie passenden optionalen Feldern wie category, payment_method, kind, group_name, notes oder expected_contribution. Maßgeblich für genaue Feldwerte und Betragskonventionen ist die aktuelle API-Dokumentation. Verwende für sichere Wiederholungen eine gleichbleibende Anfragekennung und für tatsächlich getrennte identische Einkäufe unterschiedliche Kennungen. Schlüssel erlauben weder den Abruf der gesamten Buchungshistorie noch Änderungen bestehender Einträge.

## Serversicherheit und Fehlerbehebung

Der Server verwendet standardmäßig HTTPS. Für ein privates LAN-Zertifikat müssen die Geräte der lokalen Zertifizierungsstelle vertrauen. Der nur an Loopback gebundene Local-Entwicklungsstarter ist eine separate Einrichtung. Bewahre gewählten Port und Zugangsdaten in der lokalen Umgebungskonfiguration außerhalb von Git auf.

Die optionale Datenbankverschlüsselung ist standardmäßig aus und benötigt die dokumentierte SQLCipher-Einrichtung sowie einen sicher gesicherten Schlüssel. Ohne diesen Schlüssel können Daten unwiederbringlich verloren sein. Datenbankverschlüsselung verschlüsselt keine portablen Exporte und entfernt nicht automatisch alte Klartextkopien. Lies vor einer Migration die Server-Sicherheits- und Installationsanleitung. Android nutzt seinen App-Speicher und die Gerätesicherheit; eine zusätzliche verschlüsselte Datenbank wird damit nicht zugesichert.

Wenn ein Import oder eine Wiederherstellung falsch aussieht, halte an und erstelle vor weiteren Änderungen eine Sicherung. Prüfe Datensatz, Konto, Zeitraum, Vorzeichen und effektive Ansicht. Korrigiere OCR-Fehler vor dem Speichern. Prüfe bei Anmelde- oder HTTPS-Problemen Hostname, Port und Zertifikatsvertrauen. Melde Fehler mit erfundenen Beispielen und ohne Belege, Kontonummern, private Serveradressen oder API-Schlüssel. Android wird auf einem echten Gerät abgenommen; für die Nutzung des Servers ist kein automatischer Cloud-Build erforderlich.
