package de.kassensturz.app

import org.junit.Assert.*
import org.junit.Test

class TransferMatcherTest {
    private val accounts=listOf(Account("A",iban="DE89370400440532013000"),Account("B",iban="DE12500105170648489890"))
    private fun e(id:Long,amount:Long,payment:String,merchant:String="Umbuchung",date:String="2026-10-01")=Entry(id,date,merchant,amount,"Shopping",payment)
    @Test fun uniqueEvidenceMatchesAndAmbiguityDoesNot() {
        val entries=listOf(e(1,5000,"A"),e(2,-5000,"B"))
        assertEquals(listOf(Transfer(1,2)),TransferMatcher.automatic(entries,accounts,emptyList()))
        assertTrue(TransferMatcher.automatic(entries+e(3,-5000,"B"),accounts,emptyList()).isEmpty())
    }
    @Test fun amountAloneIsOnlyASuggestion() {
        val entries=listOf(e(1,5000,"A","Shop"),e(2,-5000,"B","Cashback"))
        assertEquals(1,TransferMatcher.candidates(entries,accounts,emptyList()).size)
        assertTrue(TransferMatcher.automatic(entries,accounts,emptyList()).isEmpty())
        assertEquals(1,TransferMatcher.automatic(listOf(entries[0].copy(counterparty=accounts[1].iban),entries[1]),accounts,emptyList()).size)
    }
    @Test fun groupsDatesIgnoredAndUsedLegsAreExcluded() {
        val entries=listOf(e(1,5000,"A"),e(2,-5000,"B"))
        assertTrue(TransferMatcher.candidates(entries,accounts,listOf(Transfer(1,2))).isEmpty())
        assertTrue(TransferMatcher.candidates(entries,accounts,emptyList(),listOf(Transfer(1,2))).isEmpty())
        assertTrue(TransferMatcher.candidates(listOf(entries[0].copy(group="Gift"),entries[1]),accounts,emptyList()).isEmpty())
        assertTrue(TransferMatcher.candidates(listOf(entries[0],entries[1].copy(date="2026-10-05")),accounts,emptyList()).isEmpty())
    }
}
