package de.kassensturz.app

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.math.BigInteger
import java.math.RoundingMode
import java.time.LocalDate

internal fun JSONArray.rows(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
internal fun JSONObject.num(key: String): Long {
    require(Regex("-?[0-9]+").matches(get(key).toString())) { "Ungültige Ganzzahl: $key" }
    return get(key).toString().toLong()
}

/** Portable wealth document, also used by the server backup format. */
object Wealth {
    const val MAX = 99999999999L
    val types = linkedMapOf("cash" to "Giro / Verrechnungskonto", "brokerage" to "Aktiendepot", "building" to "Bausparvertrag", "fixed" to "Festgeld", "savings" to "Tagesgeld", "other" to "Sonstiges")
    fun empty() = JSONObject().put("version",1).put("assets",JSONArray()).put("plans",JSONArray()).put("events",JSONArray())
    fun assets(d: JSONObject) = d.getJSONArray("assets").rows()
    fun plans(d: JSONObject) = d.getJSONArray("plans").rows()
    fun events(d: JSONObject) = d.getJSONArray("events").rows()
    private fun number(n: Long, low: Long=0, high: Long=MAX): Long { require(n in low..high) { "Vermögenswert außerhalb des zulässigen Bereichs." };return n }
    private fun text(raw: String, limit: Int=100, required: Boolean=true) { require(raw.length<=limit && '\u0000' !in raw && (!required || raw.isNotBlank())) { "Bezeichnung fehlt oder ist zu lang." } }
    private fun day(raw: String): String { require(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}").matches(raw)) { "Datum als JJJJ-MM-TT eingeben." };LocalDate.parse(raw);return raw }
    fun scaled(raw: String, places: Int=2): Long {
        require(Regex("-?[0-9]+([.,][0-9]+)?").matches(raw.trim())) { "Zahl ohne Tausendertrennzeichen eingeben." }
        return BigDecimal(raw.trim().replace(',','.')).movePointRight(places).longValueExact()
    }
    fun decimal(n: Long, places: Int=2) = BigDecimal(n).movePointLeft(places).toPlainString()
    private fun round(n: BigInteger, denominator: Long) = BigDecimal(n).divide(BigDecimal(denominator),0,RoundingMode.HALF_UP).longValueExact()
    private fun round(n: Long, denominator: Long) = round(BigInteger.valueOf(n),denominator)
    fun linked(d: JSONObject): Set<Long> = events(d).flatMap { e -> val a=e.getJSONArray("entries");(0 until a.length()).map { a.getLong(it) } }.toSet()
    fun asset(d: JSONObject, id: Long) = assets(d).find { it.num("id")==id }
    fun validate(d: JSONObject): JSONObject {
        require(d.num("version")==1L && assets(d).size<=100 && plans(d).size<=200 && events(d).size<=10000) { "Unbekanntes oder zu großes Vermögensformat." }
        val ids=mutableSetOf<Long>();val names=mutableSetOf<String>()
        assets(d).forEach { a ->
            require(ids.add(number(a.num("id"),1)) && a.getString("type") in types) { "Ungültige Anlage." }
            text(a.getString("name"));number(a.num("rate_bp"),-10000,10000)
            require(names.add(a.getString("name").trim().lowercase(java.util.Locale.ROOT))) { "Anlagenamen müssen eindeutig sein." }
            if(a.getString("maturity").isNotEmpty()) day(a.getString("maturity"))
            else require(a.getString("type")!="fixed") { "Für Festgeld ein Laufzeitende angeben." }
            val snapshots=a.getJSONArray("snapshots").rows();require(snapshots.size in 1..1000 && snapshots.map { it.getString("date") }.distinct().size==snapshots.size)
            snapshots.forEach { s -> day(s.getString("date"));number(s.num("value"));number(s.num("seq")) }
            val positions=a.getJSONArray("positions").rows();require(positions.size<=100 && positions.map { it.getString("name") }.distinct().size==positions.size)
            positions.forEach { p ->
                require(a.getString("type")=="brokerage");text(p.getString("name"));val symbol=p.getString("symbol")
                require(symbol.isEmpty() || Regex("[A-Za-z0-9.^_-]{1,30}").matches(symbol));number(p.num("units"),0,1000000000000);number(p.num("price"),0,1000000000000);day(p.getString("date"))
            }
        }
        val planIds=mutableSetOf<Long>()
        plans(d).forEach { p ->
            require(planIds.add(number(p.num("id"),1)) && p.num("from") in ids && p.num("to") in ids && p.num("from")!=p.num("to")) { "Ungültiger Dauerauftrag." }
            text(p.getString("name"));number(p.num("amount"),1);number(p.num("every"),1,12);day(p.getString("start"))
            val end=p.getString("end");require(end.isEmpty() || day(end)>=p.getString("start"));require(p.get("enabled") is Boolean)
        }
        val eventIds=mutableSetOf<Long>();val occurrences=mutableSetOf<Pair<Long,String>>();val linked=mutableSetOf<Long>()
        events(d).forEach { e ->
            require(eventIds.add(number(e.num("id"),1)));day(e.getString("date"));number(e.num("amount"),1);text(e.getString("note"),500,false)
            val kind=e.getString("kind");require(kind in listOf("transfer","interest","dividend","fee","buy","sell") && e.num("to") in ids)
            require(if(kind=="transfer") e.num("from") in ids && e.num("from")!=e.num("to") else e.num("from")==0L)
            val plan=number(e.num("plan"));if(plan>0)require(plan in planIds && occurrences.add(plan to e.getString("date")))
            val entries=e.getJSONArray("entries");require(entries.length()<=2)
            repeat(entries.length()) { i -> require(kind=="transfer" && linked.add(number(entries.getLong(i),1))) }
        }
        val maximum=eventIds.maxOrNull() ?: 0L
        require(assets(d).all { a -> a.getJSONArray("snapshots").rows().all { it.num("seq")<=maximum } }) { "Bestandswert verweist auf unbekannte Buchungsfolge." }
        assets(d).forEach { a -> number(holdings(a));number(cash(d,a));number(cash(d,a)+holdings(a)) }
        return d
    }
    fun cash(d: JSONObject, a: JSONObject, date: String=LocalDate.now().toString()): Long {
        val s=a.getJSONArray("snapshots").rows().filter { it.getString("date")<=date }.maxByOrNull { it.getString("date") } ?: return 0
        var value=s.num("value")
        events(d).forEach { e ->
            val ed=e.getString("date")
            if(ed<=date && (ed>s.getString("date") || ed==s.getString("date") && e.num("id")>s.num("seq"))) {
                if(e.getString("kind")=="transfer") value+=e.num("amount")*((if(e.num("to")==a.num("id"))1 else 0)-(if(e.num("from")==a.num("id"))1 else 0))
                else if(e.num("to")==a.num("id")) value+=e.num("amount")*if(e.getString("kind") in listOf("fee","buy"))-1 else 1
            }
        }
        return value
    }
    fun holdings(a: JSONObject) = a.getJSONArray("positions").rows().sumOf { p -> round(BigInteger.valueOf(p.num("units")).multiply(BigInteger.valueOf(p.num("price"))),10000000000) }
    fun total(d: JSONObject) = assets(d).sumOf { cash(d,it)+holdings(it) }
    private fun next(rows: List<JSONObject>) = (rows.maxOfOrNull { it.num("id") } ?: 0)+1
    private fun replace(d: JSONObject, key: String, old: JSONObject?, new: JSONObject) {
        val rows=d.getJSONArray(key).rows().toMutableList();if(old==null)rows.add(new) else rows[rows.indexOf(old)]=new;d.put(key,JSONArray(rows))
    }
    fun dates(p: JSONObject, after: String, until: String): List<String> {
        val result=mutableListOf<String>();val start=LocalDate.parse(p.getString("start"));val end=p.getString("end")
        for(i in 0 until 1200) {
            val date=start.plusMonths(i*p.num("every")).toString();if(date>until || end.isNotEmpty() && date>end)return result
            if(date>after)result.add(date)
        }
        error("Dauerauftrag umfasst mehr als 1200 Termine.")
    }
    private fun post(d: JSONObject, c: JSONObject, today: String) {
        val e=JSONObject().put("id",next(events(d))).put("date",day(c.getString("date"))).put("kind",c.getString("kind")).put("amount",number(c.num("amount"),1))
            .put("from",c.optLong("from",0)).put("to",c.num("to")).put("note",c.optString("note","")).put("plan",c.optLong("plan",0)).put("entries",c.optJSONArray("entries") ?: JSONArray())
        require(e.getString("date")<=today) { "Zukünftige Buchungen als Dauerauftrag planen." }
        val a=asset(d,if(e.getString("kind")=="transfer")e.num("from") else e.num("to")) ?: error("Quellanlage fehlt.")
        val target=asset(d,e.num("to")) ?: error("Zielanlage fehlt.")
        require(listOf(a,target).none { item -> item.getJSONArray("snapshots").rows().any { it.getString("date")>e.getString("date") } }) { "Bewegung liegt vor einem neueren Bestandswert. Historische Korrekturen über Bestandswerte erfassen." }
        require(listOf(a,target).all { it.getJSONArray("snapshots").rows().any { s -> s.getString("date")<=e.getString("date") } }) { "Anfangsbestand zum Buchungsdatum fehlt." }
        require(e.getString("kind") !in listOf("transfer","fee","buy") || cash(d,a,e.getString("date"))>=e.num("amount")) { "Quellguthaben reicht nicht aus." }
        d.getJSONArray("events").put(e);validate(d)
        val checkDates=events(d).map { it.getString("date") }.filter { it>=e.getString("date") }+today
        require(assets(d).all { item -> checkDates.all { cash(d,item,it)>=0 } }) { "Buchung würde ein späteres Guthaben überziehen." }
    }
    fun apply(source: JSONObject, c: JSONObject, today: String=LocalDate.now().toString()): JSONObject {
        val d=JSONObject(source.toString())
        when(c.getString("op")) {
            "asset" -> {
                val old=asset(d,c.optLong("id",0));require(c.optLong("id",0)==0L || old!=null) { "Anlage fehlt." }
                val a=if(old==null) JSONObject().put("id",next(assets(d))).put("snapshots",JSONArray()).put("positions",JSONArray()) else JSONObject(old.toString())
                a.put("name",c.getString("name").trim()).put("type",c.getString("type")).put("rate_bp",c.num("rate_bp")).put("maturity",c.optString("maturity",""))
                if(c.has("value")) {
                    val date=day(c.getString("date"));require(date<=today)
                    val snapshots=a.getJSONArray("snapshots").rows().filter { it.getString("date")!=date }.toMutableList()
                    snapshots.add(JSONObject().put("date",date).put("value",c.num("value")).put("seq",events(d).maxOfOrNull { it.num("id") } ?: 0));a.put("snapshots",JSONArray(snapshots))
                }
                replace(d,"assets",old,a)
            }
            "delete-asset" -> {
                val id=c.num("id");require((events(d)+plans(d)).none { it.num("from")==id || it.num("to")==id }) { "Anlagen mit Bewegungen oder Daueraufträgen bleiben für die Historie erhalten." }
                d.put("assets",JSONArray(assets(d).filter { it.num("id")!=id }))
            }
            "plan" -> {
                val old=plans(d).find { it.num("id")==c.optLong("id",0) }
                val p=JSONObject();listOf("name","from","to","amount","every","start","end","enabled").forEach { p.put(it,c.get(it)) };p.put("id",old?.num("id") ?: next(plans(d)))
                require(old==null || events(d).none { it.num("plan")==old.num("id") } || listOf("start","every","from","to").all { p.get(it).toString()==old.get(it).toString() }) { "Gebuchten Dauerauftrag pausieren und neuen anlegen." }
                replace(d,"plans",old,p)
            }
            "event" -> post(d,c,today)
            "link" -> {
                val e=events(d).find { it.num("id")==c.num("id") && it.getString("kind")=="transfer" } ?: error("Umbuchung fehlt.")
                e.put("entries",c.getJSONArray("entries"))
            }
            "delete-position" -> {
                val a=asset(d,c.num("id")) ?: error("Depot fehlt.");val positions=a.getJSONArray("positions").rows()
                val p=positions.find { it.getString("name")==c.getString("name") } ?: error("Position fehlt.")
                require(p.num("units")==0L) { "Vor dem Entfernen Bestand auf null setzen oder Position verkaufen." }
                a.put("positions",JSONArray(positions.filter { it!==p }))
            }
            "run-plans" -> {
                val booked=events(d).map { it.num("plan") to it.getString("date") }.toSet()
                val due=plans(d).filter { it.getBoolean("enabled") }.flatMap { p -> dates(p,"0001-01-01",today).filter { (p.num("id") to it) !in booked }.map { it to p } }.sortedWith(compareBy({it.first},{it.second.num("id")}))
                due.forEach { (date,p) -> post(d,JSONObject().put("date",date).put("kind","transfer").put("amount",p.num("amount")).put("from",p.num("from")).put("to",p.num("to")).put("note",p.getString("name")).put("plan",p.num("id")),today) }
            }
            "position", "trade" -> {
                val a=asset(d,c.num("id")) ?: error("Depot fehlt.");require(a.getString("type")=="brokerage")
                val positions=a.getJSONArray("positions").rows().toMutableList();val old=positions.find { it.getString("name")==c.getString("name") }
                val p=JSONObject();listOf("name","symbol","units","price","date").forEach { p.put(it,c.get(it)) };require(day(p.getString("date"))<=today)
                if(c.getString("op")=="trade") {
                    require(p.getString("date")==today) { "Wertpapierhandel zunächst nur mit heutigem Datum erfassen; historische Bestände über Bestandskorrektur setzen." }
                    val units=number(p.num("units"),1,1000000000000);val price=number(p.num("price"),1,1000000000000);val sell=c.optBoolean("sell",false)
                    require(!sell || (old?.num("units") ?: 0)>=units) { "Nicht genügend Wertpapieranteile." }
                    post(d,JSONObject().put("date",p.getString("date")).put("kind",if(sell)"sell" else "buy").put("amount",round(BigInteger.valueOf(units).multiply(BigInteger.valueOf(price)),10000000000)).put("to",a.num("id")).put("note",(if(sell)"Verkauf " else "Kauf ")+p.getString("name")),today)
                    p.put("units",(old?.num("units") ?: 0)+if(sell)-units else units)
                }
                if(old==null)positions.add(p) else positions[positions.indexOf(old)]=p;a.put("positions",JSONArray(positions))
            }
            else -> error("Unbekannte Vermögensaktion.")
        }
        return validate(d)
    }
    data class Point(val date: String, val total: Long, val growth: Long)
    data class Projection(val points: List<Point>, val skipped: Int)
    fun forecast(d: JSONObject, months: Int, delta: Int=0, today: String=LocalDate.now().toString()): Projection {
        require(months in 1..360)
        val assets=assets(d);val balances=assets.associate { it.num("id") to cash(d,it,today) }.toMutableMap()
        val invested=assets.associate { it.num("id") to holdings(it) }.toMutableMap()
        val accrual=balances.mapValues { 0L }.toMutableMap();val start=LocalDate.parse(today);val last=start.plusMonths(months.toLong()).toString()
        val due=plans(d).filter { it.getBoolean("enabled") }.flatMap { p -> dates(p,today,last).map { it to p } }.groupBy({it.first},{it.second})
        val targets=(1..months).map { start.plusMonths(it.toLong()).toString() }.toSet()
        var current=start;var growth=0L;var skipped=0;val points=mutableListOf(Point(today,balances.values.sum()+invested.values.sum(),0))
        while(current.toString()<last) {
            current=current.plusDays(1);val date=current.toString()
            assets.forEach { a ->
                val id=a.num("id");val maturity=a.getString("maturity");val rate=(a.num("rate_bp")+if(a.getString("type")=="brokerage")delta else 0).coerceIn(-10000,10000)
                val basis=if(a.getString("type")=="brokerage")invested.getValue(id) else balances.getValue(id)
                if(maturity.isEmpty() || date<=maturity)accrual[id]=Math.addExact(accrual.getValue(id),Math.multiplyExact(basis,rate))
                if(current.dayOfMonth==current.lengthOfMonth() || date==maturity) {
                    val target=if(a.getString("type")=="brokerage")invested else balances
                    val interest=round(accrual.getValue(id),3650000);target[id]=number(target.getValue(id)+interest);accrual[id]=0;growth+=interest
                }
            }
            due[date]?.sortedBy { it.num("id") }?.forEach { p ->
                val from=p.num("from");val to=p.num("to");val amount=p.num("amount")
                if(balances.getValue(from)>=amount) { balances[from]=balances.getValue(from)-amount;balances[to]=number(balances.getValue(to)+amount) } else skipped++
            }
            if(date in targets)points.add(Point(date,balances.values.sum()+invested.values.sum(),growth))
        }
        return Projection(points,skipped)
    }
}
