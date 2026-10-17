package de.kassensturz.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.File
import java.util.concurrent.TimeUnit
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReceiptTest {
    @Test fun jpegConversionBoundsSizeAndFlattensTransparency() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val bitmap=Bitmap.createBitmap(4000,2000,Bitmap.Config.ARGB_8888)
        val file=File.createTempFile("test-image-",".png",context.cacheDir)
        try {
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
            val bytes=ReceiptImages.jpeg(context,Uri.fromFile(file))
            assertEquals(0xff.toByte(),bytes[0]);assertEquals(0xd8.toByte(),bytes[1])
            val decoded=BitmapFactory.decodeByteArray(bytes,0,bytes.size)
            try { assertEquals(3200,decoded.width);assertEquals(1600,decoded.height);assertEquals(Color.WHITE,decoded.getPixel(0,0)) } finally { decoded.recycle() }
        } finally { bitmap.recycle();file.delete() }
    }
    @Test fun bundledOcrWorksWithoutInternetPermission() {
        val bitmap=Bitmap.createBitmap(1000,1000,Bitmap.Config.ARGB_8888)
        val canvas=Canvas(bitmap);canvas.drawColor(Color.WHITE)
        val paint=Paint(Paint.ANTI_ALIAS_FLAG).apply { color=Color.BLACK;textSize=64f;typeface=android.graphics.Typeface.MONOSPACE }
        canvas.drawText("KASSENSTURZ",60f,150f,paint);canvas.drawText("TESTBELEG",60f,260f,paint);canvas.drawText("SUMME EUR 7,25",60f,500f,paint)
        val recognizer=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        try {
            val text=Tasks.await(recognizer.process(InputImage.fromBitmap(bitmap,0)),90,TimeUnit.SECONDS).text
            assertTrue(text,text.contains("SUMME"));assertTrue(text,text.contains("7,25") || text.contains("7.25"))
        } finally { recognizer.close();bitmap.recycle() }
    }
}
