# Vermögensübersicht · 0.14.0

Unter **Vermögen** Giro-/Verrechnungskonten, Aktiendepots, Bausparverträge,
Festgeld, Tagesgeld und sonstige Guthaben anlegen. Die Web-Versionen `local` und
`server` und die native Android-App verwenden dieselben Rechenregeln und ein
gemeinsames Sicherungsformat. Alle Beträge werden in EUR geführt.

## Bestände und Umbuchungen

1. Zuerst das Girokonto mit einem bekannten Anfangsbestand und dem zugehörigen
   Datum erfassen. Ein Kontostand wird nicht aus der Ausgabenliste abgeleitet.
2. Zielanlagen mit ihren tatsächlichen Beständen anlegen. Bei Depots ist der
   Bestandswert nur das Verrechnungsguthaben; Wertpapierpositionen kommen hinzu.
3. Über **Bewegung erfassen** Geld zwischen zwei erfassten Vermögenswerten
   umbuchen. Es wird einmal abgezogen und einmal hinzugefügt. Gesamtvermögen,
   Ausgaben und Einnahmen ändern sich dadurch nicht.
4. Bereits importierte Bankbuchungen anschließend im Vermögensjournal zuordnen.
   Es entsteht dabei keine weitere Geldbewegung. Die Originalbuchung bleibt
   erhalten, zählt aber in keiner Ausgabenansicht und keinem Diagramm mit.
   Eine oder zwei passende, ungeteilte Buchungen ohne Gruppe lassen sich
   verknüpfen; zwei Buchungen müssen entgegengesetzte Vorzeichen haben.
   Zum Aufheben der Zuordnung „Keine“ wählen.

Bei einer Überweisung von 500 EUR vom Girokonto ins Tagesgeld sinkt Giro um
500 EUR und Tagesgeld steigt um 500 EUR. Dasselbe gilt für einen Sparplan oder
eine Auszahlung zurück aufs Girokonto. Geldanlagen sind keine Konsumausgaben.

Zinsen, Dividenden und Gebühren werden als eigene Vermögensbewegungen im Journal
erfasst. Sie ändern das Guthaben der betroffenen Anlage und werden dort getrennt
von Umbuchungen ausgewiesen. Keine automatische Übernahme in die Ausgaben- oder
Einnahmenbuchungen. Prognostizierte Erträge erzeugen keine tatsächlichen Buchungen.

Ein neuer Bestandswert ist eine Bestandskorrektur, keine Einzahlung. Er enthält
alle bis dahin erfassten Bewegungen am gewählten Tag; spätere Bewegungen desselben
Tages kommen hinzu. Ältere Werte bleiben gespeichert. Bewegungen vor einem neueren
Bestandswert werden abgelehnt, damit nachträgliche Umbuchungen nicht einseitig
verschwinden. Historische Korrekturen dann über passende Bestandswerte erfassen.
Bewegungen bleiben im Journal; eine falsche Überweisung durch Gegenumbuchung
korrigieren. Anlagen mit Bewegungen oder Daueraufträgen nicht löschen.

## Depotpositionen und Kurse

**Position erfassen** dient dem anfänglichen Bestand oder einer manuellen
Bestandskorrektur. **Kaufen / Verkaufen** verändert zusätzlich das
Verrechnungsguthaben. Ein Kauf tauscht Geld gegen Wertpapiere und ist keine
Ausgabe; ein Verkauf ist keine Einnahme. Handelsdatum derzeit nur heute.
Gebühren separat buchen. Stückzahlen und Kurse unterstützen sechs
Nachkommastellen; Positionswerte werden je Position auf Cent gerundet.
Keine automatische Dividendenerfassung, Split-Anpassung oder Steuerberechnung.

Optional **Kurs aktualisieren** für genau eine Position verwenden. Dazu einen
eigenen kostenlosen Alpha-Vantage-API-Schlüssel eingeben und bestätigen, dass
das Symbol in EUR notiert. Der Schlüssel wird weder im Datensatz noch in der
Sicherung gespeichert. Der Server bzw. das Android-Gerät fragt nur Symbol und
Schlüssel beim fest vorgegebenen HTTPS-Endpunkt ab. Keine Hintergrundjobs,
keine automatischen Wiederholungen, keine Premium-/Realtime-Parameter.

Der kostenlose Zugang erfordert Registrierung mit E-Mail-Adresse. Der Anbieter
nennt derzeit 25 kostenlose Abfragen pro Tag; verfügbare Symbole und Daten können
beschränkt sein. Es sind keine zugesagten Echtzeitkurse. Kursdatum und letzter
gespeicherter Wert sind sichtbar; Fehler oder ältere Anbieterwerte überschreiben
den Kurs nicht. Die Währung ist im Quote-Endpunkt nicht zuverlässig enthalten:
EUR-Notierung selbst prüfen. Andere Währungen manuell in EUR bewerten.
Ohne Schlüssel bleiben manuelle Kurse und sämtliche anderen Funktionen nutzbar.

Anbieter: [Dokumentation](https://www.alphavantage.co/documentation/#latestprice),
[kostenloser Schlüssel und Limit](https://www.alphavantage.co/support/).
Es wurde kein echter Anbieterabruf für die Implementierung ausgeführt.

## Daueraufträge und Prognosen

Monatliche, vierteljährliche, halbjährliche und jährliche Umbuchungen mit Start,
optionalem Ende und Pause erfassen. Der ursprüngliche Monatstag bleibt der
Anker: 31. Januar → 28./29. Februar → 31. März. **Fällige Termine buchen** bucht
nach Bestätigung alle noch offenen Termine bis heute. Wiederholen erzeugt keine
Duplikate. Fehlt Guthaben oder ein Anfangsbestand zum Termin, wird der gesamte
Vorgang zurückgerollt. Bankzuordnung anschließend am vorhandenen Journaleintrag
vornehmen, keine zweite Umbuchung erfassen. Gebuchte Termine bleiben erhalten,
auch wenn der Auftrag später pausiert wird. Für andere Konten oder einen anderen
Terminrhythmus einen neuen Auftrag anlegen und den alten pausieren.

Die Prognose über 1–30 Jahre beginnt mit den aktuellen Beständen. Nominale
Jahresraten werden tagweise mit ACT/365 abgegrenzt und zum Monatsende auf Cent
gerundet gutgeschrieben. Am Laufzeitende erfolgt die letzte Gutschrift;
anschließend bleibt das Guthaben unverzinst stehen. Festgeld benötigt ein Ende.
Bausparen wird als Guthaben ohne Darlehensphase, Bonus oder Prämien modelliert.

Bei Depots gilt die Renditeannahme nur für Wertpapierpositionen, nicht für das
Verrechnungsguthaben. Vorsichtiges und optimistisches Szenario verändern diese
Annahme um −2 bzw. +2 Prozentpunkte; feste Produktzinsen bleiben unverändert.
Kurswachstum wird nicht als verfügbares Bargeld behandelt. Einzahlungen ins Depot
bleiben in der Prognose Verrechnungsguthaben; sie kaufen nicht automatisch Anteile.
Nicht finanzierbare Dauerauftragstermine werden ausgelassen und gezählt.
Keine erfundenen Gehaltseingänge, Inflation, Steuern oder Transaktionskosten.
Die Modellrechnung ist keine Renditezusage oder historische Performanceanalyse.

## Daten und Sicherungen

Private und Demo-Datensätze bleiben getrennt; auf dem Server gilt weiterhin die
Benutzertrennung. Die bestehenden vollständigen ZIP-Sicherungen enthalten jetzt
auch Vermögenswerte, Positionen, Bestandswerte, Daueraufträge, Journal und
Bankzuordnungen. Sicherungen mit Vermögen tragen Formatversion 2, damit alte
App-Versionen diese nicht unbemerkt ohne Vermögensdaten wiederherstellen.
Neue Versionen lesen weiterhin alte Formatversion-1-Sicherungen; dabei wird die
Vermögensübersicht des Zieldatensatzes geleert. CSV kennzeichnet zugeordnete
Bankbuchungen als Vermögensumbuchung, ersetzt aber keine vollständige Sicherung.

## Prüfung

Automatisierte Python-Tests prüfen Cent-Rundung, Bestand am selben Tag,
Summenerhaltung, Wertpapierhandel, Monatsende, Laufzeitende, negative Renditen,
Unterdeckung, wiederholtes Buchen, Bankzuordnung, Authentifizierung/CSRF,
Datensatztrennung sowie Sicherungs-Roundtrip und alte Sicherungen. Anbieterantworten
werden simuliert. Android-Instrumentierungstests enthalten dieselben Cent-Beispiele.
Android-Build und physische Geräteabnahme sind separat erforderlich; keine
Actions, Builds, Deployments oder Emulatoren wurden gestartet.
