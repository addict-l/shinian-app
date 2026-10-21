package cn.shinian.app.ui.chat

import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.ui.theme.ShinianTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import android.content.res.Configuration
import android.graphics.Bitmap
import java.io.File

@RunWith(AndroidJUnit4::class)
class ChatPhotoComposerTest {
    @get:Rule val compose = createComposeRule()
    private fun photo(id: String, status: String = "selected") = SelectedPhoto(id,
        InstrumentationRegistry.getInstrumentation().context.assets.open("photo-review-summer.jpg").use { it.readBytes() }, status = status)

    @Test fun selectedPhotosUseSmallThumbnailsAndExplicitAccessibleRemoval() {
        var photos by mutableStateOf(listOf(photo("first"), photo("second", "uploaded"), photo("third", "failed")))
        compose.setContent { ShinianTheme {
            SelectedPhotoStrip(photos, enabled = true, onRemove = { id -> photos = photos.filterNot { it.id == id } })
        } }
        val scale = InstrumentationRegistry.getInstrumentation().targetContext.resources.displayMetrics.density
        val image = compose.onNodeWithTag("chat.selectedPhoto.first").fetchSemanticsNode().boundsInRoot
        val remove = compose.onNodeWithTag("chat.removePhoto.first").fetchSemanticsNode().boundsInRoot
        assertEquals(72f * scale, image.width, 1f)
        assertEquals(72f * scale, image.height, 1f)
        assertTrue(remove.width >= 48f * scale - 1f && remove.height >= 48f * scale - 1f)
        compose.onNodeWithText("已选择").assertDoesNotExist()
        compose.onNodeWithText("已上传").assertDoesNotExist()
        compose.onNodeWithText("上传失败").assertIsDisplayed()
        compose.onNodeWithTag("chat.removePhoto.second").performClick()
        compose.runOnIdle { assertEquals(listOf("first", "third"), photos.map { it.id }) }
        compose.onNodeWithTag("chat.selectedPhoto.second").assertDoesNotExist()
    }

    @Test fun selectedPhotosStayInsideComposerAndManagementSheetClosesWithDone() {
        val photos = listOf(photo("first"), photo("second"))
        var managing by mutableStateOf(false)
        var statusBarTop = 0
        compose.setContent { ShinianTheme {
            val context = LocalContext.current
            statusBarTop = WindowInsets.statusBars.getTop(LocalDensity.current)
            val dictation = remember { MandarinDictation(context) {} }
            Column(Modifier.fillMaxSize()) {
                Spacer(Modifier.weight(1f))
                NarrationComposer("", {}, care = false, enabled = true, sendEnabled = true, retrying = false,
                    dictation = dictation, onMic = {}, onSend = {}, hasPhotos = true,
                    selectedPhotos = { SelectedPhotoStrip(photos, true, {}) })
            }
            if (managing) ChatPhotoSheet("已选照片", "完成", { managing = false }) {
                SelectedPhotoStrip(photos, true, {})
            }
        } }
        compose.onNodeWithTag("chat.selectedPhotos").assert(hasAnyAncestor(hasTestTag("chat.composer")))
        compose.onNodeWithText("也可以写几句话…").assertIsDisplayed()
        compose.runOnIdle { managing = true }
        compose.onNodeWithText("已选照片").assertIsDisplayed()
        val close = compose.onNodeWithTag("chat.photos.close").fetchSemanticsNode().boundsInWindow
        assertTrue("The sheet action must sit below the system status bar", close.top >= statusBarTop - 1)
        captureManagementSheet()
        compose.onNodeWithTag("chat.photos.close").assertHasClickAction().performClick()
        compose.waitUntil(5_000) { !managing }
        compose.onNodeWithTag("chat.photos.close").assertDoesNotExist()
    }

    private fun captureManagementSheet() {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val config = context.resources.configuration
        val direction = if (config.orientation == Configuration.ORIENTATION_LANDSCAPE) "landscape" else "portrait"
        val output = File(context.getExternalFilesDir(null), "photo-responsive-screenshots").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try {
            File(output, "$direction-font-${config.fontScale}-width-${config.screenWidthDp}.png").outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
        } finally { bitmap.recycle() }
    }
}
