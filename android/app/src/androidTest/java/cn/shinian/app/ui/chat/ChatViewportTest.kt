package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.displayCutout
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.AuthSession
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.Person
import cn.shinian.app.ui.theme.shinianContentInsets
import cn.shinian.app.ui.theme.ShinianTheme
import cn.shinian.app.ui.theme.applyShinianWindowPolicy
import java.io.File
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
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
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Production chat/controller with a terminal in-memory interceptor: no socket or account access. */
@RunWith(AndroidJUnit4::class)
class ChatViewportTest {
    companion object { private var educationConfirmed = false }
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val transport = ViewportTransport()
    private val repository = BackendRepository(transport.session, OkHttpClient.Builder().addInterceptor(transport).build())
    private val person = Person(transport.personId, "界面验证家人", "奶奶", hasChatHistory = true)
    private val baseline get() = InstrumentationRegistry.getArguments().getString("viewportBaseline") == "true"
    private var tag = "chat"
    private val modelKey get() = "chat-${repository.session.scopeKey}-${repository.session.token.hashCode()}-${person.id}"
    private fun controller() = ViewModelProvider(compose.activity)[modelKey, ChatController::class.java]

    @After fun cleanup() {
        repository.invalidate()
        File(File(context.noBackupFilesDir, "PendingStories"), transport.session.scopeKey).deleteRecursively()
    }

    private fun start(life: Boolean, fullscreen: Boolean = !baseline) {
        tag = if (life) "life" else "chat"
        transport.life = life
        compose.runOnUiThread {
            compose.activity.enableEdgeToEdge()
            compose.activity.window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
            if (fullscreen) applyShinianWindowPolicy(compose.activity.window)
        }
        compose.setContent { ShinianTheme { Box(Modifier.fillMaxSize().background(cn.shinian.app.ui.theme.JournalColors.Paper)
            .shinianContentInsets().testTag("viewport.host")) {
            ChatScreen(person, repository, false, {}, {}, {})
        } } }
        waitInput()
        if (!baseline) dismissImmersiveEducation(waitForAppearance = !educationConfirmed)
    }

    private fun waitInput() = compose.waitUntil(15_000) {
        compose.onAllNodesWithTag("$tag.input").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
    }
    private fun visible(nodeTag: String) = runCatching {
        compose.onNodeWithTag(nodeTag, useUnmergedTree = true).assertIsDisplayed()
    }.isSuccess
    private fun waitBottom() {
        compose.waitUntil(10_000) { visible("$tag.bottom") }
        val bottom = compose.onNodeWithTag("$tag.bottom", useUnmergedTree = true).fetchSemanticsNode().boundsInRoot
        val history = compose.onNodeWithTag("$tag.history").fetchSemanticsNode().boundsInRoot
        assertTrue("Latest bottom is inside the actual message viewport", bottom.bottom <= history.bottom + 2f)
        assertTrue("Latest bottom reaches the viewport end", bottom.bottom >= history.bottom - 120f)
    }
    private fun imeVisible(): Boolean {
        var value = false
        compose.runOnUiThread { value = ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true }
        return value
    }
    private fun assertStatusBarVisible() {
        compose.waitUntil(8_000) {
            var hidden = false
            compose.runOnUiThread {
                val insets = ViewCompat.getRootWindowInsets(compose.activity.window.decorView)
                hidden = insets != null && insets.isVisible(WindowInsetsCompat.Type.statusBars()) &&
                    (insets.isVisible(WindowInsetsCompat.Type.ime()) || !insets.isVisible(WindowInsetsCompat.Type.navigationBars()))
            }
            hidden
        }
    }
    private fun assertComposerAboveIme() {
        val bottom = compose.onNodeWithTag("$tag.composer").fetchSemanticsNode().boundsInRoot.bottom
        var height = 0
        var imeBottom = 0
        var nav = false
        var status = true
        compose.runOnUiThread {
            val decor = compose.activity.window.decorView
            val insets = requireNotNull(ViewCompat.getRootWindowInsets(decor))
            height = decor.height; imeBottom = insets.getInsets(WindowInsetsCompat.Type.ime()).bottom
            nav = insets.isVisible(WindowInsetsCompat.Type.navigationBars())
            status = insets.isVisible(WindowInsetsCompat.Type.statusBars())
        }
        assertTrue("The current docked or floating input method is visible", imeVisible())
        assertTrue("Status bar remains visible while the keyboard is visible", status)
        assertTrue("Composer stays above the actual keyboard", bottom <= height - imeBottom + 3f)
        File(context.getExternalFilesDir(null), "chat-viewport-screenshots/$tag-ime-insets.json").apply { parentFile?.mkdirs() }
            .writeText(JSONObject().put("ime_bottom", imeBottom).put("window_height", height).put("composer_bottom", bottom)
                .put("ime_owned_navigation_visible", nav).put("status_bar_visible", status).toString())
    }
    private fun screenshot(name: String) {
        if (!baseline) dismissImmersiveEducation(waitForAppearance = false)
        compose.waitForIdle()
        val directory = File(context.getExternalFilesDir(null), "chat-viewport-screenshots").apply { mkdirs() }
        val image = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try { File(directory, "$name.png").outputStream().use { assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, it)) } }
        finally { image.recycle() }
    }
    private fun educationButton(): android.view.accessibility.AccessibilityNodeInfo? {
        val automation = instrumentation.uiAutomation
        val service = automation.serviceInfo
        if (service.flags and android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS == 0) {
            service.flags = service.flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            automation.serviceInfo = service
        }
        val pending = java.util.ArrayDeque<android.view.accessibility.AccessibilityNodeInfo>()
        automation.windows.mapNotNull { it.root }.forEach(pending::add)
        automation.rootInActiveWindow?.let(pending::add)
        while (pending.isNotEmpty()) {
            val node = pending.removeFirst()
            if (node.isVisibleToUser && node.text?.toString() in listOf("Got it", "知道了", "明白了")) return node
            repeat(node.childCount) { node.getChild(it)?.let(pending::add) }
        }
        return null
    }
    private fun dismissImmersiveEducation(waitForAppearance: Boolean) {
        val until = android.os.SystemClock.uptimeMillis() + if (waitForAppearance) 3_000 else 0
        do {
            val button = educationButton()
            if (button != null) {
                assertTrue("Confirm the visible Android fullscreen education button normally",
                    button.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
                compose.waitUntil(5_000) { educationButton() == null }
                educationConfirmed = true
                File(context.getExternalFilesDir(null), "chat-viewport-screenshots/education-confirmation.json")
                    .apply { parentFile?.mkdirs() }.writeText("{\"visible_system_button_clicked\":true,\"confirmation_setting_was_not_modified\":true}")
                return
            }
            if (android.os.SystemClock.uptimeMillis() < until) android.os.SystemClock.sleep(100)
        } while (android.os.SystemClock.uptimeMillis() < until)
    }
    private fun appendIncoming(long: Boolean = false) {
        val reads = transport.reads.get()
        transport.appendAssistant(long)
        compose.runOnIdle { controller().retryOpen() }
        compose.waitUntil(15_000) { transport.reads.get() > reads }
        waitInput()
    }
    private fun send(text: String) {
        val sends = transport.sends.get()
        compose.onNodeWithTag("$tag.input").performTextReplacement(text)
        compose.onNodeWithTag("$tag.send").performClick()
        compose.waitUntil(15_000) { transport.sends.get() > sends }
        waitInput()
    }
    private fun exerciseFollow(life: Boolean) {
        start(life)
        waitBottom()
        compose.onAllNodesWithText("慢慢讲，我在听", substring = true).assertCountEquals(0)
        compose.onNodeWithTag("$tag.input").performClick()
        compose.waitUntil(8_000) { imeVisible() }
        waitBottom()
        assertStatusBarVisible()
        assertComposerAboveIme()
        screenshot("$tag-keyboard-latest")
        send("这是完全本地的界面跟随验证讲述。")
        waitBottom()
        screenshot("$tag-after-own-send-and-reply")
        appendIncoming(long = true)
        waitBottom()
        screenshot("$tag-long-reply-bottom")
        if (imeVisible()) instrumentation.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        compose.waitUntil(8_000) { !imeVisible() }
        waitBottom()
        assertStatusBarVisible()
    }

    @Test fun baselineLifeHistoryDoesNotReachItsLatestQuestion() {
        assumeTrue("Only run explicitly against the pre-change APK", baseline)
        start(life = true, fullscreen = false)
        val last = transport.lastContent()
        val latestVisible = runCatching { compose.onNodeWithText(last).assertIsDisplayed() }.isSuccess
        val labelVisible = compose.onAllNodesWithText("慢慢讲，我在听", substring = true).fetchSemanticsNodes().isNotEmpty()
        screenshot("baseline-life-initial-history")
        assertFalse("Baseline must reproduce the missing life-chat follow", latestVisible)
        assertTrue("Baseline must reproduce the floating input label", labelVisible)
    }

    @Test fun lifeFollowsSendReplyKeyboardAndLongReplyWithoutFloatingLabel() = exerciseFollow(true)
    @Test fun storyFollowsSendReplyKeyboardAndLongReplyWithoutFloatingLabel() = exerciseFollow(false)

    private fun exerciseManualHistory(life: Boolean) {
        start(life); waitBottom()
        val history = compose.onNodeWithTag("$tag.history")
        repeat(3) { history.performTouchInput { swipeDown(durationMillis = 450) } }
        compose.waitUntil(5_000) { !visible("$tag.bottom") }
        val viewport = history.fetchSemanticsNode().boundsInRoot
        val anchor = transport.ids().firstNotNullOfOrNull { id ->
            val nodeTag = "$tag.message.$id"
            val bounds = runCatching { compose.onNodeWithTag(nodeTag, useUnmergedTree = true).fetchSemanticsNode().boundsInRoot }.getOrNull()
            if (bounds != null && bounds.top > viewport.top + 4f && bounds.bottom < viewport.bottom - 4f) nodeTag to bounds.top else null
        }
        assertNotNull("A real user drag must expose an older complete message", anchor)
        val (anchorTag, before) = requireNotNull(anchor)
        appendIncoming()
        assertFalse("Incoming reply must not pull a user away from history", visible("$tag.bottom"))
        val after = compose.onNodeWithTag(anchorTag, useUnmergedTree = true).fetchSemanticsNode().boundsInRoot.top
        assertEquals("The visible historical anchor remains in place", before, after, 3f)
        screenshot("$tag-manual-history-preserved")
        compose.onNodeWithTag("$tag.latest").performClick()
        waitBottom()
        repeat(2) { history.performTouchInput { swipeDown(durationMillis = 450) } }
        compose.waitUntil(5_000) { !visible("$tag.bottom") }
        send("从翻看的历史里发一条新的本地讲述。")
        waitBottom()
        screenshot("$tag-own-send-resumes-bottom")
    }
    @Test fun lifeKeepsManualHistoryOnIncomingReplyButOwnSendReturnsToBottom() = exerciseManualHistory(true)
    @Test fun storyKeepsManualHistoryOnIncomingReplyButOwnSendReturnsToBottom() = exerciseManualHistory(false)

    @Test fun productionWindowPolicyKeepsStatusBarVisibleAfterImeAndActivityReentry() {
        start(life = false); waitBottom(); assertStatusBarVisible()
        compose.onNodeWithTag("chat.input").performClick()
        compose.waitUntil(8_000) { imeVisible() }; assertStatusBarVisible(); waitBottom(); assertComposerAboveIme()
        instrumentation.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        compose.waitUntil(8_000) { !imeVisible() }; assertStatusBarVisible(); waitBottom()
        compose.activityRule.scenario.moveToState(Lifecycle.State.STARTED)
        compose.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        compose.runOnUiThread { applyShinianWindowPolicy(compose.activity.window) }
        assertStatusBarVisible(); waitBottom(); screenshot("statusbar-reentry")
        compose.onNodeWithContentDescription("前面聊过的").performClick()
        compose.onNodeWithText("前面聊过的").assertIsDisplayed()
        if (android.os.Build.VERSION.SDK_INT >= 29) {
            compose.waitUntil(8_000) {
                var hidden = false
                compose.runOnUiThread {
                    val windows = android.view.inspector.WindowInspector.getGlobalWindowViews().filter { it.isShown }
                    hidden = windows.size >= 2 && windows.all { view ->
                        ViewCompat.getRootWindowInsets(view)?.isVisible(WindowInsetsCompat.Type.statusBars()) == true
                    }
                }
                hidden
            }
        }
        screenshot("statusbar-history-dialog")
        instrumentation.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        waitBottom(); assertStatusBarVisible()
    }
}

private class ViewportTransport : Interceptor {
    val personId = UUID.randomUUID().toString()
    private val sessionId = UUID.randomUUID().toString()
    val session = AuthSession("https://viewport-fixture.invalid", UUID.randomUUID().toString(), UUID.randomUUID().toString(), "local-viewport", false, "local-viewport-token", "2099-01-01T00:00:00Z")
    val reads = AtomicInteger()
    val sends = AtomicInteger()
    @Volatile var life = false
    private var version = 1
    private val messages = mutableListOf<JSONObject>().apply {
        repeat(33) { index -> add(message(if (index % 2 == 0) "assistant" else "user", "本地旧记录 ${index + 1}：那年家门口有一棵树。我们在树下说话，记住了生活里的小事。")) }
    }
    @Synchronized fun lastContent(): String = messages.last().getString("content")
    @Synchronized fun ids(): List<String> = messages.map { it.getString("id") }
    @Synchronized fun appendAssistant(long: Boolean = false) {
        messages += message("assistant", if (long) (1..70).joinToString("\n") { "长回复第 $it 行：这是本地受控内容，不涉及任何账号或网络。" } + "\n长回复已经结束。" else "新回复 ${messages.size}：接着说说那一天吧。")
        version++
    }
    @Synchronized override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        check(request.url.host == "viewport-fixture.invalid") { "Unexpected host in controlled UI test" }
        val path = request.url.encodedPath
        val body = request.body?.let { Buffer().also(it::writeTo).readUtf8() }?.takeIf { it.isNotBlank() }?.let(::JSONObject)
        val response = when {
            path.endsWith("/auth/me") -> JSONObject().put("account_id", session.accountId).put("family_id", session.familyId).put("username", session.username)
            path.endsWith("/conversation/messages") || path.endsWith("/life-overview/actions") -> {
                val value = requireNotNull(body)
                messages += message("user", value.optString(if (life) "text" else "content"), value.getString("client_request_id"))
                appendAssistant(); sends.incrementAndGet(); snapshot()
            }
            path.endsWith("/conversation") -> { reads.incrementAndGet(); snapshot() }
            else -> throw AssertionError("Unexpected controlled UI path: $path")
        }
        // This interceptor terminates every request; chain.proceed is never used.
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
            .body(response.toString().toResponseBody("application/json".toMediaType())).build()
    }
    private fun snapshot(): JSONObject = JSONObject()
        .put("session", JSONObject().put("id", sessionId).put("status", "active").put("version", version).put("information", JSONObject()))
        .put("messages", JSONArray(messages)).put("current_message_ids", JSONArray(ids())).put("can_generate", false)
        .put("life_overview", if (!life) JSONObject.NULL else JSONObject().put("required", true).put("status", "collecting").put("version", version)
            .put("question_number", 6).put("total_questions", 11).put("question", lastContent()).put("question_id", "SK03b")
            .put("fields", JSONArray()).put("turns", JSONArray(messages)))
    private fun message(role: String, text: String, id: String = UUID.randomUUID().toString()) = JSONObject()
        .put("id", id).put("role", role).put("content", text).put("attachments", JSONArray())
}
