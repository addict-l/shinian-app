package cn.shinian.app.ui.memoir

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.IntSize
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.MemoirSettings
import cn.shinian.app.ui.theme.ShinianTheme
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionGoTo
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDPageFitDestination
import java.io.File
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Uses actual PDF annotations, pointer gestures and scrolling, rather than fake reader callbacks. */
@RunWith(AndroidJUnit4::class)
class MemoirReaderInteractionTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var file: File

    @Before fun createLinkedBook() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        PDFBoxResourceLoader.init(context)
        file = File(context.cacheDir, "reader-interaction-${System.nanoTime()}.pdf")
        PDDocument().use { document ->
            repeat(3) { document.addPage(PDPage(PDRectangle(420f, 595f))) }
            val destination = PDPageFitDestination().apply { page = document.getPage(2) }
            val link = PDAnnotationLink().apply {
                rectangle = PDRectangle(105f, 416.5f, 210f, 59.5f)
                action = PDActionGoTo().apply { this.destination = destination }
            }
            document.getPage(0).annotations.add(link)
            document.save(file)
        }
    }

    @After fun removeBook() { if (::file.isInitialized) file.delete() }

    @Test fun actualPdfLinkRemainsClickableAfterZoomAndPan() {
        val pages = readBookPages(file)
        assertEquals(3, pages.size)
        assertEquals(2, pages[0].links.single().target)
        val size = IntSize(420, 595)
        val original = Offset(210f, 148.75f)
        assertEquals(2, pages[0].linkAt(original, size, 1f, Offset.Zero))
        val center = Offset(210f, 297.5f)
        val pan = Offset(30f, 40f)
        val transformed = (original - center) * 2f + center + pan
        assertEquals(2, pages[0].linkAt(transformed, size, 2f, pan))
        assertNull(pages[0].linkAt(Offset(10f, 10f), size, 1f, Offset.Zero))
    }

    @Test fun readerSupportsPinchDoubleTapSingleFingerScrollAndRealTocNavigation() {
        compose.setContent {
            ShinianTheme { MemoirPdfPreview(BookPreview(file, "test", MemoirSettings("测试回忆录"), 3), Modifier.fillMaxSize()) }
        }
        val first = compose.onNodeWithTag("memoir.pdf.page.0")
        compose.waitUntil(10_000) {
            runCatching { first.fetchSemanticsNode().config[SemanticsActions.CustomActions].any { it.label == "跳转到第 3 页" } }.getOrDefault(false)
        }
        first.performTouchInput {
            pinch(center + Offset(-30f, 0f), center + Offset(30f, 0f), center + Offset(-110f, 0f), center + Offset(110f, 0f))
        }
        first.assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "已放大，可单指移动，双击还原"))
        first.performTouchInput { doubleClick(center) }
        first.assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "原始大小，可上下翻阅，双指缩放"))
        first.performTouchInput { swipeUp() }
        compose.waitUntil(10_000) {
            runCatching {
                compose.onNodeWithTag("memoir-page-count").fetchSemanticsNode().config[SemanticsProperties.Text]
                    .any { it.text == "第 2 / 3 页" || it.text == "第 3 / 3 页" }
            }.getOrDefault(false)
        }
        compose.onNodeWithTag("memoir-pdf").performScrollToIndex(0)
        first.performTouchInput { click(Offset(width * .5f, height * .25f)) }
        compose.waitUntil(10_000) { runCatching { compose.onNodeWithTag("memoir.pdf.page.2").assertIsDisplayed(); true }.getOrDefault(false) }
        compose.onNodeWithTag("memoir.pdf.page.2").assertIsDisplayed()
    }
}
