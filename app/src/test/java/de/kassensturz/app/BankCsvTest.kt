package de.kassensturz.app

import org.junit.Assert.*
import org.junit.Test

class BankCsvTest {
    private val vbHeader="Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;Bankname Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;Verwendungszweck;Betrag;Waehrung;Saldo nach Buchung;Bemerkung;Gekennzeichneter Umsatz;Glaeubiger ID;Mandatsreferenz"
    private val vbRow="Demo account;DE00000000000000000000;DEMO;Example bank;03.10.2026;02.10.2026;Fictional shop;de 2222;DEMO;Lastschrift;Fictional purpose;-23,45;EUR;1.234,56;Fixture note;;Demo creditor;Demo mandate"
    @Test fun volksbankMappingIdentityNotesAndDuplicates() {
        val rows=BankCsv.parse("\uFEFF$vbHeader\r\n$vbRow\r\n$vbRow",';')
        assertTrue(BankCsv.isVolksbank(rows))
        val result=BankCsv.volksbank(rows,"Bar","Unkategorisiert")
        val entry=result.entries.first()
        assertEquals("2026-10-03",entry.date);assertEquals(2345L,entry.amount);assertEquals("DE2222",entry.counterparty)
        assertEquals("Lastschrift\nFictional purpose\nFixture note\nDemo creditor\nDemo mandate",entry.notes)
        assertEquals("vb:8a2526a0e07d0150840e1b9e960654dce9c4a475a5a418e8e15c8d71c18b7a62",entry.importKey);assertNotEquals(entry.importKey,result.entries[1].importKey)
        val changed=vbRow.replace("1.234,56","0").replace("Fixture note","Changed");assertEquals(entry.importKey,BankCsv.volksbank(BankCsv.parse("$vbHeader\n$changed",';'),"Bar","Unkategorisiert").entries.single().importKey)
    }
    @Test fun volksbankMultiAccountSelectionAndValidation() {
        val other=vbRow.replace("DE00000000000000000000","DE11111111111111111111")
        val rows=BankCsv.parse("$vbHeader\n$vbRow\n$other",';')
        assertEquals(2,BankCsv.volksbankAccounts(rows).size)
        assertThrows(IllegalArgumentException::class.java) { BankCsv.volksbank(rows,"Bar","Unkategorisiert") }
        val result=BankCsv.volksbank(rows,"Bar","Unkategorisiert","DE00000000000000000000")
        assertEquals(1,result.entries.size);assertEquals(1,result.excluded.size)
        assertNotEquals(result.entries.single().importKey,BankCsv.volksbank(rows,"Bar","Unkategorisiert","DE11111111111111111111").entries.single().importKey)
        for(invalid in listOf(vbRow.replace("EUR","USD"),vbRow.replace("03.10.2026","31.02.2026"),vbRow.replace("-23,45","1,234"),vbRow.substringBeforeLast(';'))) {
            assertThrows(IllegalArgumentException::class.java) { BankCsv.volksbank(BankCsv.parse("$vbHeader\n$invalid",';'),"Bar","Unkategorisiert") }
        }
        assertEquals(1,BankCsv.volksbank(BankCsv.parse("$vbHeader\n"+vbRow.replace("-23,45","0"),';'),"Bar","Unkategorisiert").excluded.size)
    }
    private fun ingFixture(vararg lines:String) = "\uFEFFUmsatzanzeige;Synthetic fixture only;;;;;;;;\r\nIBAN;DE00000000000000000000;;;;;;;;\r\n;;;;;;;;;\r\nBuchung;Wertstellungsdatum;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Referenz;Saldo;Währung;Betrag;Währung\r\n"+lines.joinToString("\r\n")
    @Test fun ingPreambleCurrenciesNotesAndSharedIdentity() {
        val row="30.09.2026;29.09.2026;Example shop;Lastschrift;Example purpose;;9.876,54;EUR;-10,50;EUR"
        val rows=BankCsv.parse(ingFixture(row),';')
        assertTrue(BankCsv.isIng(rows));assertEquals(2,rows.size)
        val entry=BankCsv.ing(rows,"Bar","Unkategorisiert").entries.single()
        assertEquals("2026-09-30",entry.date);assertEquals(1050L,entry.amount)
        assertEquals("Lastschrift\nExample purpose",entry.notes)
        assertEquals("ing:5b433d3a38b0b5e0b794b7024ba9da27198b3f53e7419b94412a3982a1cbd172",entry.importKey)
        val duplicate=BankCsv.ing(BankCsv.parse(ingFixture(row,row),';'),"Bar","Unkategorisiert")
        assertEquals(2,duplicate.entries.size);assertNotEquals(duplicate.entries[0].importKey,duplicate.entries[1].importKey)
        assertEquals(entry.importKey,BankCsv.ing(BankCsv.parse(ingFixture(row.replace("9.876,54","1,00")),';'),"Bar","Unkategorisiert").entries.single().importKey)
        assertNotEquals(entry.importKey,BankCsv.ing(rows,"PayPal","Unkategorisiert").entries.single().importKey)
    }
    @Test fun ingSalaryRefundZeroAndInvalidFields() {
        val row="30.09.2026;29.09.2026;Example shop;Lastschrift;Example purpose;;9.876,54;EUR;-10,50;EUR"
        val salary=row.replace("Lastschrift","Gehalt/Rente").replace("-10,50","1234")
        val refund=row.replace("Lastschrift","Gutschrift").replace("-10,50","25")
        val result=BankCsv.ing(BankCsv.parse(ingFixture(salary,refund,row.replace("-10,50","0")),';'),"Bar","Unkategorisiert")
        assertEquals(listOf("income","expense"),result.entries.map { it.kind });assertEquals(1,result.excluded.size)
        for(invalid in listOf(row.replace("EUR","USD"),row.replace("30.09.2026","31.02.2026"),row.replace("-10,50","1,234"),row.substringBeforeLast(';'))) {
            assertThrows(IllegalArgumentException::class.java) { BankCsv.ing(BankCsv.parse(ingFixture(row,invalid),';'),"Bar","Unkategorisiert") }
        }
        val quoted=row.replace("Example purpose","\"Quoted; purpose\nsecond line\"")
        assertTrue(BankCsv.ing(BankCsv.parse(ingFixture(quoted),';'),"Bar","Unkategorisiert").entries.single().notes.contains("Quoted; purpose\nsecond line"))
    }
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
