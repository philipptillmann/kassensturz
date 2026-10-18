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
        return rows.mapIndexed { index, columns -> if(index==0) columns.map { it.removePrefix("\uFEFF") } else columns }
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
    private val trHeaders=setOf("datetime","date","account_type","category","type","name","amount","currency","transaction_id","counterparty_iban","description","asset_class")
    private val trTypes=setOf("CARD_TRANSACTION","TRANSFER_INSTANT_OUTBOUND","TRANSFER_INSTANT_INBOUND","TRANSFER_OUTBOUND","TRANSFER_INBOUND")
    fun isTradeRepublic(rows: List<List<String>>) = rows.isNotEmpty() && rows.first().containsAll(trHeaders)
    data class TradeRepublicImport(val entries: List<Entry>, val excluded: List<String>)
    fun tradeRepublic(rows: List<List<String>>, account: String, category: String): TradeRepublicImport {
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
        return TradeRepublicImport(entries,excluded)
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
