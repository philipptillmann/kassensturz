package de.kassensturz.app

import java.time.LocalDate

object TransferMatcher {
    fun candidates(entries: List<Entry>, accounts: List<Account>, links: List<Transfer>, ignored: List<Transfer> = emptyList()): List<Transfer> {
        val used=links.flatMap { listOf(it.outgoing,it.incoming) }.toSet();val names=accounts.map { it.name }.toSet()
        val eligible=entries.filter { it.id !in used && it.payment in names && it.group.isEmpty() && it.parts.none { p->!p.group.isNullOrEmpty() } }
        val incoming=eligible.filter { it.amount<0 }.groupBy { (-it.amount) to it.date }
        val ignoredSet=ignored.toSet()
        return eligible.filter { it.amount>0 }.flatMap { a ->
            val day=LocalDate.parse(a.date)
            (-3L..3L).flatMap { delta -> incoming[a.amount to day.plusDays(delta).toString()] ?: emptyList() }
                .filter { it.payment!=a.payment }.map { Transfer(a.id,it.id) }
        }.filter { it !in ignoredSet }
    }
    fun automatic(entries: List<Entry>, accounts: List<Account>, links: List<Transfer>, ignored: List<Transfer> = emptyList()): List<Transfer> {
        val candidates=candidates(entries,accounts,links,ignored);val out=candidates.groupingBy { it.outgoing }.eachCount();val incoming=candidates.groupingBy { it.incoming }.eachCount()
        val tx=entries.associateBy { it.id };val settings=accounts.associateBy { it.name }
        val keyword=Regex("umbuchung|kontoübertrag|kontouebertrag|übertrag|uebertrag|eigenüberweisung|eigenueberweisung",RegexOption.IGNORE_CASE)
        fun mentions(e:Entry,iban:String)=iban.isNotEmpty() && (e.counterparty==iban || e.merchant.replace(Regex("\\s"),"").uppercase(java.util.Locale.ROOT).contains(iban))
        return candidates.filter { p ->
            val a=tx.getValue(p.outgoing);val b=tx.getValue(p.incoming)
            out[p.outgoing]==1 && incoming[p.incoming]==1 && (mentions(a,settings.getValue(b.payment).iban) || mentions(b,settings.getValue(a.payment).iban) || keyword.containsMatchIn(a.merchant) && keyword.containsMatchIn(b.merchant))
        }
    }
}
