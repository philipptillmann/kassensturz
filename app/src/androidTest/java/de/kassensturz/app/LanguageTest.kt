package de.kassensturz.app

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Locale

@RunWith(AndroidJUnit4::class)
class LanguageTest {
    @Test fun persistedLanguageAndOfflineManuals() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val preferences=context.getSharedPreferences("language",android.content.Context.MODE_PRIVATE)
        val previous=preferences.getString("value",null)
        try {
            preferences.edit().putString("value","en").commit()
            L10n.init(context)
            assertEquals("en",L10n.language)
            assertEquals(Locale.UK,L10n.locale)
            assertEquals("New entry",L10n.t("Neue Buchung"))
            val privateName="Ausgaben und Vermögen"
            assertEquals("Agreed: "+privateName,L10n.t("Vereinbart: ")+privateName)
            assertTrue(context.assets.open("manual/en.html").bufferedReader().use { it.readText() }.contains("Kassensturz user manual"))
            preferences.edit().putString("value","de").commit()
            L10n.init(context)
            assertEquals(Locale.GERMANY,L10n.locale)
            assertEquals("Neue Buchung",L10n.t("Neue Buchung"))
            assertTrue(context.assets.open("manual/de.html").bufferedReader().use { it.readText() }.contains("Kassensturz Benutzerhandbuch"))
        } finally {
            if(previous==null) preferences.edit().remove("value").commit() else preferences.edit().putString("value",previous).commit()
            L10n.init(context)
        }
    }
}
