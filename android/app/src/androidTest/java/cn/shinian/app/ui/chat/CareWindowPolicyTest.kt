package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import android.graphics.Color as AndroidColor
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.Density
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.Person
import cn.shinian.app.ui.browse.CarePersonSelectionScreen
import cn.shinian.app.ui.care.CareBackdrop
import cn.shinian.app.ui.theme.JournalColors
import cn.shinian.app.ui.theme.ShinianImmersiveWindow
import cn.shinian.app.ui.theme.ShinianTheme
import cn.shinian.app.ui.theme.applyShinianWindowPolicy
import cn.shinian.app.ui.theme.shinianContentInsets
import java.io.File
import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToInt
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Actual edge-to-edge window and actual care page; no account, API or input-setting writes. */
@RunWith(AndroidJUnit4::class)
class CareWindowPolicyTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val person = Person(UUID.randomUUID().toString(), "本地窗口测试家人", "爷爷", "1940-01-01", 3)
    private var density = 1f
    private var fontScale = 0f
    private var selected = ""

    private fun showRealCarePage() {
        compose.runOnUiThread {
            compose.activity.enableEdgeToEdge()
            applyShinianWindowPolicy(compose.activity.window)
        }
        compose.setContent {
            ShinianTheme {
                val runtime = LocalDensity.current
                CompositionLocalProvider(LocalDensity provides Density(runtime.density, fontScale = 1f)) {
                    val ordinary = LocalDensity.current
                    SideEffect { density = ordinary.density; fontScale = ordinary.fontScale }
                    ShinianImmersiveWindow()
                    // Keep the same order as MainActivity: paper is drawn behind the safe inset.
                    Box(Modifier.fillMaxSize().testTag("window.root").background(JournalColors.Paper).shinianContentInsets()) {
                        CareBackdrop(Modifier.fillMaxSize().testTag("window.care.content")) {
                            CarePersonSelectionScreen(listOf(person), loading = false, error = null,
                                onSelect = { selected = it.id }, onAdd = {}, onRefresh = {}, onBack = {})
                        }
                    }
                }
            }
        }
        compose.waitForIdle()
        compose.onNodeWithText("选择家人").assertIsDisplayed()
        compose.onNodeWithText("这次讲谁的故事？").assertIsDisplayed()
        compose.onNodeWithTag("member.${person.id}").assertIsDisplayed()
    }

    private data class WindowGeometry(
        val statusTop: Int,
        val cutoutTop: Int,
        val safeLeft: Int,
        val safeRight: Int,
        val statusVisible: Boolean,
        val root: Rect,
        val content: Rect,
        val back: Rect,
    ) {
        val safeTop get() = max(statusTop, cutoutTop)
        fun json(): JSONObject = JSONObject()
            .put("status_top_px", statusTop).put("cutout_top_px", cutoutTop).put("safe_top_px", safeTop)
            .put("safe_left_px", safeLeft).put("safe_right_px", safeRight).put("status_visible", statusVisible)
            .put("root_bounds_px", root.json()).put("care_content_bounds_px", content.json()).put("back_bounds_px", back.json())
    }

    private fun geometry(): WindowGeometry {
        val insets = compose.runOnIdle {
            checkNotNull(ViewCompat.getRootWindowInsets(compose.activity.window.decorView)) { "Real window insets were not delivered" }
        }
        val status = insets.getInsets(WindowInsetsCompat.Type.statusBars())
        val cutout = insets.getInsets(WindowInsetsCompat.Type.displayCutout())
        return WindowGeometry(status.top, cutout.top, max(status.left, cutout.left), max(status.right, cutout.right),
            insets.isVisible(WindowInsetsCompat.Type.statusBars()),
            compose.onNodeWithTag("window.root").fetchSemanticsNode().boundsInRoot,
            compose.onNodeWithTag("window.care.content").fetchSemanticsNode().boundsInRoot,
            compose.onNodeWithTag("browse.back").fetchSemanticsNode().boundsInRoot)
    }

    private fun capture(name: String): Pair<Bitmap, File> {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "care-window-policy").apply { mkdirs() }
        val image = compose.onNodeWithTag("window.root").captureToImage().asAndroidBitmap()
        val file = File(folder, "$name.png")
        file.outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val systemImage = checkNotNull(instrumentation.uiAutomation.takeScreenshot()) { "System UI screenshot was not available" }
        try {
            File(folder, "$name-system.png").outputStream().use { systemImage.compress(Bitmap.CompressFormat.PNG, 100, it) }
        } finally { systemImage.recycle() }
        return image to file
    }

    @Test fun actualCarePageConsumesStatusAndCutoutSafeAreaExactlyOnce() {
        showRealCarePage()
        compose.onNodeWithTag("member.${person.id}").performClick()
        compose.runOnIdle { assertEquals(person.id, selected) }
        val measured = geometry()
        val (image, file) = capture("care-safe-area")
        try {
            val report = measured.json().put("font_scale", fontScale).put("density", density)
                .put("page", "CarePersonSelectionScreen").put("synthetic_people", 1).put("selected_person", selected)
                .put("screenshot", file.absolutePath).put("expected_toolbar_top_padding_dp", 6)
                .put("system_screenshot", File(file.parentFile, "${file.nameWithoutExtension}-system.png").absolutePath)
            File(file.parentFile, "care-safe-area.json").writeText(report.toString(2))
            assertEquals(1f, fontScale, 0f)
            assertTrue("Status bar must remain visible", measured.statusVisible)
            assertTrue("The real window must supply a top status/cutout safe area", measured.safeTop > 0)
            assertEquals("Safe top must be consumed exactly once", measured.root.top + measured.safeTop, measured.content.top, 1f)
            assertEquals("The actual toolbar must add only its own 6dp top padding", measured.content.top + 6f * density, measured.back.top, 1.5f)
            assertTrue("Toolbar overlaps status/cutout", measured.back.top >= measured.root.top + measured.safeTop)
            assertEquals("Horizontal safe inset must also be consumed once", measured.root.left + measured.safeLeft, measured.content.left, 1f)
            assertEquals(measured.root.right - measured.safeRight, measured.content.right, 1f)
        } finally { image.recycle() }
    }

    @Test fun actualCareBackdropMeetsTheStatusRegionWithoutAnRgbSeam() {
        showRealCarePage()
        val measured = geometry()
        val (image, file) = capture("care-status-seam")
        try {
            val boundary = (measured.content.top - measured.root.top).roundToInt()
            check(boundary in 1 until image.height) { "The screenshot must include both sides of the real safe-area boundary" }
            val expectedPaper = JournalColors.Paper.toArgb()
            val samples = JSONArray()
            var maxDelta = 0
            var maxPaperDelta = 0
            for (fraction in listOf(.25f, .5f, .75f, .9f)) {
                val x = ((image.width - 1) * fraction).roundToInt()
                val upper = image.getPixel(x, boundary - 1)
                val lower = image.getPixel(x, boundary)
                val delta = rgbDelta(upper, lower)
                val paperDelta = rgbDelta(upper, expectedPaper)
                maxDelta = max(maxDelta, delta.maxOrNull() ?: 0)
                maxPaperDelta = max(maxPaperDelta, paperDelta.maxOrNull() ?: 0)
                samples.put(JSONObject().put("x_fraction", fraction).put("x_px", x)
                    .put("status_y_px", boundary - 1).put("care_y_px", boundary)
                    .put("status_rgb", rgb(upper)).put("care_rgb", rgb(lower))
                    .put("absolute_rgb_delta", JSONArray(delta)).put("status_to_paper_delta", JSONArray(paperDelta)))
            }
            val report = measured.json().put("font_scale", fontScale).put("density", density)
                .put("page", "CarePersonSelectionScreen").put("synthetic_people", 1)
                .put("screenshot", file.absolutePath).put("image_width_px", image.width).put("image_height_px", image.height)
                .put("system_screenshot", File(file.parentFile, "${file.nameWithoutExtension}-system.png").absolutePath)
                .put("expected_paper_rgb", rgb(expectedPaper)).put("max_channel_delta", maxDelta)
                .put("max_status_to_paper_delta", maxPaperDelta).put("allowed_channel_delta", 2).put("samples", samples)
            // Persist the failing pixels before assertions so the missing transition is reviewable.
            File(file.parentFile, "care-status-seam.json").writeText(report.toString(2))
            assertEquals(1f, fontScale, 0f)
            assertTrue("Status to CareBackdrop boundary has an RGB seam: max delta $maxDelta; see ${file.absolutePath}", maxDelta <= 2)
        } finally { image.recycle() }
    }
}

private fun Rect.json(): JSONArray = JSONArray(listOf(left, top, right, bottom))
private fun rgb(value: Int): JSONArray = JSONArray(listOf(AndroidColor.red(value), AndroidColor.green(value), AndroidColor.blue(value)))
private fun rgbDelta(a: Int, b: Int): List<Int> = listOf(abs(AndroidColor.red(a) - AndroidColor.red(b)), abs(AndroidColor.green(a) - AndroidColor.green(b)), abs(AndroidColor.blue(a) - AndroidColor.blue(b)))
