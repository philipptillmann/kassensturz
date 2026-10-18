package de.kassensturz.app

import org.junit.Assert.*
import org.junit.Test

class BankCsvTest {
    @Test fun tradeRepublicBookingDateIdentityAndExclusions() {
        val h="datetime;date;account_type;category;type;asset_class;name;amount;currency;transaction_id;counterparty_iban;description".split(';')
        val card=listOf("2026-09-30T23:30:00Z","2026-10-01","DEFAULT","CASH","CARD_TRANSACTION","","Synthetic shop","-12.34","EUR","fixture-1","","")
        val rows=listOf(h,card,card.toMutableList().also { it[9]="fixture-2" },card.toMutableList().also { it[4]="INTEREST_PAYMENT" })
        val result=BankCsv.tradeRepublic(rows,"Bar","Unkategorisiert")
        assertEquals(2,result.entries.size);assertEquals(1,result.excluded.size)
        assertEquals("2026-10-01",result.entries[0].date);assertEquals(1234L,result.entries[0].amount)
        assertNotEquals(result.entries[0].importKey,result.entries[1].importKey)
        assertNotEquals(result.entries[0].importKey,BankCsv.tradeRepublic(rows,"PayPal","Unkategorisiert").entries[0].importKey)
        assertEquals(result.entries[0].importKey,BankCsv.tradeRepublic(listOf(h,card.toMutableList().also { it[6]="Edited" }),"Bar","Unkategorisiert").entries[0].importKey)
        assertThrows(IllegalArgumentException::class.java) { BankCsv.tradeRepublic(listOf(h,card.toMutableList().also { it[8]="USD" }),"Bar","Unkategorisiert") }
    }
    @Test fun quotedMultilineAndEscapedQuotes() {
        val rows=BankCsv.parse("\uFEFFDate;Merchant;Amount\r\n01.10.2026;\"A; B\n\"\"Hello\"\"\";-12,50\r\n",';')
        assertEquals("Date",rows[0][0]);assertEquals("A; B\n\"Hello\"",rows[1][1])
        assertEquals(1250L,BankCsv.entries(rows,0,1,2,"ING","Shopping",true).single().amount)
    }
    @Test fun germanAmountsAndStrictDates() {
        assertEquals(-123456L,BankCsv.amount("-1.234,56 EUR"));assertEquals("2026-10-01",BankCsv.date("01.10.2026"))
        assertThrows(IllegalArgumentException::class.java) { BankCsv.date("31.02.2026") }
    }
    @Test fun duplicateOccurrencesArePreservedAndKeysAreAccountScoped() {
        val rows=listOf(listOf("D","M","A"),listOf("2026-10-01","Shop","-5,00"),listOf("2026-10-01","Shop","-5,00"))
        val a=BankCsv.entries(rows,0,1,2,"A","Shopping",true);val b=BankCsv.entries(rows,0,1,2,"B","Shopping",true)
        assertNotEquals(a[0].importKey,a[1].importKey);assertNotEquals(a[0].importKey,b[0].importKey)
        assertEquals(a,BankCsv.entries(rows,0,1,2,"A","Shopping",true))
    }
    @Test fun incomeClassificationIsExplicit() {
        val rows=listOf(listOf("D","M","A"),listOf("2026-10-01","Salary","2000"))
        assertEquals("expense",BankCsv.entries(rows,0,1,2,"A","Shopping",true).single().kind)
        assertEquals("income",BankCsv.entries(rows,0,1,2,"A","Gehalt",true,income=true).single().kind)
    }
    @Test fun malformedCsvCannotPartiallyImport() {
        assertThrows(IllegalArgumentException::class.java) { BankCsv.parse("A;B\n\"unfinished",';') }
        val rows=listOf(listOf("D","M","A"),listOf("2026-10-01","Shop","-5"),listOf("bad","Shop","-5"))
        assertThrows(IllegalArgumentException::class.java) { BankCsv.entries(rows,0,1,2,"A","Shopping",true) }
    }
}
