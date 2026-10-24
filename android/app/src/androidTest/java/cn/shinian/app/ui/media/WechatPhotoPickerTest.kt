package cn.shinian.app.ui.media

import android.Manifest
import android.content.ContentValues
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.media.DevicePhoto
import cn.shinian.app.media.DevicePhotoLibrary
import cn.shinian.app.ui.theme.ShinianTheme
import java.io.File
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the production picker against photos owned exclusively by this test. */
@RunWith(AndroidJUnit4::class)
class WechatPhotoPickerTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val inserted = mutableListOf<Uri>()
    private lateinit var mainPhotos: List<DevicePhoto>
    private lateinit var otherPhotos: List<DevicePhoto>
    private lateinit var mainAlbum: String
    private lateinit var otherAlbum: String
    private var confirmed: List<Uri>? = null
    private var dismissCount = 0
    private var systemPickerCount = 0

    @Before fun prepareRealPhotoLibraryAndRequestedOrientation() {
        assumeTrue("Scoped MediaStore fixture requires API 29 or later", Build.VERSION.SDK_INT >= 29)
        val argument = InstrumentationRegistry.getArguments().getString("pickerOrientation", "portrait")
        val landscape = argument == "landscape"
        val desiredConfiguration = if (landscape) Configuration.ORIENTATION_LANDSCAPE else Configuration.ORIENTATION_PORTRAIT
        val desiredActivity = if (landscape) ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        compose.activityRule.scenario.onActivity { it.requestedOrientation = desiredActivity }
        compose.waitUntil(15_000) { compose.activity.resources.configuration.orientation == desiredConfiguration }
        assertEquals("The Activity itself must be in the requested orientation", desiredConfiguration,
            compose.activity.resources.configuration.orientation)

        val permission = if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE
        instrumentation.uiAutomation.grantRuntimePermission(context.packageName, permission)

        removeInterruptedFixtures()

        val runId = UUID.randomUUID().toString()
        val mainUris = (0 until 12).map { insertPhoto("$runId/示例照片", it) }
        val otherUris = (0 until 4).map { insertPhoto("$runId/生活片段", it + 12) }
        val indexed = runBlocking { DevicePhotoLibrary(context).load() }.associateBy { it.uri }
        mainPhotos = mainUris.map { requireNotNull(indexed[it]) { "The production library must find each inserted photo" } }
            .sortedByDescending { it.id }
        otherPhotos = otherUris.map { requireNotNull(indexed[it]) }.sortedByDescending { it.id }
        mainAlbum = mainPhotos.first().albumId
        otherAlbum = otherPhotos.first().albumId
        assertEquals(1, mainPhotos.map { it.albumId }.distinct().size)
        assertEquals(1, otherPhotos.map { it.albumId }.distinct().size)
        assertNotEquals(mainAlbum, otherAlbum)
    }

    @After fun removeOnlyFixturePhotos() {
        // Keep all unrelated user and earlier validation photos intact.
        var firstFailure: Throwable? = null
        inserted.forEach { uri ->
            try { context.contentResolver.delete(uri, null, null) }
            catch (failure: Throwable) {
                if (firstFailure == null) firstFailure = failure else firstFailure!!.addSuppressed(failure)
            }
        }
        inserted.clear()
        firstFailure?.let { throw it }
    }

    private fun removeInterruptedFixtures() {
        val path = MediaStore.Images.Media.RELATIVE_PATH
        val where = "$path LIKE ? AND ${MediaStore.Images.Media.DISPLAY_NAME} LIKE ? AND ${MediaStore.Images.Media.OWNER_PACKAGE_NAME} = ?"
        val uris = mutableListOf<Uri>()
        context.contentResolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            arrayOf(MediaStore.Images.Media._ID, path), where,
            arrayOf("Pictures/拾年选图验收/%", "picker-review-%", context.packageName), null)?.use { cursor ->
            while (cursor.moveToNext()) {
                if (Regex("Pictures/拾年选图验收/[0-9a-f-]{36}/(示例照片|生活片段)/").matches(cursor.getString(1)))
                    uris += android.content.ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cursor.getLong(0))
            }
        }
        uris.forEach { context.contentResolver.delete(it, null, null) }
    }

    @Test fun fourColumnGridKeepsSelectionOrderReindexesRemovalAndEnforcesTheLimit() {
        launchPicker(maximum = 3)
        openAlbum(mainAlbum, screenshotName = "albums")
        screenshot("grid")
        assertFourSquareColumns()

        // Select a deliberate order that differs from display order.
        val first = mainPhotos[2]
        val second = mainPhotos[0]
        val third = mainPhotos[1]
        val fourth = mainPhotos[3]
        select(first)
        select(second)
        select(third)
        assertSelection(first, 1)
        assertSelection(second, 2)
        assertSelection(third, 3)
        screenshot("selected")

        select(fourth)
        assertUnselected(fourth)
        assertSelection(third, 3)
        assertNull(confirmed)

        select(second)
        assertUnselected(second)
        assertSelection(first, 1)
        assertSelection(third, 2)
        select(fourth)
        assertSelection(fourth, 3)

        compose.onNodeWithTag("picker.done").assertIsEnabled().performClick()
        compose.waitUntil(5_000) { confirmed != null }
        compose.runOnIdle {
            assertEquals(listOf(first.uri, third.uri, fourth.uri), confirmed)
            assertEquals(0, dismissCount)
            assertEquals(0, systemPickerCount)
        }
    }

    @Test fun albumFilteringAndBothPreviewRoutesPreserveSelectionUntilExplicitConfirmation() {
        launchPicker(maximum = 5)
        compose.onNodeWithTag("picker.done").assertIsNotEnabled()
        compose.onNodeWithTag("picker.preview").assertIsNotEnabled()
        openAlbum(mainAlbum)
        val first = mainPhotos[0]
        val second = mainPhotos[1]
        select(first)
        select(second)

        // Tapping a picture opens it without changing the selected set.
        compose.onNodeWithTag("picker.photo.${mainPhotos[2].id}").performClick()
        awaitPreview()
        screenshot("preview")
        compose.onNodeWithTag("picker.previewImage").performTouchInput { swipeLeft() }
        compose.waitUntil(10_000) { compose.onAllNodesWithText("4 / 12").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("picker.previewImage").assertContentDescriptionEquals(mainPhotos[3].displayName)
        closePreview()
        assertSelection(first, 1)
        assertSelection(second, 2)
        assertUnselected(mainPhotos[2])

        // The footer preview is the selected collection in the existing order.
        compose.onNodeWithTag("picker.preview").assertIsEnabled().performClick()
        awaitPreview()
        screenshot("selected-preview")
        compose.onNodeWithTag("picker.previewImage").performTouchInput { swipeLeft() }
        compose.waitUntil(10_000) { compose.onAllNodesWithText("2 / 2").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("picker.previewImage").assertContentDescriptionEquals(second.displayName)
        closePreview()
        assertSelection(first, 1)
        assertSelection(second, 2)

        openAlbum(otherAlbum)
        compose.onNodeWithTag("picker.photo.${otherPhotos[0].id}").assertExists()
        compose.onNodeWithTag("picker.photo.${first.id}").assertDoesNotExist()
        select(otherPhotos[0])
        assertSelection(otherPhotos[0], 3)

        openAlbum(mainAlbum)
        compose.onNodeWithTag("picker.photo.${otherPhotos[0].id}").assertDoesNotExist()
        assertSelection(first, 1)
        assertSelection(second, 2)
        compose.onNodeWithTag("picker.close").performClick()
        compose.waitUntil(5_000) { dismissCount == 1 }
        compose.runOnIdle {
            assertNull("Closing the picker must never confirm or upload selected images", confirmed)
            assertEquals(0, systemPickerCount)
        }
        compose.onNodeWithTag("picker.root").assertDoesNotExist()
    }

    private fun launchPicker(maximum: Int) {
        var showing by mutableStateOf(true)
        compose.setContent { ShinianTheme {
            if (showing) WechatPhotoPicker(
                maxSelection = maximum,
                onDismiss = { dismissCount++; showing = false },
                onConfirm = { confirmed = it; showing = false },
                onSystemPicker = { systemPickerCount++ },
            )
        } }
        compose.waitUntil(15_000) { compose.onAllNodesWithTag("picker.album").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("picker.permission").assertDoesNotExist()
        if (Build.VERSION.SDK_INT >= 30) {
            var safeTop = 0
            compose.waitUntil(5_000) {
                var ready = false
                compose.runOnUiThread {
                    val windows = android.view.inspector.WindowInspector.getGlobalWindowViews()
                        .filter { it.isShown && it !== compose.activity.window.decorView }
                    ready = windows.any { view ->
                        val insets = androidx.core.view.ViewCompat.getRootWindowInsets(view)
                        val appearance = view.windowInsetsController?.systemBarsAppearance
                        if (insets?.isVisible(androidx.core.view.WindowInsetsCompat.Type.statusBars()) == true &&
                            appearance != null && appearance and android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS == 0) {
                            safeTop = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.statusBars() or
                                androidx.core.view.WindowInsetsCompat.Type.displayCutout()).top
                            true
                        } else false
                    }
                }
                ready
            }
            val album = compose.onNodeWithTag("picker.album").fetchSemanticsNode().boundsInRoot
            assertTrue("Photo picker controls stay below the camera with light status icons", album.top >= safeTop)
        }
    }

    private fun openAlbum(id: String, screenshotName: String? = null) {
        compose.onNodeWithTag("picker.album").performClick()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("picker.album.$id").fetchSemanticsNodes().isNotEmpty() }
        screenshotName?.let(::screenshot)
        compose.onNodeWithTag("picker.albums").performScrollToNode(hasTestTag("picker.album.$id"))
        compose.onNodeWithTag("picker.album.$id").performClick()
        val first = if (id == mainAlbum) mainPhotos[0] else otherPhotos[0]
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("picker.photo.${first.id}").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("picker.grid").assertExists()
    }

    private fun select(photo: DevicePhoto) {
        compose.onNodeWithTag("picker.grid").performScrollToNode(hasTestTag("picker.photo.${photo.id}"))
        val target = compose.onNodeWithTag("picker.select.${photo.id}")
        val size = target.getUnclippedBoundsInRoot()
        assertTrue("Photo selection must provide a 48 dp target", (size.right - size.left).value >= 47.9f && (size.bottom - size.top).value >= 47.9f)
        target.assertHasClickAction().performClick()
        compose.waitForIdle()
    }

    private fun assertSelection(photo: DevicePhoto, order: Int) {
        compose.onNodeWithTag("picker.select.${photo.id}")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.ToggleableState, ToggleableState.On))
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "已选择，第 $order 张"))
        compose.onNode(hasText(order.toString()) and
            (hasTestTag("picker.select.${photo.id}") or hasAnyAncestor(hasTestTag("picker.select.${photo.id}"))),
            useUnmergedTree = true).assertExists()
    }

    private fun assertUnselected(photo: DevicePhoto) {
        compose.onNodeWithTag("picker.select.${photo.id}")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.ToggleableState, ToggleableState.Off))
    }

    private fun assertFourSquareColumns() {
        val firstRow = mainPhotos.take(4).map { photo ->
            compose.onNodeWithTag("picker.photo.${photo.id}").assertExists().getUnclippedBoundsInRoot()
        }.sortedBy { it.left.value }
        firstRow.forEach { assertEquals("A grid picture must be square", (it.right - it.left).value, (it.bottom - it.top).value, .7f) }
        firstRow.drop(1).forEachIndexed { index, bounds ->
            assertEquals(firstRow[0].top.value, bounds.top.value, .7f)
            assertTrue("Four independent photo columns must share the same row", bounds.left > firstRow[index].left)
        }
        val grid = compose.onNodeWithTag("picker.grid").getUnclippedBoundsInRoot()
        assertTrue("The four thumbnails should fill the grid width", firstRow.sumOf { (it.right - it.left).value.toDouble() } >= (grid.right - grid.left).value - 16f)
    }

    private fun awaitPreview() {
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("picker.previewImage").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("picker.preview.close").assertIsDisplayed()
    }

    private fun closePreview() {
        compose.onNodeWithTag("picker.preview.close").performClick()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("picker.preview.close").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("picker.grid").assertExists()
    }

    private fun insertPhoto(album: String, index: Int): Uri {
        val fileName = "picker-review-${UUID.randomUUID()}-$index.jpg"
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, fileName)
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/拾年选图验收/$album/")
            put(MediaStore.Images.Media.DATE_TAKEN, System.currentTimeMillis() + index * 1_000L)
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        inserted += uri
        val asset = if (index % 2 == 0) "photo-review-summer.jpg" else "photo-review-dinner.jpg"
        instrumentation.context.assets.open(asset).use { input ->
            requireNotNull(context.contentResolver.openOutputStream(uri)).use { output -> input.copyTo(output) }
        }
        context.contentResolver.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
        return uri
    }

    private fun screenshot(name: String) {
        compose.waitUntil(15_000) {
            compose.onAllNodes(SemanticsMatcher("Visible picker image") {
                val tag = it.config.getOrElse(SemanticsProperties.TestTag) { "" }
                tag.startsWith("picker.photo.") || tag == "picker.previewImage"
            }, useUnmergedTree = true).fetchSemanticsNodes().all {
                it.config.getOrElse(SemanticsProperties.StateDescription) { "" } == "照片已加载"
            }
        }
        compose.waitForIdle()
        val config = compose.activity.resources.configuration
        val orientation = if (config.orientation == Configuration.ORIENTATION_LANDSCAPE) "landscape" else "portrait"
        val directory = File(context.getExternalFilesDir(null), "wechat-picker-screenshots").apply { mkdirs() }
        val image = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try {
            File(directory, "$orientation-${config.fontScale}-$name.png").outputStream().use {
                assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, it))
            }
        } finally { image.recycle() }
    }
}
