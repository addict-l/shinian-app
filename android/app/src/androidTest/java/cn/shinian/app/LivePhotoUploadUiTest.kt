package cn.shinian.app

import android.Manifest
import android.content.ContentValues
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.view.inspector.WindowInspector
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.SessionStore
import cn.shinian.app.ui.chat.ChatDraftStore
import java.io.File
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in real upload, restricted to the verifier-owned synthetic family staged on this device. */
@RunWith(AndroidJUnit4::class)
class LivePhotoUploadUiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext

    @Test fun selectedPhotosUploadAsOneMessageAndOpenInThePhotoSheet() {
        val staged = File(context.filesDir, "live-validation.private.json")
        val inserted = mutableListOf<Uri>()
        var ownedFixture = false
        var repository: BackendRepository? = null
        try {
            assumeTrue("Stage this verifier's isolated family before running the live photo test", staged.exists())
            val fixture = runCatching { JSONObject(staged.readText()) }.getOrNull()
            ownedFixture = fixture?.optString("verification_owner") == "shinian-android-20261021"
            assumeTrue("Only the verifier-owned synthetic fixture is accepted", ownedFixture)
            val credentials = requireNotNull(fixture)
            val session = SessionStore(context).load()
            assumeTrue("Log into the staged synthetic family first", session != null && session.familyId == credentials.optString("family_id"))
            val verifiedSession = requireNotNull(session)
            val personId = credentials.getString("person_id")
            val api = BackendRepository(verifiedSession).also { repository = it }
            val person = runBlocking { api.members() }.singleOrNull { it.id == personId }
            assumeTrue("The staged person must belong to this isolated family", person != null)

            compose.activityRule.scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT }
            compose.waitUntil(10_000) { compose.activity.resources.configuration.orientation == Configuration.ORIENTATION_PORTRAIT }
            assumeTrue("The selected-photo strip is verified at the normal system font size", compose.activity.resources.configuration.fontScale <= 1.3f)
            waitFor("tab.1")
            compose.onNodeWithTag("tab.1").performClick()
            waitFor("member.$personId")
            compose.onNodeWithTag("member.$personId").performClick()
            compose.waitUntil(45_000) { compose.onAllNodes(hasTestTag("chat.input") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("chat.selectedPhotos").assertDoesNotExist()

            instrumentation.uiAutomation.grantRuntimePermission(context.packageName,
                if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE)
            val album = "ShinianLivePhotoReview-${UUID.randomUUID()}"
            val photos = listOf("summer", "dinner").map { name ->
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, "$name.jpg")
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    if (Build.VERSION.SDK_INT >= 29) {
                        put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/$album/")
                        put(MediaStore.Images.Media.IS_PENDING, 1)
                    }
                }
                val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
                inserted += uri
                instrumentation.context.assets.open("photo-review-$name.jpg").use { input ->
                    requireNotNull(context.contentResolver.openOutputStream(uri)).use { output -> input.copyTo(output) }
                }
                if (Build.VERSION.SDK_INT >= 29) context.contentResolver.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
                uri
            }

            // Exercise the app's real gallery, ordered selection, and production JPEG preparation.
            compose.onNodeWithTag("chat.addPhotos").assertIsEnabled().performClick()
            photos.forEach { uri ->
                val id = android.content.ContentUris.parseId(uri)
                waitFor("picker.select.$id")
                compose.onNodeWithTag("picker.select.$id").performClick()
            }
            compose.waitUntil(15_000) { photos.all { uri ->
                compose.onAllNodesWithTag("picker.photo.${android.content.ContentUris.parseId(uri)}", useUnmergedTree = true).fetchSemanticsNodes()
                    .any { it.config.getOrElse(SemanticsProperties.StateDescription) { "" } == "照片已加载" }
            } }
            capture("00-picker-selected")
            compose.onNodeWithTag("picker.done").assertIsEnabled().performClick()
            compose.waitUntil(30_000) { nodesStartingWith("chat.selectedPhoto.").size == 2 }
            val photoIds = nodesStartingWith("chat.selectedPhoto.").map { it.removePrefix("chat.selectedPhoto.") }
            photoIds.forEach { id ->
                compose.onNode(hasTestTag("chat.selectedPhoto.$id") and hasAnyAncestor(hasTestTag("chat.composer")), useUnmergedTree = true).assertIsDisplayed()
            }
            compose.onNode(hasText("也可以写几句话…") and hasAnyAncestor(hasTestTag("chat.composer")), useUnmergedTree = true).assertIsDisplayed()
            capture("01-selected")

            val store = ChatDraftStore(context, verifiedSession.scopeKey, personId)
            compose.waitUntil(10_000) { runCatching { store.load()?.second?.map { it.id } == photoIds }.getOrDefault(false) }
            val chatSessionId = requireNotNull(store.load()?.first?.sessionId)
            val before = runBlocking { api.chatState(chatSessionId) }
            val narration = "这是安卓照片界面验收的虚构讲述。那年夏天，我和家人在院子里乘凉，孩子们骑着自行车绕着树跑。傍晚大家围坐在饭桌旁，奶奶端来热汤，我们聊起白天的小事，那些平常的日子让我一直记得很温暖。"
            compose.onNodeWithTag("chat.input").performTextInput(narration)
            compose.onNodeWithTag("chat.send").assertIsEnabled().performClick()
            compose.waitUntil(15_000) { photoIds.all { visible("chat.pendingPhoto.$it") } }
            compose.onNodeWithTag("chat.selectedPhotos").assertDoesNotExist()
            compose.waitUntil(10_000) { runCatching { store.load()?.first?.pending != null }.getOrDefault(false) }
            val pending = requireNotNull(store.load()?.first?.pending)
            photoIds.forEach { compose.onNodeWithTag("chat.pendingPhoto.$it").assertIsDisplayed() }
            capture("02-uploading")

            // No draft generation or memory confirmation is invoked by this test.
            compose.waitUntil(450_000) {
                runCatching {
                    store.load()?.first?.pending == null &&
                        compose.onAllNodes(hasTestTag("chat.input") and isEnabled()).fetchSemanticsNodes().isNotEmpty()
                }.getOrDefault(false)
            }
            val after = runBlocking { api.chatState(chatSessionId) }
            val sent = after.messages.singleOrNull { it.id == pending.id }
            assertNotNull("The uploaded narration must remain in server history", sent)
            assertEquals(narration, requireNotNull(sent).content)
            assertEquals(photoIds, sent.attachments.map { it.id })
            assertEquals(1, after.messages.count { it.role == "user" && it.id !in before.messages.map { prior -> prior.id } })
            assertTrue("The real server must finish its response", after.messages.lastOrNull()?.role == "assistant")
            compose.onNodeWithTag("chat.history").performScrollToNode(hasTestTag("chat.message.photos.${pending.id}"))
            compose.waitUntil(45_000) { photoIds.all { photoLoaded(it) } }
            photoIds.forEach { compose.onNodeWithTag("chat.photo.$it").assertIsDisplayed() }
            compose.onNodeWithTag("chat.selectedPhotos").assertDoesNotExist()
            capture("03-sent")

            compose.onNodeWithTag("chat.photo.${photoIds.first()}").performClick()
            waitFor("chat.photos.close")
            compose.waitUntil(45_000) {
                compose.onAllNodes(hasTestTag("chat.photo.${photoIds.first()}") and hasAnyAncestor(isPhotoSheet()), useUnmergedTree = true)
                    .fetchSemanticsNodes().any { it.config.getOrElse(SemanticsProperties.StateDescription) { "" } == "照片已加载" }
            }
            capture("04-viewer")
            compose.onNodeWithTag("chat.photos.close").performClick()
            compose.onNodeWithTag("chat.photos.close").assertDoesNotExist()
        } finally {
            repository?.invalidate()
            inserted.forEach { uri -> runCatching { context.contentResolver.delete(uri, null, null) } }
            if (ownedFixture) staged.delete()
        }
    }

    private fun visible(tag: String) = compose.onAllNodesWithTag(tag, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitFor(tag: String) { compose.waitUntil(45_000) { visible(tag) } }
    private fun nodesStartingWith(prefix: String): List<String> = compose.onAllNodes(SemanticsMatcher("tag prefix") {
        it.config.getOrElse(SemanticsProperties.TestTag) { "" }.startsWith(prefix)
    }, useUnmergedTree = true).fetchSemanticsNodes().map { it.config[SemanticsProperties.TestTag] }
    private fun photoLoaded(id: String) = compose.onAllNodesWithTag("chat.photo.$id", useUnmergedTree = true).fetchSemanticsNodes()
        .any { it.config.getOrElse(SemanticsProperties.StateDescription) { "" } == "照片已加载" }
    private fun isPhotoSheet() = hasTestTag("chat.photos.sheet")
    private fun capture(name: String) {
        compose.waitForIdle()
        instrumentation.waitForIdleSync()
        if (Build.VERSION.SDK_INT >= 29) {
            lateinit var committed: CountDownLatch
            instrumentation.runOnMainSync {
                val views = WindowInspector.getGlobalWindowViews().filter { it.isShown && it.width > 0 && it.height > 0 }
                committed = CountDownLatch(views.size)
                views.forEach { view ->
                    view.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }
                    view.invalidate()
                }
            }
            assertTrue("The screenshot must wait for the rendered frame", committed.await(10, TimeUnit.SECONDS))
        }
        val folder = File(context.getExternalFilesDir(null), "photo-ui-screenshots").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try { File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { bitmap.recycle() }
    }
}
