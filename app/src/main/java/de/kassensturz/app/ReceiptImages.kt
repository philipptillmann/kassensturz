package de.kassensturz.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import java.io.ByteArrayOutputStream
import java.io.File
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import kotlin.math.ceil

object ReceiptImages {
    /** ImageDecoder handles HEIF and EXIF orientation on Android 9+. */
    fun jpeg(context: Context, uri: Uri): ByteArray {
        // Bound compressed input before letting a codec inspect it.
        val bytes=context.contentResolver.openInputStream(uri)?.use { Store.readLimited(it,24_000_000) } ?: error(L10n.t("Bild konnte nicht geöffnet werden."))
        if(bytes.take(5).toByteArray().contentEquals("%PDF-".toByteArray(Charsets.US_ASCII))) {
            require(bytes.size<=12_000_000) { L10n.t("PDF ist zu groß (maximal 12 MB).") }
            return pdf(context,bytes)
        }
        val bitmap=ImageDecoder.decodeBitmap(ImageDecoder.createSource(java.nio.ByteBuffer.wrap(bytes))) { decoder, info, _ ->
            val w=info.size.width; val h=info.size.height
            require(w>0 && h>0 && w.toLong()*h <= 150_000_000) { L10n.t("Bild ist zu groß.") }
            val ratio=3200.0 / maxOf(w,h)
            if(ratio<1) decoder.setTargetSize(maxOf(1,(w*ratio).toInt()),maxOf(1,(h*ratio).toInt()))
            decoder.allocator=ImageDecoder.ALLOCATOR_SOFTWARE
        }
        try {
            // Flatten alpha onto white so PNG receipts do not acquire a black background.
            val flat=Bitmap.createBitmap(bitmap.width,bitmap.height,Bitmap.Config.RGB_565)
            try {
                val canvas=android.graphics.Canvas(flat);canvas.drawColor(android.graphics.Color.WHITE);canvas.drawBitmap(bitmap,0f,0f,null)
                val out=ByteArrayOutputStream();require(flat.compress(Bitmap.CompressFormat.JPEG,85,out)) { L10n.t("JPEG-Konvertierung fehlgeschlagen.") }
                require(out.size()<=4_000_000) { L10n.t("Bild ist nach Kompression zu groß.") }
                return out.toByteArray()
            } finally { flat.recycle() }
        } finally { bitmap.recycle() }
    }
    /** Render every PDF page; archives remain standard JPEG receipts/backups. */
    private fun pdf(context:Context, bytes:ByteArray):ByteArray {
        val file=File.createTempFile("receipt-pdf-",".pdf",context.cacheDir)
        try {
            file.writeBytes(bytes)
            ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
                val renderer=try { PdfRenderer(descriptor) } catch(error:Exception) {
                    throw IllegalArgumentException(L10n.t("PDF nicht lesbar oder passwortgeschützt. Bitte eine ungeschützte PDF verwenden."))
                }
                renderer.use {
                    require(renderer.pageCount in 1..5) { L10n.t("PDF muss 1 bis 5 Seiten enthalten.") }
                    val heights=(0 until renderer.pageCount).map { index ->
                        renderer.openPage(index).use { page ->
                            require(page.width>0 && page.height>0) { L10n.t("Ungültige PDF-Seitengröße.") }
                            val height=ceil(page.height.toDouble()*1600/page.width).toInt()
                            require(height in 1..5000) { L10n.t("PDF-Seitenformat ist zu lang oder ungültig.") }
                            height
                        }
                    }
                    val height=heights.sum()+16*(heights.size-1)
                    require(1600L*height<=25_000_000) { L10n.t("PDF ist zu groß. Bitte weniger Seiten auswählen.") }
                    val combined=Bitmap.createBitmap(1600,height,Bitmap.Config.RGB_565)
                    try {
                        val canvas=android.graphics.Canvas(combined);canvas.drawColor(android.graphics.Color.WHITE)
                        var top=0
                        heights.forEachIndexed { index,pageHeight ->
                            renderer.openPage(index).use { page ->
                                val image=Bitmap.createBitmap(1600,pageHeight,Bitmap.Config.ARGB_8888)
                                try {
                                    image.eraseColor(android.graphics.Color.WHITE)
                                    val matrix=android.graphics.Matrix().apply { setScale(1600f/page.width,1600f/page.width) }
                                    page.render(image,null,matrix,PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
                                    canvas.drawBitmap(image,0f,top.toFloat(),null)
                                } finally { image.recycle() }
                            }
                            top+=pageHeight+16
                        }
                        for(quality in listOf(85,75,65)) {
                            val out=ByteArrayOutputStream()
                            require(combined.compress(Bitmap.CompressFormat.JPEG,quality,out)) { L10n.t("JPEG-Konvertierung fehlgeschlagen.") }
                            if(out.size()<=4_000_000)return out.toByteArray()
                        }
                        throw IllegalArgumentException(L10n.t("PDF ist nach Kompression zu groß. Bitte weniger Seiten auswählen."))
                    } finally { combined.recycle() }
                }
            }
        } finally { file.delete() }
    }

}
