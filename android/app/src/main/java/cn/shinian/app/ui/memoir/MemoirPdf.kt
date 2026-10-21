package cn.shinian.app.ui.memoir

import android.content.Context
import android.graphics.*
import android.graphics.pdf.PdfDocument
import android.text.*
import android.text.style.AbsoluteSizeSpan
import android.text.style.ForegroundColorSpan
import android.text.style.TypefaceSpan
import androidx.core.content.res.ResourcesCompat
import cn.shinian.app.R
import cn.shinian.app.data.*
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSInteger
import com.tom_roush.pdfbox.cos.COSStream
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionGoTo
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDPageFitDestination
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.outline.PDDocumentOutline
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.outline.PDOutlineItem
import java.io.File
import java.text.Normalizer
import java.math.BigInteger
import java.util.Collections
import java.util.IdentityHashMap
import kotlin.math.*

/** A5, selectable Chinese text, real pagination, full photos, linked contents. */
object MemoirPdf {
    const val WIDTH = 420
    const val HEIGHT = 595
    private const val MARGIN = 38f
    private const val TOP = 46f
    private const val CONTENT_HEIGHT = HEIGHT - 106
    private val ink = Color.rgb(61, 48, 38)
    private val paper = Color.rgb(250, 245, 235)
    private val accent = Color.rgb(179, 97, 61)

    private data class TextPart(val layout: StaticLayout, val first: Int, val end: Int) {
        val height: Int get() = layout.getLineBottom(end - 1) - layout.getLineTop(first)
    }
    private data class ContentPage(val text: TextPart? = null, val photos: List<String> = emptyList())
    private data class Chapter(val title: String, val start: Int)
    private data class TocRow(val chapter: Chapter, val height: Int)

    fun render(context: Context, snapshot: MemoirSnapshot, settings: MemoirSettings, photos: Map<String, File>, output: File): Int {
        val pages = mutableListOf<ContentPage>()
        val chapters = mutableListOf<Chapter>()
        orderedStories(settings, snapshot.stories).forEach { story ->
            chapters.add(Chapter(story.title, pages.size))
            val string = SpannableStringBuilder()
            string.append(story.title).append("\n")
            string.setSpan(AbsoluteSizeSpan(22), 0, string.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            val metaStart = string.length
            string.append(listOf(story.dateLabel, story.place.value.orEmpty()).filter { it.isNotBlank() }.joinToString(" · ")).append("\n\n")
            string.setSpan(AbsoluteSizeSpan(11), metaStart, string.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            string.setSpan(ForegroundColorSpan(accent), metaStart, string.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            string.append(story.content)
            val layout = layout(string, settings.textSize.toFloat(), WIDTH - MARGIN * 2)
            val textParts = paginate(layout)
            val images = selectedPhotos(settings, story).map { it.id }.toMutableList()
            textParts.forEachIndexed { index, part ->
                if (index == textParts.lastIndex && images.isNotEmpty() && CONTENT_HEIGHT - part.height >= 160) {
                    pages.add(ContentPage(part, listOf(images.removeAt(0))))
                } else pages.add(ContentPage(part))
            }
            images.chunked(2).forEach { pages.add(ContentPage(photos = it)) }
        }
        val tocPages = mutableListOf(mutableListOf<TocRow>())
        var used = 0
        chapters.forEach { chapter ->
            val h = max(32, layout(chapter.title, 12f, WIDTH - MARGIN * 2 - 42).height + 14)
            if (used + h > HEIGHT - 150 && tocPages.last().isNotEmpty()) { tocPages.add(mutableListOf()); used = 0 }
            tocPages.last().add(TocRow(chapter, h)); used += h
        }
        val document = PdfDocument()
        val source = File(output.parentFile, "unlinked.pdf")
        try {
            var pageNumber = 0
            fun page(draw: (Canvas) -> Unit) {
                val value = document.startPage(PdfDocument.PageInfo.Builder(WIDTH, HEIGHT, ++pageNumber).create())
                draw(value.canvas); document.finishPage(value)
            }
            page { drawCover(context, it, settings, snapshot.personName, photos) }
            tocPages.forEachIndexed { index, rows ->
                page { canvas ->
                    canvas.drawColor(paper)
                    drawText(canvas, if (index == 0) "目录" else "目录 · 续", MARGIN, 42f, WIDTH - MARGIN * 2, 26f)
                    var y = 108f
                    rows.forEach { row ->
                        drawText(canvas, row.chapter.title, MARGIN, y, WIDTH - MARGIN * 2 - 42, 12f)
                        drawText(canvas, "${row.chapter.start + 1}", WIDTH - MARGIN - 35, y, 35f, 11f, accent, Layout.Alignment.ALIGN_OPPOSITE)
                        y += row.height
                    }
                }
            }
            pages.forEachIndexed { index, content ->
                page { canvas ->
                    canvas.drawColor(paper)
                    val part = content.text
                    if (part != null) {
                        canvas.save()
                        canvas.clipRect(MARGIN, TOP, WIDTH - MARGIN, TOP + part.height)
                        canvas.translate(MARGIN, TOP - part.layout.getLineTop(part.first))
                        part.layout.draw(canvas); canvas.restore()
                    }
                    if (content.photos.isNotEmpty()) {
                        val photoTop = if (part != null) TOP + part.height + 18 else TOP
                        val available = HEIGHT - 68 - photoTop
                        content.photos.forEachIndexed { i, id ->
                            val rect = RectF(MARGIN, photoTop + i * (available / content.photos.size), WIDTH - MARGIN,
                                photoTop + (i + 1) * (available / content.photos.size) - 12)
                            drawPhoto(canvas, photos.getValue(id), rect, crop = null)
                        }
                    }
                    drawText(canvas, "${index + 1}", MARGIN, HEIGHT - 37f, WIDTH - MARGIN * 2, 10f, accent, Layout.Alignment.ALIGN_CENTER)
                }
            }
            source.outputStream().use(document::writeTo)
            PDFBoxResourceLoader.init(context.applicationContext)
            PDDocument.load(source).use { pdf ->
                // Skia can map a shared Chinese glyph to a Kangxi radical alias.
                // Keep its appearance, but make copy/search return the ordinary character.
                val processed = Collections.newSetFromMap(IdentityHashMap<COSStream, Boolean>())
                pdf.pages.forEach { pdfPage ->
                    pdfPage.resources.fontNames.forEach { fontName ->
                        val stream = pdfPage.resources.getFont(fontName).cosObject.getDictionaryObject(COSName.TO_UNICODE) as? COSStream
                        if (stream != null && processed.add(stream)) {
                            val original = stream.createInputStream().use { it.readBytes().toString(Charsets.US_ASCII) }
                            val corrected = canonicalizeUnicodeMappings(original)
                            if (corrected != original) stream.createOutputStream(COSName.FLATE_DECODE).use { it.write(corrected.toByteArray(Charsets.US_ASCII)) }
                        }
                    }
                }
                val contentsOffset = 1 + tocPages.size
                val outline = PDDocumentOutline()
                pdf.documentCatalog.documentOutline = outline
                pdf.pages.forEach { it.mediaBox = PDRectangle(148 * 72f / 25.4f, 210 * 72f / 25.4f) }
                chapters.forEach { chapter ->
                    val bookmark = PDOutlineItem()
                    bookmark.title = chapter.title
                    bookmark.setDestination(pdf.getPage(contentsOffset + chapter.start))
                    outline.addLast(bookmark)
                }
                tocPages.forEachIndexed { pageIndex, rows ->
                    var y = 108f
                    rows.forEach { row ->
                        val link = PDAnnotationLink()
                        link.border = COSArray().apply { repeat(3) { add(COSInteger.ZERO) } }
                        link.rectangle = PDRectangle(MARGIN, HEIGHT - y - row.height, WIDTH - MARGIN * 2, row.height.toFloat())
                        val destination = PDPageFitDestination().apply { page = pdf.getPage(contentsOffset + row.chapter.start) }
                        link.action = PDActionGoTo().apply { this.destination = destination }
                        pdf.getPage(pageIndex + 1).annotations.add(link)
                        y += row.height
                    }
                }
                outline.openNode()
                pdf.documentInformation.title = settings.title
                pdf.documentInformation.author = "拾年 · ${snapshot.personName}"
                pdf.save(output)
                return pdf.numberOfPages
            }
        } finally { document.close(); source.delete() }
    }

    internal fun canonicalizeUnicodeMappings(source: String): String {
        fun canonical(hex: String): String {
            if (hex.length % 4 != 0) return hex
            val text = hex.chunked(4).map { it.toInt(16).toChar() }.joinToString("")
            val normalized = text.map { character ->
                if (character.code in 0x2F00..0x2FD5) Normalizer.normalize(character.toString(), Normalizer.Form.NFKC) else character.toString()
            }.joinToString("")
            return normalized.map { "%04X".format(it.code) }.joinToString("")
        }
        val pair = Regex("""<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>""")
        var result = Regex("""(?s)(\d+)\s+beginbfchar(.*?)endbfchar""").replace(source) { block ->
            val pairs = pair.findAll(block.groupValues[2]).map { match -> "<${match.groupValues[1]}> <${canonical(match.groupValues[2])}>" }.toList()
            "${pairs.size} beginbfchar\n${pairs.joinToString("\n")}\nendbfchar"
        }
        result = Regex("""(?s)(\d+)\s+beginbfrange(.*?)endbfrange""").replace(result) { block ->
            val range = Regex("""<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<([0-9A-Fa-f]+)>|\[([^]]*)])""")
            val pairs = mutableListOf<String>()
            range.findAll(block.groupValues[2]).forEach { match ->
                val start = match.groupValues[1].toInt(16)
                val end = match.groupValues[2].toInt(16)
                require(end - start in 0..65535) { "PDF Unicode range is invalid" }
                val array = Regex("""<([0-9A-Fa-f]+)>""").findAll(match.groupValues[5]).map { it.groupValues[1] }.toList()
                (start..end).forEach { code ->
                    val target = if (array.isNotEmpty()) array[code - start] else {
                        BigInteger(match.groupValues[4], 16).add(BigInteger.valueOf((code - start).toLong())).toString(16).padStart(match.groupValues[4].length, '0')
                    }
                    pairs.add("<${code.toString(16).padStart(match.groupValues[1].length, '0')}> <${canonical(target)}>")
                }
            }
            pairs.chunked(100).joinToString("\n") { "${it.size} beginbfchar\n${it.joinToString("\n")}\nendbfchar" }
        }
        return result
    }

    private fun paginate(layout: StaticLayout): List<TextPart> {
        val pages = mutableListOf<TextPart>()
        var first = 0
        while (first < layout.lineCount) {
            var end = first + 1
            val top = layout.getLineTop(first)
            while (end < layout.lineCount && layout.getLineBottom(end) - top <= CONTENT_HEIGHT) end++
            pages.add(TextPart(layout, first, end)); first = end
        }
        return pages
    }

    private fun layout(text: CharSequence, size: Float, width: Float, color: Int = ink, align: Layout.Alignment = Layout.Alignment.ALIGN_NORMAL, font: Typeface = Typeface.DEFAULT): StaticLayout {
        val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { textSize = size; this.color = color; typeface = font }
        return StaticLayout.Builder.obtain(text, 0, text.length, paint, width.toInt().coerceAtLeast(1))
            .setAlignment(align).setLineSpacing(0f, 1.4f).setIncludePad(false).build()
    }

    private fun drawText(canvas: Canvas, text: CharSequence, x: Float, y: Float, width: Float, size: Float, color: Int = ink, align: Layout.Alignment = Layout.Alignment.ALIGN_NORMAL, font: Typeface = Typeface.DEFAULT) {
        canvas.save(); canvas.translate(x, y); layout(text, size, width, color, align, font).draw(canvas); canvas.restore()
    }

    fun coverBitmap(context: Context, settings: MemoirSettings, name: String, photos: Map<String, File>): Bitmap {
        val image = Bitmap.createBitmap(WIDTH, HEIGHT, Bitmap.Config.ARGB_8888)
        drawCover(context, Canvas(image), settings, name, photos)
        return image
    }

    private fun drawCover(context: Context, canvas: Canvas, settings: MemoirSettings, name: String, photos: Map<String, File>) {
        val elegant = settings.coverTemplate == "text"
        canvas.drawColor(if (elegant) ink else if (settings.coverTemplate == "collage") Color.rgb(230, 237, 219) else Color.rgb(245, 230, 212))
        val textColor = if (elegant) paper else ink
        val accentColor = if (elegant) Color.rgb(199, 176, 153) else accent
        val chosen = settings.coverPhotos.take(coverLimit(settings))
        val area = RectF(46f, 38f, WIDTH - 40f, 353f)
        var top = if (elegant) 124f else 377f
        val title = settings.title.replace(Regex("""\s+"""), " ")
        val subtitle = settings.subtitle.replace(Regex("""\s+"""), " ")
        val font = ResourcesCompat.getFont(context, R.font.noto_serif_sc) ?: Typeface.SERIF
        var titleSize = 38f
        var subSize = 22f
        fun textHeight(): Int = layout(title, titleSize, area.width(), font = font).height +
            (if (subtitle.isBlank()) 0 else layout(subtitle, subSize, area.width(), font = font).height + 10)
        while (textHeight() > HEIGHT - 78 - top && (titleSize > 14 || subSize > 10)) {
            titleSize = (titleSize - 1).coerceAtLeast(14f); subSize = (subSize - .5f).coerceAtLeast(10f)
        }
        if (!elegant && textHeight() > HEIGHT - 78 - top) {
            // Preserve legal long titles by giving text more room on photo covers.
            top = (HEIGHT - 78f - textHeight()).coerceAtLeast(187f)
            area.bottom = top - 24
        }
        while (textHeight() > HEIGHT - 78 - top && (titleSize > 10 || subSize > 8)) {
            titleSize = (titleSize - .5f).coerceAtLeast(10f); subSize = (subSize - .5f).coerceAtLeast(8f)
        }
        require(textHeight() <= HEIGHT - 78 - top) { "封面文字太长，请缩短书名或副标题，或改用素雅文字封面。" }
        if (!elegant) {
            val count = chosen.size.coerceAtLeast(1)
            repeat(count) { index ->
                val rect = when {
                    count == 1 -> area
                    count == 2 -> RectF(area.left + index * (area.width() + 8) / 2, area.top, area.left + index * (area.width() + 8) / 2 + (area.width() - 8) / 2, area.bottom)
                    index == 0 -> RectF(area.left, area.top, area.left + area.width() * .58f - 4, area.bottom)
                    else -> RectF(area.left + area.width() * .58f + 4, area.top + (index - 1) * (area.height() + 8) / 2, area.right,
                        area.top + (index - 1) * (area.height() + 8) / 2 + (area.height() - 8) / 2)
                }
                val photo = chosen.getOrNull(index)
                val file = photo?.let { photos[it.id] }
                canvas.save()
                canvas.clipPath(Path().apply { addRoundRect(rect, 14f, 14f, Path.Direction.CW) })
                if (file != null) drawPhoto(canvas, file, rect, photo)
                else {
                    canvas.drawColor(Color.rgb(232, 214, 191))
                    drawText(canvas, name.take(1), rect.left, rect.centerY() - 40, rect.width(), 60f, accentColor, Layout.Alignment.ALIGN_CENTER)
                }
                canvas.restore()
            }
        }
        val titleHeight = layout(title, titleSize, area.width(), font = font).height
        drawText(canvas, title, area.left, top, area.width(), titleSize, textColor, font = font)
        if (subtitle.isNotBlank()) drawText(canvas, subtitle, area.left, top + titleHeight + 10, area.width(), subSize, accentColor, font = font)
        drawText(canvas, "拾 年 · $name", area.left, HEIGHT - 48f, area.width(), 16f, accentColor)
    }

    private fun drawPhoto(canvas: Canvas, file: File, rect: RectF, crop: MemoirCoverPhoto?) {
        val image = BitmapFactory.decodeFile(file.absolutePath) ?: error("照片无法读取，请重试。")
        try {
            val scale = if (crop == null) min(rect.width() / image.width, rect.height() / image.height)
                else max(rect.width() / image.width, rect.height() / image.height) * crop.zoom.toFloat()
            val w = image.width * scale; val h = image.height * scale
            val x = rect.centerX() - w / 2 + (crop?.x?.toFloat() ?: 0f) * (w - rect.width()) / 2
            val y = rect.centerY() - h / 2 + (crop?.y?.toFloat() ?: 0f) * (h - rect.height()) / 2
            canvas.save(); canvas.clipRect(rect)
            canvas.drawBitmap(image, null, RectF(x, y, x + w, y + h), Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
            canvas.restore()
        } finally { image.recycle() }
    }
}
