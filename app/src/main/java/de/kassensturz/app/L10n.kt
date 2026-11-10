package de.kassensturz.app

import android.content.Context
import org.json.JSONObject
import java.util.Locale

/** Interface-only translations. Never pass stored names or notes to this function. */
object L10n {
    var language="de"
        private set
    val locale: Locale get()=if(language=="en") Locale.UK else Locale.GERMANY
    private var catalog=JSONObject()
    private var pattern: Regex?=null
    fun init(context: Context) {
        language=if(context.getSharedPreferences("language",Context.MODE_PRIVATE).getString("value","de")=="en") "en" else "de"
        catalog=JSONObject(context.assets.open("locales/en.json").bufferedReader().use { it.readText() })
        val keys=catalog.keys().asSequence().toList().sortedByDescending { it.length }
        pattern=Regex(keys.joinToString("|") { Regex.escape(it) })
    }
    fun t(source: String): String {
        if(language!="en") return source
        if(catalog.has(source)) return catalog.getString(source)
        return pattern?.replace(source) { match ->
            val first=match.range.first;val last=match.range.last
            val before=source.getOrNull(first-1);val after=source.getOrNull(last+1)
            if((match.value.first().isLetter()&&before?.isLetter()==true)||(match.value.last().isLetter()&&after?.isLetter()==true)) match.value else catalog.getString(match.value)
        } ?: source
    }
}
