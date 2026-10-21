package cn.shinian.app

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.content.ComponentName
import android.content.Intent
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.os.Handler
import android.os.Looper
import android.os.Message
import android.os.Messenger
import android.os.ParcelFileDescriptor
import androidx.core.content.FileProvider
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.*
import cn.shinian.app.ui.memoir.MemoirPdf
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.text.PDFTextStripper
import com.tom_roush.pdfbox.text.TextPosition
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class MemoirPdfTest {
    @Test fun exportedPdfNeedsTemporaryReadGrantAndOpensCompletelyAcrossApplicationUids() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val receivingContext = instrumentation.context
        assertNotEquals(context.applicationInfo.uid, receivingContext.applicationInfo.uid)
        val folder = File(context.cacheDir, "shared/pdf-uri-${UUID.randomUUID()}").apply { mkdirs() }
        val file = File(folder, "shared.pdf")
        val pdf = PdfDocument()
        try {
            val page = pdf.startPage(PdfDocument.PageInfo.Builder(300, 200, 1).create())
            page.canvas.drawText("Temporary PDF sharing permission", 20f, 60f, Paint().apply { textSize = 15f })
            pdf.finishPage(page)
            file.outputStream().use(pdf::writeTo)
        } finally { pdf.close() }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        assertEquals("content", uri.scheme)
        data class Reply(val senderUid: Int, val data: android.os.Bundle)
        fun readInReceivingApplication(): Reply {
            val result = ArrayBlockingQueue<Reply>(1)
            val replyTo = Messenger(Handler(Looper.getMainLooper()) { message: Message ->
                result.offer(Reply(message.sendingUid, message.data)); true
            })
            context.startActivity(Intent().apply {
                component = ComponentName(receivingContext.packageName, PdfShareProbeActivity::class.java.name)
                data = uri
                putExtra("reply", replyTo)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
            return requireNotNull(result.poll(15, TimeUnit.SECONDS)) { "The separate-UID PDF receiver did not reply" }
        }
        try {
            val denied = readInReceivingApplication()
            assertEquals(receivingContext.applicationInfo.uid, denied.senderUid)
            assertEquals(SecurityException::class.java.name, denied.data.getString("error"))
            context.grantUriPermission(receivingContext.packageName, uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            val granted = readInReceivingApplication()
            assertEquals(receivingContext.applicationInfo.uid, granted.senderUid)
            assertEquals(receivingContext.applicationInfo.uid, granted.data.getInt("uid"))
            assertNull(granted.data.getString("error"))
            val received = requireNotNull(granted.data.getByteArray("bytes"))
            assertEquals("%PDF-", received.take(5).toByteArray().toString(Charsets.US_ASCII))
            assertArrayEquals(file.readBytes(), received)
        } finally {
            context.revokeUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            folder.deleteRecursively()
        }
    }

    @Test fun legalLongPhotoCoverKeepsEveryLineInsideThePage() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        PDFBoxResourceLoader.init(context)
        val settings = MemoirSettings("家".repeat(200), "回忆".repeat(150), "photo", listOf(MemoirCoverPhoto("cover")))
        val story = Memory("story", "往事", "这是一段供封面分页检查的虚构回忆。")
        val snapshot = MemoirSnapshot("person", "家人", 0, settings, listOf(story), "revision")
        val file = File(context.cacheDir, "shared/pdf-validation/long-cover.pdf").apply { parentFile?.mkdirs() }
        MemoirPdf.render(context, snapshot, settings, emptyMap(), file)
        PDDocument.load(file).use { pdf ->
            var bottom = 0f
            val reader = object : PDFTextStripper() {
                override fun processTextPosition(text: TextPosition) {
                    bottom = maxOf(bottom, text.yDirAdj + text.heightDir)
                    super.processTextPosition(text)
                }
            }.apply { startPage = 1; endPage = 1 }
            val content = reader.getText(pdf).replace(Regex("""\s+"""), "")
            assertTrue(content.contains(settings.title))
            assertTrue(content.contains(settings.subtitle))
            assertTrue("Cover text must not be clipped by page bounds", bottom < 590f)
        }
    }

    @Test fun chinesePaginationPhotosAndContentsRemainExportable() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        PDFBoxResourceLoader.init(context)
        val folder = File(context.cacheDir, "shared/pdf-validation").apply { mkdirs() }
        val photo = File(folder, "photo.jpg")
        Bitmap.createBitmap(720, 480, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.rgb(142, 162, 124))
            photo.outputStream().use { compress(Bitmap.CompressFormat.JPEG, 90, it) }; recycle()
        }
        val first = Memory("first", "院子里的夏天", ("那一年，我们坐在葡萄架下听外婆讲故事。\n".repeat(240)) + "最后一段仍然完整保留。",
            personIds = listOf("person"), memoryDate = "1980-06-01", media = listOf(Media("photo", "/api/v1/media/photo")))
        val last = Memory("second", "记不清年份的往事", "这段回忆的时间记不清，但故事依然值得珍藏。", time = InformationDimension("unknown"))
        val settings = MemoirSettings("日子里的回忆", "献给亲爱的家人", "photo", listOf(MemoirCoverPhoto("photo", "first")))
        val snapshot = MemoirSnapshot("person", "陈建国", 1, settings, listOf(last, first), "revision")
        val output = File(folder, "拾年排版验证.pdf")
        val count = MemoirPdf.render(context, snapshot, settings, mapOf("photo" to photo), output)
        assertTrue(count > 5)
        PDDocument.load(output).use { pdf ->
            assertEquals(count, pdf.numberOfPages)
            assertEquals(148 * 72f / 25.4f, pdf.getPage(0).mediaBox.width, .02f)
            assertEquals(210 * 72f / 25.4f, pdf.getPage(0).mediaBox.height, .02f)
            val text = PDFTextStripper().getText(pdf).replace(Regex("""\s+"""), "")
            assertTrue(text.contains("院子里的夏天"))
            assertTrue(text.contains("最后一段仍然完整保留。"))
            assertTrue(text.contains("这段回忆的时间记不清"))
            val links = pdf.getPage(1).annotations.filterIsInstance<PDAnnotationLink>()
            assertEquals(2, links.size)
            assertTrue(links.all { (it.border.getObject(2) as com.tom_roush.pdfbox.cos.COSNumber).floatValue() == 0f })
            assertNotNull(pdf.documentCatalog.documentOutline.firstChild)
        }
        ParcelFileDescriptor.open(output, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            PdfRenderer(descriptor).use { renderer ->
                assertEquals(count, renderer.pageCount)
                renderer.openPage(count - 1).use { page ->
                    val image = Bitmap.createBitmap(page.width, page.height, Bitmap.Config.ARGB_8888)
                    page.render(image, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    assertTrue(image.getPixel(10, 10) != Color.TRANSPARENT)
                    image.recycle()
                }
            }
        }
    }
}
