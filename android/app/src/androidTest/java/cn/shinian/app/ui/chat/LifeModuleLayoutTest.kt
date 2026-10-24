package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.AuthSession
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.Person
import cn.shinian.app.ui.theme.JournalColors
import cn.shinian.app.ui.auth.AuthScreen
import cn.shinian.app.ui.auth.AuthUiState
import cn.shinian.app.ui.theme.ShinianTheme
import cn.shinian.app.ui.theme.applyShinianWindowPolicy
import cn.shinian.app.ui.theme.shinianContentInsets
import java.io.File
import java.util.UUID
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real screen/controller with a terminal local transport; never opens a cloud account. */
@RunWith(AndroidJUnit4::class)
class LifeModuleLayoutTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val transport = ModuleLayoutTransport()
    private val repository = BackendRepository(transport.session, OkHttpClient.Builder().addInterceptor(transport).build())
    private val person = Person(transport.personId, "界面验证家人", "奶奶", hasChatHistory = true)

    @After fun cleanup() {
        repository.invalidate()
        File(File(instrumentation.targetContext.noBackupFilesDir, "PendingStories"), transport.session.scopeKey).deleteRecursively()
    }

    private fun start(width: Int = 360, height: Int = 800, fontScale: Float = 1f) {
        compose.runOnUiThread {
            compose.activity.enableEdgeToEdge()
            applyShinianWindowPolicy(compose.activity.window)
        }
        compose.setContent {
            ShinianTheme {
                val density = LocalDensity.current.density
                CompositionLocalProvider(LocalDensity provides Density(density, fontScale)) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopStart) {
                        val viewportSize = if (width > 0) Modifier.requiredSize(width.dp, height.dp) else Modifier.fillMaxSize()
                        Box(viewportSize.background(JournalColors.Paper)
                            .testTag("layout.viewport").shinianContentInsets()) {
                            ChatScreen(person, repository, false, {}, {}, {})
                        }
                    }
                }
            }
        }
        var readySince = 0L
        compose.waitUntil(15_000) {
            val ready = compose.onAllNodesWithTag("life.enter").fetchSemanticsNodes()
                .any { !it.config.contains(SemanticsProperties.Disabled) }
            val now = android.os.SystemClock.uptimeMillis()
            if (!ready) readySince = 0L else if (readySince == 0L) readySince = now
            ready && now - readySince >= 200
        }
        compose.waitForIdle()
    }

    private fun screenshot(name: String) {
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "module-layout-screenshots").apply { mkdirs() }
        val image = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try { File(folder, "$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { image.recycle() }
        val viewport = compose.onNodeWithTag("layout.viewport").captureToImage().asAndroidBitmap()
        File(folder, "$name-viewport.png").outputStream().use { viewport.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun assertAllChoicesVisible(name: String) {
        screenshot(name)
        val enter = compose.onNodeWithTag("life.enter").fetchSemanticsNode().boundsInRoot
        val viewport = compose.onNodeWithTag("layout.viewport").fetchSemanticsNode().boundsInRoot
        compose.onNodeWithTag("life.enter").assertIsDisplayed().assertIsEnabled()
        assertTrue("Enter button is completely inside the viewport", enter.bottom <= viewport.bottom + 1)
        listOf("childhood", "growth", "work", "family", "later_life", "reflection").forEach { id ->
            val node = compose.onNodeWithTag("life.module.$id").fetchSemanticsNode()
            val bounds = node.boundsInRoot
            assertTrue("$id must be fully visible without scrolling", bounds.height >= node.size.height - 1 && bounds.height > 0)
            assertTrue("$id must stay above the enter button", bounds.bottom <= enter.top)
        }
        listOf("成长的地方", "读书或学艺", "工作与生活", "重要家人", "如今的生活", "人生回望",
            "家乡与童年", "校园与手艺", "奋斗与日常", "亲人与陪伴", "此刻的日常", "回忆与感悟").forEach {
            val text = compose.onNodeWithText(it, useUnmergedTree = true).assertIsDisplayed()
            val node = text.fetchSemanticsNode()
            assertTrue("$it must not be clipped", node.boundsInRoot.height >= node.size.height - 1)
            val layouts = mutableListOf<TextLayoutResult>()
            text.performSemanticsAction(SemanticsActions.GetTextLayoutResult) { action -> action(layouts) }
            assertTrue("$it must have a text layout", layouts.isNotEmpty())
            // The paragraph can retain its wider measurement constraint after Text wraps its width.
            // Check the painted lines, as well as the node's clipping, rather than that constraint.
            layouts.forEach { layout ->
                repeat(layout.lineCount) { line ->
                    assertTrue("$it line must fit vertically", layout.getLineBottom(line) <= layout.size.height + 1)
                    assertTrue("$it line must fit horizontally", layout.getLineRight(line) <= layout.size.width + 1)
                }
            }
        }
    }

    @Test fun allSixModulesFitOnSmallPortraitPhone() { start(height = 640); assertAllChoicesVisible("small-360x640") }
    @Test fun allSixModulesFitOnTallPortraitPhone() { start(width = 400, height = 880); assertAllChoicesVisible("tall-400x880") }
    @Test fun allSixModulesFitWithModeratelyLargerText() { start(height = 800, fontScale = 1.3f); assertAllChoicesVisible("font-1.3-360x800") }

    @Test fun statusBarAndCameraInsetProtectHeaderWithoutExtraTopStrip() {
        start(width = 0, height = 0)
        screenshot("statusbar-top")
        val back = compose.onNodeWithTag("chat.back").fetchSemanticsNode().boundsInRoot
        val root = compose.onNodeWithTag("layout.viewport").fetchSemanticsNode().boundsInRoot
        val density = compose.activity.resources.displayMetrics.density
        var safeTop = 0
        compose.runOnUiThread {
            val insets = requireNotNull(ViewCompat.getRootWindowInsets(compose.activity.window.decorView))
            assertTrue("Status bar is visible", insets.isVisible(WindowInsetsCompat.Type.statusBars()))
            safeTop = insets.getInsets(WindowInsetsCompat.Type.statusBars() or WindowInsetsCompat.Type.displayCutout()).top
        }
        assertTrue("Real camera/status-bar safety area exists", safeTop > 0)
        assertTrue("Header stays below the camera and status icons", back.top - root.top >= safeTop)
        assertTrue("Safety area is applied once without another blank band", back.top - root.top <= safeTop + 12 * density)
    }

    @Test fun warmBackgroundMeetsStatusAreaWithoutAHardColorSeam() {
        compose.runOnUiThread { compose.activity.enableEdgeToEdge(); applyShinianWindowPolicy(compose.activity.window) }
        compose.setContent {
            ShinianTheme {
                Box(Modifier.fillMaxSize().background(JournalColors.Paper).testTag("layout.viewport").shinianContentInsets()) {
                    AuthScreen(AuthUiState(), { _, _ -> }, { _, _ -> },
                        modifier = Modifier.fillMaxSize().testTag("warm.background"))
                }
            }
        }
        compose.waitForIdle()
        val top = compose.onNodeWithTag("warm.background").fetchSemanticsNode().boundsInRoot.top.toInt()
        val image = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try {
            for (x in listOf(image.width / 4, image.width / 2, image.width * 3 / 4)) {
                val above = image.getPixel(x, top - 1)
                val below = image.getPixel(x, top + 1)
                for (shift in listOf(0, 8, 16)) assertTrue("Adjacent background colors blend at the status boundary",
                    kotlin.math.abs((above shr shift and 255) - (below shr shift and 255)) <= 2)
            }
        } finally { image.recycle() }
        screenshot("warm-statusbar")
    }

    @Test fun selectingAndEnteringKeepsTheCorrectModuleAndCorrectionEntry() {
        start()
        compose.onNodeWithText("查看全部与更正", substring = true).performClick()
        compose.onNodeWithText("核对人生脉络").assertIsDisplayed()
        compose.onAllNodesWithTag("chat.back").onLast().performClick()
        compose.onNodeWithTag("life.module.reflection").performClick().assertIsSelected()
        compose.onNodeWithTag("life.enter").assertTextContains("人生回望", substring = true).performClick()
        compose.waitUntil(10_000) { transport.selectedModule == "reflection" }
        assertEquals("reflection", transport.selectedModule)
    }
}

private class ModuleLayoutTransport : Interceptor {
    val personId = UUID.randomUUID().toString()
    private val sessionId = UUID.randomUUID().toString()
    val session = AuthSession("https://module-layout.invalid", UUID.randomUUID().toString(), UUID.randomUUID().toString(),
        "local-layout", false, "local-layout-token", "2099-01-01T00:00:00Z")
    @Volatile var selectedModule = ""
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        check(request.url.host == "module-layout.invalid")
        val path = request.url.encodedPath
        val body = request.body?.let { Buffer().also(it::writeTo).readUtf8() }?.takeIf { it.isNotBlank() }?.let(::JSONObject)
        val response = when {
            path.endsWith("/auth/me") -> JSONObject().put("account_id", session.accountId).put("family_id", session.familyId).put("username", session.username)
            path.endsWith("/interview") -> { selectedModule = requireNotNull(body).getString("module"); snapshot() }
            path.endsWith("/conversation") -> snapshot()
            else -> throw AssertionError("Unexpected local UI request: $path")
        }
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
            .body(response.toString().toResponseBody("application/json".toMediaType())).build()
    }
    private fun snapshot() = JSONObject()
        .put("session", JSONObject().put("id", sessionId).put("status", "active").put("version", 1)
            .put("information", JSONObject().put("guided_interview", JSONObject().put("module_selected", selectedModule.isNotBlank()).put("module", selectedModule))))
        .put("messages", JSONArray()).put("current_message_ids", JSONArray()).put("can_generate", false)
        .put("life_overview", JSONObject().put("required", true).put("status", "confirmed").put("version", 1)
            .put("fields", JSONArray().put(JSONObject().put("topic_id", "SK01").put("status", "known")
                .put("evidence", JSONArray().put(JSONObject().put("quote", "出生在家乡，和家人一起长大。后来读书、工作，留下许多值得珍藏的回忆。")))))
            .put("turns", JSONArray()))
}
