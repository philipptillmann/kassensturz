package de.kassensturz.app

import java.security.MessageDigest
import java.time.LocalDate
import java.time.format.DateTimeFormatter

/** Quoted CSV fields and German bank number/date conventions. */
object BankCsv {
    fun parse(text: String, delimiter: Char): List<List<String>> {
        require(text.length <= 8_000_000) { "CSV zu groß (max. 8 MB)." }
        val rows=mutableListOf<List<String>>(); var row=mutableListOf<String>(); val field=StringBuilder(); var quoted=false; var closed=false; var i=0
        while(i<text.length) {
            val c=text[i]
            if(quoted) { if(c=='"') { if(i+1<text.length && text[i+1]=='"') { field.append('"'); i++ } else { quoted=false; closed=true } } else field.append(c) }
            else when(c) {
                '"' -> { require(field.isEmpty() && !closed) { "Ungültige CSV-Anführungszeichen." }; quoted=true }
                delimiter -> { row.add(field.toString()); field.setLength(0); closed=false }
                '\n','\r' -> { row.add(field.toString()); field.setLength(0); if(row.any { it.isNotBlank() }) rows.add(row); row=mutableListOf();closed=false;if(c=='\r' && i+1<text.length && text[i+1]=='\n') i++ }
                else -> { require(!closed || c==' ' || c=='\t') { "Text nach CSV-Anführungszeichen." }; if(!closed) field.append(c) }
            }
            i++
        }
        require(!quoted) { "Nicht geschlossene CSV-Anführungszeichen." }
        if(field.isNotEmpty() || row.isNotEmpty()) { row.add(field.toString()); if(row.any { it.isNotBlank() }) rows.add(row) }
        val cleaned=rows.mapIndexed { index, columns -> if(index==0) columns.map { it.removePrefix("\uFEFF") } else columns }
        val start=cleaned.indexOfFirst { it==ingHeader }
        return if(start>=0) listOf(ingColumns)+cleaned.drop(start+1) else cleaned
    }
    fun amount(raw: String): Long {
        var s=raw.trim().replace("€", "").replace("EUR", "",true).replace("\u00a0", "").replace(" ", "")
        if(',' in s) s=s.replace(".", "")
        return Ledger.cents(s)
    }
    fun date(raw: String): String {
        val s=raw.trim()
        for(format in listOf(DateTimeFormatter.ISO_LOCAL_DATE,DateTimeFormatter.ofPattern("dd.MM.uuuu").withResolverStyle(java.time.format.ResolverStyle.STRICT))) {
            try { return LocalDate.parse(s,format).toString() } catch (_: java.time.DateTimeException) { }
        }
        throw IllegalArgumentException("Datum muss JJJJ-MM-TT oder TT.MM.JJJJ sein: $s")
    }
    fun entries(rows: List<List<String>>, dateColumn: Int, merchantColumn: Int, amountColumn: Int,
        account: String, category: String, bankSign: Boolean, ibanColumn: Int = -1, income: Boolean = false): List<Entry> {
        require(rows.size >= 2 && account.isNotBlank()) { "CSV enthält keine Daten oder Konto fehlt." }
        val indices=listOf(dateColumn,merchantColumn,amountColumn)+if(ibanColumn>=0) listOf(ibanColumn) else emptyList()
        require(indices.all { it >= 0 && it < rows.first().size }) { "Spaltenzuordnung fehlt." }
        val occurrences=mutableMapOf<String,Int>()
        return rows.drop(1).mapIndexedNotNull { index,row ->
            require(indices.all { it < row.size }) { "Zeile ${index+2}: Spalten fehlen." }
            try {
                val signed=amount(row[amountColumn]); val value=if(bankSign) -signed else signed
                if(value==0L) return@mapIndexedNotNull null
                val day=date(row[dateColumn]); val merchant=row[merchantColumn].trim().ifEmpty { "Bankbuchung" }
                val iban=if(ibanColumn>=0) row[ibanColumn].replace(Regex("\\s"),"").uppercase(java.util.Locale.ROOT) else ""
                val base=listOf(account.trim(),day,merchant,value.toString(),iban).joinToString("\u0000")
                val nth=occurrences.getOrDefault(base,0);occurrences[base]=nth+1
                val key=MessageDigest.getInstance("SHA-256").digest((base+"\u0000"+nth).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
                Entry(date=day,merchant=merchant,amount=value,category=category,payment=account.trim(),kind=if(income && value<0) "income" else "expense",counterparty=iban,importKey="csv:$key").also { Ledger.validate(it) }
            } catch(e: IllegalArgumentException) { throw IllegalArgumentException("Zeile ${index+2}: ${e.message}") }
        }
    }
    private val volksbankHeader=listOf("Bezeichnung Auftragskonto","IBAN Auftragskonto","BIC Auftragskonto","Bankname Auftragskonto","Buchungstag","Valutadatum","Name Zahlungsbeteiligter","IBAN Zahlungsbeteiligter","BIC (SWIFT-Code) Zahlungsbeteiligter","Buchungstext","Verwendungszweck","Betrag","Waehrung","Saldo nach Buchung","Bemerkung","Gekennzeichneter Umsatz","Glaeubiger ID","Mandatsreferenz")
    fun isVolksbank(rows:List<List<String>>) = rows.firstOrNull()==volksbankHeader
    private fun iban(value:String)=value.replace(Regex("\\s+"),"").uppercase(java.util.Locale.ROOT)
    fun volksbankAccounts(rows:List<List<String>>):List<String> {
        require(isVolksbank(rows) && rows.drop(1).all { it.size==volksbankHeader.size }) { "Volksbank: Unerwartete Spaltenanzahl." }
        return rows.drop(1).map { iban(it[1]) }.distinct().sorted().also { accounts -> require(accounts.isNotEmpty() && accounts.all { it.isNotEmpty() && it.length<=34 }) { "Volksbank: IBAN Auftragskonto fehlt oder ist zu lang." } }
    }
    fun volksbank(rows:List<List<String>>,account:String,category:String,sourceAccount:String=""):ProviderImport {
        require(account.isNotBlank()) { "Für Volksbank bitte ein Zahlungsmittel auswählen." }
        val accounts=volksbankAccounts(rows)
        val source=iban(sourceAccount).ifEmpty { if(accounts.size==1) accounts.single() else "" }
        require(source in accounts) { "Volksbank: Genau ein Quellkonto aus der CSV auswählen." }
        val entries=mutableListOf<Entry>();val excluded=mutableListOf<String>();val occurrences=mutableMapOf<String,Int>()
        rows.drop(1).forEachIndexed { index,row ->
            val r=volksbankHeader.zip(row).toMap()
            fun cell(name:String)=r.getValue(name).trim()
            val own=iban(cell("IBAN Auftragskonto"))
            if(own!=source) excluded.add("Zeile ${index+2}: Anderes Quellkonto (nicht ausgewählt)")
            else try {
                require(cell("Waehrung")=="EUR") { "Nur EUR wird unterstützt." }
                val day=date(cell("Buchungstag"));val valueDay=date(cell("Valutadatum"));val value= -amount(cell("Betrag"))
                if(value==0L) excluded.add("Zeile ${index+2}: Nullbetrag")
                else {
                    val merchant=cell("Name Zahlungsbeteiligter").ifEmpty { cell("Verwendungszweck") }.ifEmpty { cell("Buchungstext") }
                    val counterparty=iban(cell("IBAN Zahlungsbeteiligter"));require(counterparty.length<=34) { "Gegenkonto zu lang." }
                    val notes=listOf("Buchungstext","Verwendungszweck","Bemerkung","Glaeubiger ID","Mandatsreferenz").map { cell(it) }.filter { it.isNotEmpty() }.joinToString("\n")
                    val base=listOf("volksbank",account.trim(),own,day,valueDay,merchant,counterparty,cell("Buchungstext"),cell("Verwendungszweck"),cell("Glaeubiger ID"),cell("Mandatsreferenz"),value.toString(),"EUR").joinToString("\u0000")
                    val nth=occurrences.getOrDefault(base,0)+1;occurrences[base]=nth
                    val key=MessageDigest.getInstance("SHA-256").digest((base+"\u0000"+nth).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
                    entries.add(Entry(date=day,merchant=merchant,amount=value,category=category,payment=account.trim(),kind="expense",notes=notes,counterparty=counterparty,importKey="vb:$key").also { Ledger.validate(it) })
                }
            } catch(e:IllegalArgumentException) { throw IllegalArgumentException("Volksbank-Zeile ${index+2}: ${e.message}") }
        }
        return ProviderImport(entries,excluded)
    }
    private val ingHeader=listOf("Buchung","Wertstellungsdatum","Auftraggeber/Empfänger","Buchungstext","Verwendungszweck","Referenz","Saldo","Währung","Betrag","Währung")
    private val ingColumns=ingHeader.dropLast(1)+"Betragswährung"
    fun isIng(rows: List<List<String>>) = rows.firstOrNull()==ingColumns
    fun ing(rows: List<List<String>>, account:String, category:String): ProviderImport {
        require(isIng(rows) && account.isNotBlank()) { "ING: Konto oder Spalten fehlen." }
        val entries=mutableListOf<Entry>();val excluded=mutableListOf<String>();val occurrences=mutableMapOf<String,Int>()
        rows.drop(1).forEachIndexed { index,row ->
            require(row.size==ingColumns.size) { "ING-Buchungszeile ${index+2}: Spalten fehlen." }
            try {
                val r=ingColumns.zip(row).toMap()
                fun cell(name:String)=r.getValue(name).trim()
                require(cell("Währung")=="EUR" && cell("Betragswährung")=="EUR") { "ING: Nur EUR wird unterstützt." }
                val day=date(cell("Buchung"));val valueDay=date(cell("Wertstellungsdatum"));val value= -amount(cell("Betrag"))
                if(value==0L) excluded.add("Buchungszeile ${index+2}: Nullbetrag")
                else {
                    val merchant=cell("Auftraggeber/Empfänger").ifEmpty { cell("Verwendungszweck") }.ifEmpty { cell("Buchungstext") }
                    val notes=listOf("Buchungstext","Verwendungszweck","Referenz").map { cell(it) }.filter { it.isNotEmpty() }.joinToString("\n")
                    val base=listOf("ing",account.trim(),day,valueDay,merchant,cell("Buchungstext"),cell("Verwendungszweck"),cell("Referenz"),value.toString(),"EUR").joinToString("\u0000")
                    val nth=occurrences.getOrDefault(base,0)+1;occurrences[base]=nth
                    val key=MessageDigest.getInstance("SHA-256").digest((base+"\u0000"+nth).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
                    entries.add(Entry(date=day,merchant=merchant,amount=value,category=category,payment=account.trim(),kind=if(value<0 && cell("Buchungstext")=="Gehalt/Rente") "income" else "expense",notes=notes,importKey="ing:$key").also { Ledger.validate(it) })
                }
            } catch(e: IllegalArgumentException) { throw IllegalArgumentException("ING-Buchungszeile ${index+2}: ${e.message}") }
        }
        return ProviderImport(entries,excluded)
    }
    private val trHeaders=setOf("datetime","date","account_type","category","type","name","amount","currency","transaction_id","counterparty_iban","description","asset_class")
    private val trTypes=setOf("CARD_TRANSACTION","TRANSFER_INSTANT_OUTBOUND","TRANSFER_INSTANT_INBOUND","TRANSFER_OUTBOUND","TRANSFER_INBOUND")
    fun isTradeRepublic(rows: List<List<String>>) = rows.isNotEmpty() && rows.first().containsAll(trHeaders)
    data class ProviderImport(val entries: List<Entry>, val excluded: List<String>)
    fun tradeRepublic(rows: List<List<String>>, account: String, category: String): ProviderImport {
        require(isTradeRepublic(rows) && account.isNotBlank()) { "Trade Republic: Konto oder Spalten fehlen." }
        val entries=mutableListOf<Entry>();val excluded=mutableListOf<String>()
        rows.drop(1).forEachIndexed { index,row ->
            require(row.size==rows.first().size) { "Zeile ${index+2}: Spalten fehlen." }
            val r=rows.first().zip(row).toMap()
            fun cell(name:String)=r.getValue(name)
            val type=cell("type")
            if(cell("category")!="CASH" || type !in trTypes || cell("asset_class").isNotBlank()) {
                excluded.add("Zeile ${index+2}: $type (Nicht unterstützte Buchungsart / Anlagebuchung)")
            } else {
                try {
                    require(cell("currency")=="EUR") { "Nur EUR wird unterstützt." }
                    require(cell("transaction_id").isNotBlank()) { "Transaktions-ID fehlt." }
                    val value=amount(cell("amount"))
                    if(value==0L) excluded.add("Zeile ${index+2}: $type (Nullbetrag)")
                    else {
                        val merchant=cell("name").trim().ifEmpty { r["counterparty_name"].orEmpty().trim() }.ifEmpty { cell("description").trim() }
                        val base=listOf("trade-republic",account.trim(),cell("account_type").trim(),cell("transaction_id").trim()).joinToString("\u0000")
                        val key=MessageDigest.getInstance("SHA-256").digest(base.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
                        entries.add(Entry(date=date(cell("date")),merchant=merchant,amount=-value,category=category,payment=account.trim(),kind="expense",counterparty=cell("counterparty_iban").replace(Regex("\\s+"),"").uppercase(java.util.Locale.ROOT),importKey="tr:$key").also { Ledger.validate(it) })
                    }
                } catch(e: IllegalArgumentException) { throw IllegalArgumentException("Zeile ${index+2}: ${e.message}") }
            }
        }
        return ProviderImport(entries,excluded)
    }
    fun export(entries: List<Entry>): String {
        fun cell(value: String) = "\""+value.replace("\"","\"\"")+"\""
        val header=listOf("Datum","Bezeichnung","Betrag","Kategorie","Zahlungsmittel","Art","Gruppe","Notizen","Position","Positionsbetrag","Positionskategorie","Positionsgruppe")
        return "\uFEFF"+(listOf(header)+entries.flatMap { e ->
            val base=listOf(e.date,e.merchant,java.math.BigDecimal(e.amount).movePointLeft(2).toPlainString().replace('.',','),e.category,e.payment,e.kind,e.group,e.notes)
            if(e.parts.isEmpty()) listOf(base+listOf("","","","")) else e.parts.map { p -> base+listOf(p.name,java.math.BigDecimal(p.amount).movePointLeft(2).toPlainString().replace('.',','),p.category,p.group ?: "(geerbt)") }
        }).joinToString("\r\n") { row -> row.joinToString(";") { cell(it) } }
    }
}
