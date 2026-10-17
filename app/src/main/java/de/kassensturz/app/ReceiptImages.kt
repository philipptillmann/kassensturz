package de.kassensturz.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import java.io.ByteArrayOutputStream

object ReceiptImages {
    /** ImageDecoder handles HEIF and EXIF orientation on Android 9+. */
    fun jpeg(context: Context, uri: Uri): ByteArray {
        // Bound compressed input before letting a codec inspect it.
        val bytes=context.contentResolver.openInputStream(uri)?.use { Store.readLimited(it,24_000_000) } ?: error("Bild konnte nicht geöffnet werden.")
        val bitmap=ImageDecoder.decodeBitmap(ImageDecoder.createSource(java.nio.ByteBuffer.wrap(bytes))) { decoder, info, _ ->
            val w=info.size.width; val h=info.size.height
            require(w>0 && h>0 && w.toLong()*h <= 150_000_000) { "Bild ist zu groß." }
            val ratio=3200.0 / maxOf(w,h)
            if(ratio<1) decoder.setTargetSize(maxOf(1,(w*ratio).toInt()),maxOf(1,(h*ratio).toInt()))
            decoder.allocator=ImageDecoder.ALLOCATOR_SOFTWARE
        }
        try {
            // Flatten alpha onto white so PNG receipts do not acquire a black background.
            val flat=Bitmap.createBitmap(bitmap.width,bitmap.height,Bitmap.Config.RGB_565)
            try {
                val canvas=android.graphics.Canvas(flat);canvas.drawColor(android.graphics.Color.WHITE);canvas.drawBitmap(bitmap,0f,0f,null)
                val out=ByteArrayOutputStream();require(flat.compress(Bitmap.CompressFormat.JPEG,85,out)) { "JPEG-Konvertierung fehlgeschlagen." }
                require(out.size()<=4_000_000) { "Bild ist nach Kompression zu groß." }
                return out.toByteArray()
            } finally { flat.recycle() }
        } finally { bitmap.recycle() }
    }
}
