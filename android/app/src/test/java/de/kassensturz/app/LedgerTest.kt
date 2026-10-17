package de.kassensturz.app

import org.junit.Assert.*
import org.junit.Test

class LedgerTest {
    private fun tx(id:Long=1,date:String="2026-10-01",amount:Long=10000,group:String="",kind:String="expense",parts:List<Part> = emptyList(),payment:String="Card") = Entry(id,date,"Example",amount,"Shopping",payment,kind,group=group,parts=parts)
    @Test fun decimalMoneyIsExactAndBounded() {
        assertEquals(1234L,Ledger.cents("12,34"));assertEquals(-1L,Ledger.cents("-0.01"))
        listOf("1,234","1.000,00","NaN","1e4","1000000000").forEach { raw->assertThrows(IllegalArgumentException::class.java) { Ledger.cents(raw) } }
    }
    @Test fun contributionsRemainInTheirOwnMonth() {
        val rows=listOf(tx(amount=9000,group="Gift"),tx(2,"2026-11-02",-3000,"Gift"))
        assertEquals(9000L,Ledger.totals(Ledger.rows(rows,"2026-10",true)).net)
        assertEquals(-3000L,Ledger.totals(Ledger.rows(rows,"2026-11",true)).net)
        assertEquals(6000L,Ledger.rows(rows,null,true).single().amount)
        assertEquals(2,Ledger.rows(rows,null,false).size)
    }
    @Test fun zeroAndNegativeGroupsArePreserved() {
        assertEquals(0L,Ledger.rows(listOf(tx(amount=5000,group="Gift"),tx(2,amount=-5000,group="Gift")),null,true).single().amount)
        assertEquals(-1000L,Ledger.rows(listOf(tx(amount=5000,group="Gift"),tx(2,amount=-6000,group="Gift")),null,true).single().amount)
    }
    @Test fun splitReceiptGroupsOnlyTheGift() {
        val parts=listOf(Part("Gift",3000,"Shopping","Gift"),Part("Own item",2000,"Freizeit",""))
        val rows=Ledger.rows(listOf(tx(amount=5000,parts=parts),tx(2,amount=-1000,group="Gift")),null,true)
        assertEquals(2,rows.size);assertEquals(listOf(2000L,2000L),rows.map { it.amount }.sorted());assertEquals(4000L,Ledger.totals(rows).net)
    }
    @Test fun nullGroupsInheritButEmptyOptOut() {
        val e=tx(amount=5000,group="Gift",parts=listOf(Part("A",3000,"Shopping"),Part("B",2000,"Freizeit","")))
        val rows=Ledger.rows(listOf(e),null,true)
        assertEquals(3000L,rows.single { it.grouped }.amount);assertEquals(2000L,rows.single { !it.grouped }.amount)
    }
    @Test fun incomeNeverOffsetsExpenseGroups() {
        val rows=Ledger.rows(listOf(tx(group="Gift"),tx(2,amount=-250000,group="Gift",kind="income")),null,true)
        val totals=Ledger.totals(rows);assertEquals(10000L,totals.net);assertEquals(250000L,totals.income)
    }
    @Test fun shareRoundingPreservesReceiptSumAndSigns() {
        val e=tx(amount=3,parts=listOf(Part("A",1,"Shopping"),Part("B",1,"Shopping"),Part("C",1,"Shopping")))
        val personal=Ledger.personal(e,Account("Card",5000));assertEquals(2L,personal.amount);assertEquals(personal.amount,personal.parts.sumOf { it.amount })
        assertEquals(-2L,Ledger.personal(e.copy(amount=-3,parts=e.parts.map { it.copy(amount=-1) }),Account("Card",5000)).amount)
        assertEquals(-3L,Ledger.personal(e.copy(amount=-3,parts=emptyList()),Account("Card",5000,false)).amount)
        assertEquals(3L,e.amount)
    }
    @Test fun transfersDisappearEvenAcrossMonths() {
        val rows=listOf(tx(amount=10000),tx(2,"2026-11-01",-10000,payment="Other"))
        assertTrue(Ledger.rows(rows,"2026-10",true,transfers=listOf(Transfer(1,2))).isEmpty())
        assertEquals(1,Ledger.rows(rows,"2026-10",false,transfers=listOf(Transfer(1,2))).size)
    }
    @Test fun invalidReceiptSumAndIncomeSignAreRejected() {
        assertThrows(IllegalArgumentException::class.java) { Ledger.validate(tx(parts=listOf(Part("A",1,"Shopping")))) }
        assertThrows(IllegalArgumentException::class.java) { Ledger.validate(tx(kind="income")) }
    }
    @Test fun monthRangeCrossesYearBoundary() { assertEquals(listOf("2025-12","2026-01","2026-02"),Ledger.monthRange(java.time.YearMonth.of(2026,2),3)) }
}
