package de.kassensturz.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class WealthTest {
    private val today="2026-01-01"
    private fun add(d:JSONObject,name:String="Giro",type:String="cash",value:Long=100000,rate:Long=0,maturity:String="") = Wealth.apply(d,JSONObject().put("op","asset").put("name",name).put("type",type).put("value",value).put("date",today).put("rate_bp",rate).put("maturity",maturity),today)
    @Test fun transfersPreserveTotalAndAreNotExpenses() {
        var d=add(Wealth.empty());d=add(d,"Tagesgeld","savings",0)
        d=Wealth.apply(d,JSONObject().put("op","event").put("kind","transfer").put("from",1).put("to",2).put("amount",25000).put("date",today),today)
        assertEquals(75000L,Wealth.cash(d,Wealth.assets(d)[0],today));assertEquals(25000L,Wealth.cash(d,Wealth.assets(d)[1],today))
        val linked=Entry(id=1,date=today,merchant="Anlage",amount=25000,category="Shopping",wealthTransfer=true)
        assertTrue(Ledger.rows(listOf(linked),null,false).isEmpty());assertTrue(Ledger.rows(listOf(linked),null,true).isEmpty())
    }
    @Test fun monthEndAndRunIdempotenceMatchServer() {
        var d=add(Wealth.empty());d=add(d,"Tagesgeld","savings",0)
        d=Wealth.apply(d,JSONObject().put("op","plan").put("name","Sparen").put("from",1).put("to",2).put("amount",10000).put("every",1).put("start","2026-01-31").put("end","2026-03-31").put("enabled",true),today)
        d=Wealth.apply(d,JSONObject().put("op","run-plans"),"2026-03-31")
        d=Wealth.apply(d,JSONObject().put("op","run-plans"),"2026-03-31")
        assertEquals(listOf("2026-01-31","2026-02-28","2026-03-31"),Wealth.events(d).map { it.getString("date") })
        assertEquals(100000L,Wealth.assets(d).sumOf { Wealth.cash(d,it,"2026-03-31") })
    }
    @Test fun interestAndMaturityUseSameCentVectorsAsServer() {
        val d=add(Wealth.empty(),type="savings",value=1000000,rate=1200)
        assertEquals(1009863L,Wealth.forecast(d,1,today=today).points.last().total)
        val fixed=add(Wealth.empty(),type="fixed",value=1000000,rate=1200,maturity="2026-01-16")
        assertEquals(1004932L,Wealth.forecast(fixed,12,today=today).points.last().total)
        val negative=add(Wealth.empty(),type="savings",value=1000000,rate=-1200)
        assertEquals(990137L,Wealth.forecast(negative,1,today=today).points.last().total)
    }
    @Test fun purchasesConsumeCashAndKeepTotal() {
        var d=add(Wealth.empty(),type="brokerage")
        d=Wealth.apply(d,JSONObject().put("op","trade").put("id",1).put("name","ETF").put("symbol","EXAMPLE").put("units",3000000).put("price",10000000).put("date",today),today)
        assertEquals(97000L,Wealth.cash(d,Wealth.assets(d)[0],today));assertEquals(3000L,Wealth.holdings(Wealth.assets(d)[0]))
        assertEquals(100000L,Wealth.forecast(d,1,today=today).points.last().total)
    }
    @Test fun paperGainsDoNotFundCashTransfers() {
        var d=add(Wealth.empty(),name="Depot",type="brokerage",value=0,rate=500);d=add(d,name="Giro",value=0)
        d=Wealth.apply(d,JSONObject().put("op","position").put("id",1).put("name","ETF").put("symbol","").put("units",10000000).put("price",10000000).put("date",today),today)
        d=Wealth.apply(d,JSONObject().put("op","plan").put("name","Auszahlung").put("from",1).put("to",2).put("amount",1000).put("every",1).put("start","2026-01-02").put("end","").put("enabled",true),today)
        val forecast=Wealth.forecast(d,1,today=today)
        assertEquals(1,forecast.skipped);assertTrue(forecast.points.last().total>10000L)
    }
    @Test fun insufficientFundsDoNotMutateSource() {
        var d=add(Wealth.empty());d=add(d,"Tagesgeld","savings",0)
        val before=d.toString()
        try { Wealth.apply(d,JSONObject().put("op","event").put("kind","transfer").put("from",1).put("to",2).put("amount",200000).put("date",today),today);fail("Insufficient funds accepted") } catch(expected:IllegalArgumentException) { }
        assertEquals(before,d.toString())
    }
}
