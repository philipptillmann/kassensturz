package de.kassensturz.app

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate

/** A single optional, user-triggered free GLOBAL_QUOTE request. No retries. */
object WealthQuotes {
    fun fetch(symbol:String,key:String):Pair<Long,String> {
        require(Regex("[A-Za-z0-9.^_-]{1,30}").matches(symbol) && Regex("[A-Za-z0-9]{1,100}").matches(key)) { "Börsensymbol oder API-Schlüssel ungültig." }
        val connection=URL("https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${URLEncoder.encode(symbol,"UTF-8")}&apikey=${URLEncoder.encode(key,"UTF-8")}").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout=10000;connection.readTimeout=10000;connection.instanceFollowRedirects=false
            require(connection.responseCode==200)
            val raw=connection.inputStream.use { Store.readLimited(it,100000).toString(Charsets.UTF_8) }
            val quote=JSONObject(raw).getJSONObject("Global Quote");require(quote.getString("01. symbol").equals(symbol,true))
            val price=BigDecimal(quote.getString("05. price"));require(price>BigDecimal.ZERO && price<=BigDecimal(1000000))
            val date=LocalDate.parse(quote.getString("07. latest trading day"));require(date<=LocalDate.now())
            return price.movePointRight(6).setScale(0,RoundingMode.HALF_UP).longValueExact() to date.toString()
        } catch(e:Exception) { throw IllegalArgumentException("Kein Kurs verfügbar. Symbol, kostenloses API-Limit und Verbindung prüfen. Bisheriger Kurs bleibt erhalten.") }
        finally { connection.disconnect() }
    }
}
