package de.kassensturz.app

import org.junit.Assert.*
import org.junit.Test

class BankCsvTest {
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
