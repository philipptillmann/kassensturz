package de.kassensturz.app

import android.content.Intent
import android.widget.TextView
import android.view.ViewGroup
import android.view.View
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LaunchTest {
    private fun find(v:View,text:String):TextView? {
        if(v is TextView && v.text.toString()==text)return v
        if(v is ViewGroup)for(i in 0 until v.childCount)find(v.getChildAt(i),text)?.let { return it }
        return null
    }
    @Test fun launchAndNavigateWithoutServer() {
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val a=instrumentation.startActivitySync(Intent(instrumentation.targetContext,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrumentation.waitForIdleSync()
            val deadline=System.currentTimeMillis()+10000
            while(System.currentTimeMillis()<deadline) {
                var ready=false;instrumentation.runOnMainSync { find(a.window.decorView,"Mehr")?.performClick();ready=find(a.window.decorView,"Vollständige Sicherung erstellen")!=null }
                if(ready)break
                Thread.sleep(100)
            }
            instrumentation.runOnMainSync { assertNotNull(find(a.window.decorView,"Kassensturz")) }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync { assertNotNull(find(a.window.decorView,"Vollständige Sicherung erstellen")) }
            assertFalse(a.packageManager.getPackageInfo(a.packageName,android.content.pm.PackageManager.GET_PERMISSIONS).requestedPermissions?.contains("android.permission.INTERNET") ?: false)
        } finally { instrumentation.runOnMainSync { a.finish() } }
    }
}
