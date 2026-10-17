package de.kassensturz.app

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import java.time.YearMonth

/** Money is signed integer cents: expenses positive, credits/income negative. */
data class Part(val name: String, val amount: Long, val category: String, val group: String? = null)
data class Entry(val id: Long = 0, val date: String, val merchant: String, val amount: Long,
    val category: String, val payment: String = "", val kind: String = "expense", val notes: String = "",
    val group: String = "", val parts: List<Part> = emptyList(), val receipt: Boolean = false,
    val counterparty: String = "", val importKey: String? = null)
data class Account(val name: String, val share: Int = 10000, val shareIncome: Boolean = true, val iban: String = "")
data class Transfer(val outgoing: Long, val incoming: Long)
data class ReportRow(val date: String, val name: String, val amount: Long, val category: String, val kind: String,
    val ids: List<Long>, val grouped: Boolean = false, val parts: List<Part> = emptyList())
data class Totals(val expenses: Long, val credits: Long, val income: Long) { val net get() = expenses - credits; val balance get() = income - net }

object Ledger {
    const val MAX_CENTS = 99999999999L
    fun cents(raw: String): Long {
        val value = raw.trim().replace("€", "").replace(" ", "")
        require(Regex("[+-]?[0-9]+([.,][0-9]{1,2})?").matches(value)) { "Betrag z. B. 12,50 eingeben (ohne Tausendertrennzeichen)." }
        return BigDecimal(value.replace(',', '.')).movePointRight(2).longValueExact().also {
            require(it in -MAX_CENTS..MAX_CENTS) { "Betrag ist zu groß." }
        }
    }
    fun validate(entry: Entry) {
        require(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}").matches(entry.date)) { "Datum muss JJJJ-MM-TT sein." }
        LocalDate.parse(entry.date)
        require(entry.merchant.isNotBlank() && entry.merchant.length <= 200) { "Bezeichnung: 1–200 Zeichen." }
        require(entry.amount in -MAX_CENTS..MAX_CENTS && entry.amount != 0L) { "Betrag darf nicht null sein." }
        require(entry.kind in listOf("expense", "income")) { "Unbekannte Buchungsart." }
        require(entry.kind != "income" || entry.amount < 0) { "Einnahmen als positiven Eingabebetrag erfassen." }
        require(entry.category.isNotBlank() && entry.category.length <= 60) { "Kategorie fehlt." }
        require(entry.payment.length <= 60 && entry.group.length <= 100 && entry.notes.length <= 10000) { "Text ist zu lang." }
        require(entry.parts.size <= 200) { "Höchstens 200 Positionen." }
        require(entry.parts.isEmpty() || entry.parts.sumOf { it.amount } == entry.amount) { "Die Summe der Positionen muss dem Gesamtbetrag entsprechen." }
        entry.parts.forEach {
            require(it.name.isNotBlank() && it.name.length <= 200 && it.category.isNotBlank() && it.category.length <= 60 && (it.group?.length ?: 0) <= 100) { "Ungültige Position." }
            require(it.amount in -MAX_CENTS..MAX_CENTS) { "Positionsbetrag zu groß." }
        }
    }
    private fun scale(value: Long, share: Int) = BigDecimal(value).multiply(BigDecimal(share)).divide(BigDecimal(10000), 0, RoundingMode.HALF_UP).longValueExact()
    fun personal(entry: Entry, account: Account?): Entry {
        val share = if (account == null || entry.amount < 0 && !account.shareIncome) 10000 else account.share
        val amount = scale(entry.amount, share)
        if (entry.parts.isEmpty()) return entry.copy(amount = amount)
        val parts = entry.parts.map { it.copy(amount = it.amount * share / 10000) }.toMutableList()
        val delta = amount - parts.sumOf { it.amount }
        val order = entry.parts.indices.sortedBy { if (delta >= 0) -(entry.parts[it].amount * share % 10000) else entry.parts[it].amount * share % 10000 }
        repeat(kotlin.math.abs(delta).toInt()) { n -> val i = order[n % order.size]; parts[i] = parts[i].copy(amount = parts[i].amount + if (delta > 0) 1 else -1) }
        return entry.copy(amount = amount, parts = parts)
    }
    fun rows(entries: List<Entry>, month: String?, effective: Boolean, accounts: List<Account> = emptyList(), transfers: List<Transfer> = emptyList()): List<ReportRow> {
        val excluded = if (effective) transfers.flatMap { listOf(it.outgoing, it.incoming) }.toSet() else emptySet()
        val settings = accounts.associateBy { it.name }
        val source = entries.filter { it.id !in excluded }.map { if (effective) personal(it, settings[it.payment]) else it }
        data class Piece(val entry: Entry, val amount: Long, val category: String, val group: String, val label: String)
        fun pieces(e: Entry): List<Piece> = if (e.kind != "income" && e.parts.isNotEmpty() && e.parts.any { it.group != null })
            e.parts.map { Piece(e, it.amount, it.category, it.group ?: e.group, e.merchant + " · " + it.name) }
            else listOf(Piece(e, e.amount, e.category, e.group, e.merchant))
        val all = source.flatMap(::pieces)
        val anchors = all.filter { it.entry.kind != "income" && it.group.isNotEmpty() }.groupBy { it.group }.mapValues { (_, p) ->
            val sorted = p.sortedWith(compareBy({ it.entry.date }, { it.entry.id })); sorted.firstOrNull { it.amount > 0 } ?: sorted.first()
        }
        val selected = source.filter { month == null || it.date.startsWith(month) }
        if (!effective) return selected.map { ReportRow(it.date,it.merchant,it.amount,it.category,it.kind,listOf(it.id),parts=it.parts) }
        val selectedParts = selected.flatMap { e -> val p = pieces(e); if (p.any { it.group.isNotEmpty() } && e.kind != "income") p else listOf(Piece(e,e.amount,e.category,"",e.merchant)) }
        val result = mutableListOf<ReportRow>()
        val groups = linkedMapOf<String, MutableList<Piece>>()
        selectedParts.forEach { p -> if (p.entry.kind == "income" || p.group.isEmpty()) result.add(ReportRow(p.entry.date,p.label,p.amount,p.category,p.entry.kind,listOf(p.entry.id),parts=if(p.label==p.entry.merchant) p.entry.parts else emptyList())) else groups.getOrPut(p.group) { mutableListOf() }.add(p) }
        groups.forEach { (name, p) -> result.add(ReportRow(p.minOf { it.entry.date },name,p.sumOf { it.amount },anchors.getValue(name).category,"expense",p.map { it.entry.id }.distinct(),true)) }
        return result.sortedByDescending { it.date }
    }
    fun totals(rows: List<ReportRow>) = Totals(rows.filter { it.kind != "income" && it.amount > 0 }.sumOf { it.amount },
        rows.filter { it.kind != "income" && it.amount < 0 }.sumOf { -it.amount }, rows.filter { it.kind == "income" }.sumOf { -it.amount })
    fun monthRange(end: YearMonth, count: Int = 12) = (count - 1 downTo 0).map { end.minusMonths(it.toLong()).toString() }
}
