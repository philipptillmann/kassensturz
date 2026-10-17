package de.kassensturz.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream
import java.time.LocalDate
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

private fun values(vararg pairs: Pair<String, Any?>) = ContentValues().apply { pairs.forEach { (key, value) ->
    when (value) { null -> putNull(key); is String -> put(key,value); is Long -> put(key,value); is Int -> put(key,value); is ByteArray -> put(key,value); else -> error("Unsupported value") }
} }
private fun JSONObject.exactLong(key: String): Long {
    val raw=get(key).toString()
    require(Regex("-?[0-9]+").matches(raw)) { "Ungültiger ganzzahliger Wert: $key" }
    return raw.toLong()
}
private fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }
private fun JSONArray.strings() = (0 until length()).map { getString(it) }

data class Snapshot(val entries: List<Entry>, val categories: List<String>, val payments: List<String>, val accounts: List<Account>, val transfers: List<Transfer>, val ignored: List<Transfer> = emptyList())

class Store(context: Context, val demo: Boolean) : SQLiteOpenHelper(context, if (demo) "demo.sqlite3" else "private.sqlite3", null, 1) {
    override fun onConfigure(db: SQLiteDatabase) { db.setForeignKeyConstraintsEnabled(true) }
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE categories(name TEXT PRIMARY KEY NOT NULL)")
        db.execSQL("CREATE TABLE payments(name TEXT PRIMARY KEY NOT NULL)")
        db.execSQL("CREATE TABLE entries(id INTEGER PRIMARY KEY AUTOINCREMENT,date TEXT NOT NULL,merchant TEXT NOT NULL,amount INTEGER NOT NULL,category TEXT NOT NULL REFERENCES categories(name) ON UPDATE CASCADE,payment TEXT NOT NULL,kind TEXT NOT NULL,notes TEXT NOT NULL,group_name TEXT NOT NULL,parts TEXT NOT NULL,counterparty TEXT NOT NULL,import_key TEXT UNIQUE)")
        db.execSQL("CREATE TABLE receipts(entry_id INTEGER PRIMARY KEY REFERENCES entries(id) ON DELETE CASCADE,image BLOB NOT NULL)")
        db.execSQL("CREATE TABLE accounts(name TEXT PRIMARY KEY REFERENCES payments(name),share INTEGER NOT NULL,share_income INTEGER NOT NULL,iban TEXT NOT NULL)")
        db.execSQL("CREATE TABLE transfers(outgoing INTEGER PRIMARY KEY REFERENCES entries(id) ON DELETE CASCADE,incoming INTEGER UNIQUE REFERENCES entries(id) ON DELETE CASCADE)")
        db.execSQL("CREATE TABLE ignored(outgoing INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,incoming INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,PRIMARY KEY(outgoing,incoming))")
        listOf("Unkategorisiert","Lebensmittel","Wohnen","Mobilität","Freizeit","Shopping","Gesundheit","Gehalt","Geschenke","Sonstige Einnahmen").forEach { db.insertOrThrow("categories",null,values("name" to it)) }
        listOf("Bar","PayPal","Bankkarte").forEach { db.insertOrThrow("payments",null,values("name" to it)) }
        if (demo) seed(db)
    }
    override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) { error("Unbekannte Datenbankversion $old → $new") }
    private fun partsJson(parts: List<Part>) = JSONArray().apply { parts.forEach { p -> put(JSONObject().put("name",p.name).put("amount",p.amount).put("category",p.category).put("group",p.group ?: JSONObject.NULL)) } }.toString()
    private fun parseParts(raw: String) = JSONArray(raw).objects().map { Part(it.getString("name"),it.exactLong("amount"),it.getString("category"),if (it.isNull("group")) null else it.getString("group")) }
    private fun putEntry(db: SQLiteDatabase, e: Entry): Long {
        Ledger.validate(e)
        require(db.rawQuery("SELECT 1 FROM categories WHERE name=?",arrayOf(e.category)).use { it.moveToFirst() }) { "Kategorie existiert nicht." }
        e.parts.forEach { p -> require(db.rawQuery("SELECT 1 FROM categories WHERE name=?",arrayOf(p.category)).use { it.moveToFirst() }) { "Positionskategorie existiert nicht." } }
        if (e.payment.isNotEmpty()) db.insertWithOnConflict("payments",null,values("name" to e.payment),SQLiteDatabase.CONFLICT_IGNORE)
        val v = values("date" to e.date,"merchant" to e.merchant.trim(),"amount" to e.amount,"category" to e.category,"payment" to e.payment,"kind" to e.kind,"notes" to e.notes,"group_name" to e.group.trim(),"parts" to partsJson(e.parts),"counterparty" to e.counterparty,"import_key" to e.importKey)
        return if (e.id == 0L) db.insertOrThrow("entries",null,v) else { require(db.update("entries",v,"id=?",arrayOf(e.id.toString())) == 1) { "Buchung nicht gefunden." }; e.id }
    }
    fun save(e: Entry, receipt: ByteArray? = null, removeReceipt: Boolean = false): Long = transaction { db ->
        val id = putEntry(db,e)
        // Editing either leg invalidates an earlier manual transfer pairing.
        db.delete("transfers","outgoing=? OR incoming=?",arrayOf(id.toString(),id.toString()))
        if (removeReceipt) db.delete("receipts","entry_id=?",arrayOf(id.toString()))
        if (receipt != null) {
            require(receipt.size <= 4_000_000 && receipt.size > 2 && receipt[0] == 0xff.toByte() && receipt[1] == 0xd8.toByte()) { "Ungültiges JPEG." }
            db.insertWithOnConflict("receipts",null,values("entry_id" to id,"image" to receipt),SQLiteDatabase.CONFLICT_REPLACE)
        }
        reconcile()
        id
    }
    fun delete(id: Long) { writableDatabase.delete("entries","id=?",arrayOf(id.toString())) }
    fun receipt(id: Long): ByteArray? = readableDatabase.rawQuery("SELECT image FROM receipts WHERE entry_id=?",arrayOf(id.toString())).use { if (it.moveToFirst()) it.getBlob(0) else null }
    fun snapshot(): Snapshot {
        val db = readableDatabase
        val entries = db.rawQuery("SELECT e.*,EXISTS(SELECT 1 FROM receipts WHERE entry_id=e.id) AS has_receipt FROM entries e ORDER BY date DESC,id DESC",null).use { c ->
            buildList { while (c.moveToNext()) {
                fun s(key: String) = c.getString(c.getColumnIndexOrThrow(key))
                add(Entry(c.getLong(0),s("date"),s("merchant"),c.getLong(c.getColumnIndexOrThrow("amount")),s("category"),s("payment"),s("kind"),s("notes"),s("group_name"),parseParts(s("parts")),c.getInt(c.getColumnIndexOrThrow("has_receipt")) == 1,s("counterparty"),c.getColumnIndexOrThrow("import_key").let { if (c.isNull(it)) null else c.getString(it) }))
            } }
        }
        fun names(table: String) = db.rawQuery("SELECT name FROM $table ORDER BY name COLLATE NOCASE",null).use { c -> buildList { while(c.moveToNext()) add(c.getString(0)) } }
        val accounts = db.rawQuery("SELECT * FROM accounts ORDER BY name",null).use { c -> buildList { while(c.moveToNext()) add(Account(c.getString(0),c.getInt(1),c.getInt(2)==1,c.getString(3))) } }
        val transfers = db.rawQuery("SELECT * FROM transfers",null).use { c -> buildList { while(c.moveToNext()) add(Transfer(c.getLong(0),c.getLong(1))) } }
        val ignored=db.rawQuery("SELECT * FROM ignored",null).use { c -> buildList { while(c.moveToNext()) add(Transfer(c.getLong(0),c.getLong(1))) } }
        return Snapshot(entries,names("categories"),names("payments"),accounts,transfers,ignored)
    }
    fun addName(name: String, category: Boolean) {
        val cleaned = name.trim(); require(cleaned.isNotEmpty() && cleaned.length <= 60) { "Name: 1–60 Zeichen." }
        writableDatabase.insertOrThrow(if(category) "categories" else "payments",null,values("name" to cleaned))
    }
    fun renameCategory(old: String, name: String) = transaction { db ->
        val cleaned = name.trim(); require(cleaned.isNotEmpty() && cleaned.length <= 60) { "Name: 1–60 Zeichen." }
        require(db.update("categories",values("name" to cleaned),"name=?",arrayOf(old))==1) { "Kategorie fehlt." }
        db.rawQuery("SELECT id,parts FROM entries",null).use { c -> while(c.moveToNext()) {
            val parts = parseParts(c.getString(1)).map { if(it.category == old) it.copy(category=cleaned) else it }
            db.update("entries",values("parts" to partsJson(parts)),"id=?",arrayOf(c.getLong(0).toString()))
        } }
    }
    fun configure(account: Account, autoMatch: Boolean = true) = transaction { db ->
        require(account.name.isNotBlank() && account.name.length <= 60 && account.share in 0..10000) { "Ungültige Kontoeinstellungen." }
        val iban = normalizeIban(account.iban)
        require(iban.isEmpty() || !db.rawQuery("SELECT 1 FROM accounts WHERE iban=? AND name!=?",arrayOf(iban,account.name)).use { it.moveToFirst() }) { "IBAN bereits vergeben." }
        db.insertWithOnConflict("payments",null,values("name" to account.name),SQLiteDatabase.CONFLICT_IGNORE)
        // UPDATE instead of REPLACE: preserve foreign-key identity.
        val v = values("share" to account.share,"share_income" to if(account.shareIncome) 1 else 0,"iban" to iban)
        if (db.update("accounts",v,"name=?",arrayOf(account.name))==0) { v.put("name",account.name); db.insertOrThrow("accounts",null,v) }
        if(autoMatch) reconcile()
    }
    fun link(pair: Transfer) = transaction { db ->
        val entries = snapshot().entries.associateBy { it.id }
        val a = entries[pair.outgoing] ?: error("Buchung fehlt."); val b = entries[pair.incoming] ?: error("Buchung fehlt.")
        require(a.amount > 0 && b.amount == -a.amount && a.payment.isNotEmpty() && b.payment.isNotEmpty() && a.payment != b.payment && a.group.isEmpty() && b.group.isEmpty() && (a.parts+b.parts).none { !it.group.isNullOrEmpty() }) { "Keine passenden Gegenbuchungen. Gruppen zuerst entfernen." }
        require(snapshot().accounts.map { it.name }.containsAll(listOf(a.payment,b.payment))) { "Beide Zahlungsmittel als eigene Konten konfigurieren." }
        require(!db.rawQuery("SELECT 1 FROM transfers WHERE outgoing IN (?,?) OR incoming IN (?,?)",arrayOf(a.id.toString(),b.id.toString(),a.id.toString(),b.id.toString())).use { it.moveToFirst() }) { "Buchung bereits zugeordnet." }
        db.insertOrThrow("transfers",null,values("outgoing" to a.id,"incoming" to b.id))
    }
    fun unlink(pair: Transfer) = transaction { db ->
        db.delete("transfers","outgoing=?",arrayOf(pair.outgoing.toString()))
        db.insertWithOnConflict("ignored",null,values("outgoing" to pair.outgoing,"incoming" to pair.incoming),SQLiteDatabase.CONFLICT_IGNORE)
    }
    fun reconsider(pair: Transfer) { writableDatabase.delete("ignored","outgoing=? AND incoming=?",arrayOf(pair.outgoing.toString(),pair.incoming.toString())) }
    fun transferCandidates(): List<Transfer> { val s=snapshot();return TransferMatcher.candidates(s.entries,s.accounts,s.transfers,s.ignored) }
    private fun reconcile() {
        val s=snapshot()
        TransferMatcher.automatic(s.entries,s.accounts,s.transfers,s.ignored).forEach { pair -> writableDatabase.insertOrThrow("transfers",null,values("outgoing" to pair.outgoing,"incoming" to pair.incoming)) }
    }
    fun importEntries(entries: List<Entry>): Pair<Int,Int> = transaction { db ->
        var imported=0; var skipped=0
        entries.forEach { e ->
            if(e.importKey != null && db.rawQuery("SELECT 1 FROM entries WHERE import_key=?",arrayOf(e.importKey)).use { it.moveToFirst() }) skipped++
            else { putEntry(db,e.copy(id=0)); imported++ }
        }
        reconcile()
        imported to skipped
    }
    private fun <T> transaction(action: (SQLiteDatabase) -> T): T {
        val db=writableDatabase; db.beginTransaction()
        try { val result=action(db); db.setTransactionSuccessful(); return result } finally { db.endTransaction() }
    }
    private fun seed(db: SQLiteDatabase) {
        val today=LocalDate.now()
        for (i in 0L..11L) {
            val month=today.withDayOfMonth(1).minusMonths(i)
            listOf(
                Entry(date=month.plusDays(1).toString(),merchant="Gehalt · Beispiel",amount=-285000,category="Gehalt",payment="Bankkarte",kind="income"),
                Entry(date=month.plusDays(2).toString(),merchant="Miete",amount=85000,category="Wohnen",payment="Bankkarte"),
                Entry(date=month.plusDays(4).toString(),merchant="Supermarkt",amount=5480+i*137,category="Lebensmittel",payment="Bankkarte"),
                Entry(date=month.plusDays(8).toString(),merchant="Wochenmarkt",amount=2310+i*53,category="Lebensmittel",payment="Bar"),
                Entry(date=month.plusDays(11).toString(),merchant="Bahn",amount=2900+i*120,category="Mobilität",payment="Bankkarte"),
                Entry(date=month.plusDays(15).toString(),merchant="Restaurant",amount=4200,category="Freizeit",payment="Bankkarte",group="Abendessen ${month}"),
                Entry(date=month.plusDays(16).toString(),merchant="Anteil von Alex",amount=-2100,category="Freizeit",payment="PayPal",group="Abendessen ${month}",notes="Erstattung als negative Ausgabe")
            ).forEach { putEntry(db,it) }
        }
    }
    private fun entryJson(e: Entry) = JSONObject().put("id",e.id).put("date",e.date).put("merchant",e.merchant).put("amount",e.amount).put("category",e.category).put("payment",e.payment).put("kind",e.kind).put("notes",e.notes).put("group",e.group).put("parts",JSONArray(partsJson(e.parts))).put("receipt",e.receipt).put("counterparty",e.counterparty).put("import_key",e.importKey ?: JSONObject.NULL)
    fun backup(output: OutputStream) = transaction { _ ->
        val s=snapshot()
        require(s.entries.size <= 50000 && s.categories.size <= 2000 && s.payments.size <= 2000) { "Datensatz für dieses Sicherungsformat zu groß." }
        readableDatabase.rawQuery("SELECT COALESCE(SUM(length(image)),0) FROM receipts",null).use { c -> c.moveToFirst();require(c.getLong(0)<=512_000_000) { "Belege für dieses Sicherungsformat zu groß (max. 512 MB)." } }
        val metadata=JSONObject().put("format","kassensturz-android").put("version",1)
            .put("categories",JSONArray(s.categories)).put("payments",JSONArray(s.payments))
            .put("entries",JSONArray().apply { s.entries.forEach { put(entryJson(it)) } })
            .put("accounts",JSONArray().apply { s.accounts.forEach { put(JSONObject().put("name",it.name).put("share",it.share).put("share_income",it.shareIncome).put("iban",it.iban)) } })
            .put("ignored",JSONArray().apply { s.ignored.forEach { put(JSONObject().put("outgoing",it.outgoing).put("incoming",it.incoming)) } })
            .put("transfers",JSONArray().apply { s.transfers.forEach { put(JSONObject().put("outgoing",it.outgoing).put("incoming",it.incoming)) } })
        val raw=metadata.toString().toByteArray(Charsets.UTF_8)
        require(raw.size <= 16_000_000) { "Datensatz für dieses Sicherungsformat zu groß." }
        ZipOutputStream(output).use { zip ->
            zip.putNextEntry(ZipEntry("data.json")); zip.write(raw); zip.closeEntry()
            s.entries.filter { it.receipt }.forEach { e -> zip.putNextEntry(ZipEntry("receipts/${e.id}.jpg")); zip.write(receipt(e.id) ?: error("Beleg fehlt.")); zip.closeEntry() }
        }
    }
    fun restore(input: InputStream) = transaction { db ->
        ZipInputStream(input).use { zip ->
            require(zip.nextEntry?.name == "data.json") { "Keine Kassensturz-Android-Sicherung." }
            val meta=JSONObject(readLimited(zip,16_000_000).toString(Charsets.UTF_8))
            require(meta.getString("format")=="kassensturz-android" && meta.getInt("version")==1) { "Unbekanntes Sicherungsformat." }
            val cats=meta.getJSONArray("categories").strings(); val payments=meta.getJSONArray("payments").strings()
            require(cats.isNotEmpty() && cats.size <= 2000 && payments.size <= 2000 && (cats+payments).all { it.isNotBlank() && it.length <= 60 }) { "Ungültige Kategorien oder Zahlungsmittel." }
            val rows=meta.getJSONArray("entries").objects()
            require(rows.size <= 50000) { "Zu viele Buchungen." }
            val expectedReceipts=mutableSetOf<Long>()
            listOf("ignored","transfers","receipts","entries","accounts","payments","categories").forEach { db.delete(it,null,null) }
            cats.forEach { db.insertOrThrow("categories",null,values("name" to it)) }; payments.forEach { db.insertOrThrow("payments",null,values("name" to it)) }
            rows.forEach { j ->
                val e=Entry(id=j.exactLong("id"),date=j.getString("date"),merchant=j.getString("merchant"),amount=j.exactLong("amount"),category=j.getString("category"),payment=j.getString("payment"),kind=j.getString("kind"),notes=j.getString("notes"),group=j.getString("group"),parts=parseParts(j.getJSONArray("parts").toString()),counterparty=j.getString("counterparty"),importKey=if(j.isNull("import_key")) null else j.getString("import_key"))
                require(e.id > 0) { "Ungültige ID." }; Ledger.validate(e)
                // Insert placeholder identity, then use the normal validated write path.
                db.execSQL("INSERT INTO entries(id,date,merchant,amount,category,payment,kind,notes,group_name,parts,counterparty) VALUES (?,?,?,1,?,'','expense','','','[]','')",arrayOf(e.id,e.date,e.merchant,e.category))
                putEntry(db,e)
                if(j.getBoolean("receipt")) expectedReceipts.add(e.id)
            }
            meta.getJSONArray("accounts").objects().forEach { j -> configure(Account(j.getString("name"),j.getInt("share"),j.getBoolean("share_income"),j.getString("iban")),autoMatch=false) }
            meta.getJSONArray("transfers").objects().forEach { j -> link(Transfer(j.exactLong("outgoing"),j.exactLong("incoming"))) }
            meta.optJSONArray("ignored")?.objects()?.forEach { j ->
                db.insertOrThrow("ignored",null,values("outgoing" to j.exactLong("outgoing"),"incoming" to j.exactLong("incoming")))
            }
            var total=0L
            while(true) {
                val part=zip.nextEntry ?: break
                require(Regex("receipts/[1-9][0-9]*\\.jpg").matches(part.name)) { "Unbekannter Archivinhalt." }
                val id=part.name.removePrefix("receipts/").removeSuffix(".jpg").toLong()
                require(expectedReceipts.remove(id)) { "Doppelter oder unbekannter Beleg." }
                val bytes=readLimited(zip,4_000_000); total += bytes.size
                require(total <= 512_000_000 && bytes.size > 2 && bytes[0] == 0xff.toByte() && bytes[1] == 0xd8.toByte()) { "Belegarchiv ist ungültig oder zu groß." }
                db.insertOrThrow("receipts",null,values("entry_id" to id,"image" to bytes))
            }
            require(expectedReceipts.isEmpty()) { "Belege fehlen in der Sicherung." }
        }
    }
    companion object {
        fun readLimited(input: InputStream, max: Int): ByteArray {
            val out=java.io.ByteArrayOutputStream(); val buffer=ByteArray(8192)
            while(true) { val n=input.read(buffer); if(n<0) break; require(out.size()+n <= max) { "Datei ist zu groß." }; out.write(buffer,0,n) }
            return out.toByteArray()
        }
        fun normalizeIban(raw: String): String {
            val iban=raw.replace(Regex("\\s"),"").uppercase(java.util.Locale.ROOT)
            if(iban.isEmpty()) return ""
            require(Regex("[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}").matches(iban)) { "Ungültige IBAN." }
            val number=(iban.drop(4)+iban.take(4)).map { if(it.isLetter()) (it.code-55).toString() else it.toString() }.joinToString("")
            require(java.math.BigInteger(number).mod(java.math.BigInteger.valueOf(97)).toInt()==1) { "IBAN-Prüfsumme stimmt nicht." }
            return iban
        }
    }
}
