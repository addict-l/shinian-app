package cn.shinian.app.ui.chat

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.SoftwareKeyboardController
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.AuthSession
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.Person
import cn.shinian.app.ui.theme.ShinianTheme
import java.io.File
import java.io.IOException
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.runBlocking
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
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real screen/repository/persistence with a deterministic HTTP transport. Never contacts a family. */
@RunWith(AndroidJUnit4::class)
class ChatInteractionTest {
    @get:Rule val compose = createComposeRule()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val backend = DialogueTransport()
    private val repository = BackendRepository(backend.session, OkHttpClient.Builder().addInterceptor(backend).build())
    private val person = Person(backend.personId, "测试家人", "爷爷", hasChatHistory = true)
    private var keyboard: SoftwareKeyboardController? = null

    @After fun cleanup() {
        repository.invalidate()
        File(File(context.noBackupFilesDir, "PendingStories"), backend.session.scopeKey).deleteRecursively()
    }

    private fun start(life: Boolean = false, care: Boolean = false, onHome: () -> Unit = {}, onSaved: () -> Unit = {}) {
        backend.life = life
        compose.setContent {
            keyboard = LocalSoftwareKeyboardController.current
            ShinianTheme { Box(Modifier.fillMaxSize().statusBarsPadding()) { ChatScreen(person, repository, care, {}, onSaved, onHome) } }
        }
    }
    private fun waitTag(tag: String) = compose.waitUntil(15_000) {
        compose.onAllNodesWithTag(tag).fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
    }
    private fun waitText(text: String) = compose.waitUntil(15_000) { compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty() }

    @Test fun interruptedNarrationRetriesSameIdentityAndDraftNeedsExplicitSave() {
        var saved = 0
        backend.failFirstMessage = true
        start(onSaved = { saved++ })
        waitTag("chat.input")
        compose.onNodeWithTag("chat.input").performTextInput("那年我离开家乡，第一次去工厂上班。")
        compose.onNodeWithTag("chat.send").performClick()
        waitText("重试这条讲述")
        compose.onNodeWithText("重试这条讲述").performScrollTo().performClick()
        waitTag("chat.generate")
        assertEquals(2, backend.messages.size)
        assertEquals(backend.messages[0].getString("client_request_id"), backend.messages[1].getString("client_request_id"))
        compose.onNodeWithTag("chat.generate").performClick()
        waitTag("memory.save")
        assertEquals(0, backend.confirmations.get())
        compose.onNodeWithText("编辑文字与时间").performScrollTo().performClick()
        waitTag("draft.title")
        compose.onNodeWithTag("draft.time").performScrollTo().performTextReplacement("2010年")
        compose.onNodeWithTag("draft.timePreview").performScrollTo().performClick()
        waitTag("time.suggestion.title-time")
        compose.onNodeWithTag("time.suggestion.title-time").performScrollTo().performClick()
        compose.onNodeWithTag("time.suggestion.body-time").performScrollTo().performClick()
        compose.onNodeWithTag("time.apply").performClick()
        compose.onNodeWithTag("draft.title").performScrollTo().assertTextContains("2010年", substring = true)
        compose.onNodeWithTag("draft.body").performScrollTo().assertTextContains("2010年", substring = true)
        compose.onNodeWithTag("draft.title").performScrollTo().performTextReplacement("2010年离开故乡的记忆")
        compose.runOnIdle { keyboard?.hide() }
        compose.waitForIdle()
        compose.onNodeWithTag("draft.keepEdits").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        compose.waitUntil(15_000) { backend.edits.size == 1 }
        waitTag("memory.save")
        waitText("2010年离开故乡的记忆")
        assertEquals(0, backend.confirmations.get())
        assertEquals("2010年离开故乡的记忆", backend.edits.single().getString("title"))
        compose.onNodeWithTag("memory.save").performScrollTo().assertIsEnabled().performClick()
        compose.waitUntil(15_000) { backend.openedAfterSave.get() == 1 && compose.onAllNodesWithTag("chat.input").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("这段故事，已经留下了").assertDoesNotExist()
        compose.onNodeWithTag("chat.input").assertIsDisplayed()
        assertEquals(1, backend.confirmations.get())
        compose.runOnIdle { assertEquals(1, saved) }
    }

    @Test fun careSaveOffersHomeReadingAndContinueWithoutOpeningNextSegmentEarly() {
        var saved = 0
        var home = 0
        start(care = true, onHome = { home++ }, onSaved = { saved++ })
        waitTag("chat.input")
        compose.onNodeWithTag("chat.input").performTextInput("那年我第一次离开家乡去上班。")
        compose.onNodeWithTag("chat.send").performClick()
        waitTag("chat.generate")
        compose.onNodeWithTag("chat.generate").performClick()
        waitTag("memory.save")
        compose.onNodeWithTag("memory.save").performScrollTo().performClick()
        waitText("这段故事，已经留下了")
        assertEquals(1, backend.confirmations.get())
        assertEquals(0, backend.openedAfterSave.get())
        compose.runOnIdle { assertEquals(1, saved) }
        compose.onNodeWithText("回到首页").performScrollTo().assertIsDisplayed().performClick()
        compose.runOnIdle { assertEquals(1, home) }
        compose.onNodeWithText("读读这段回忆").performClick()
        compose.onNodeWithText("回到首页").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(2, home) }
        compose.onNodeWithTag("chat.back").performClick()
        compose.onNodeWithText("继续记录").performClick()
        compose.waitUntil(15_000) { backend.openedAfterSave.get() == 1 && compose.onAllNodesWithTag("chat.input").fetchSemanticsNodes().isNotEmpty() }
        assertEquals(1, backend.confirmations.get())
    }

    @Test fun lifeOutlineSkipAndModuleUseServerStateAndInvalidationRetainsUnsentInput() {
        start(life = true)
        waitTag("life.begin")
        compose.onNodeWithTag("life.begin").performClick()
        waitTag("life.skip")
        compose.onNodeWithText("您大概是什么时候出生的？").assertIsDisplayed()
        compose.onNodeWithTag("life.skip").performClick()
        waitTag("life.confirm")
        assertEquals("跳过这题", backend.lifeCommands.last().getString("text"))
        compose.onNodeWithTag("life.confirm").performClick()
        waitTag("life.module.work")
        compose.onNodeWithTag("life.module.work").performScrollTo().performClick()
        compose.onNodeWithTag("life.enter").performClick()
        waitTag("chat.input")
        assertEquals("work", backend.selectedModule)
        compose.onNodeWithTag("chat.input").performTextInput("这句还没有发送，请保留。")
        val folder = File(File(File(context.noBackupFilesDir, "PendingStories"), backend.session.scopeKey), person.id)
        compose.waitUntil(8_000) { File(folder, "draft.json").run { exists() && readText().contains("这句还没有发送") } }
        val reads = backend.stateReads.get()
        runBlocking { invalidateChatAfterMemoryChange(context, backend.session.scopeKey) }
        compose.waitUntil(15_000) { backend.stateReads.get() > reads }
        waitTag("chat.input")
        compose.onNodeWithTag("chat.input").assertTextContains("这句还没有发送，请保留。", substring = true)
        assertEquals(0, backend.messages.size)
    }
}

private class DialogueTransport : Interceptor {
    val personId = UUID.randomUUID().toString()
    private var sessionId = UUID.randomUUID().toString()
    private val draftId = UUID.randomUUID().toString()
    private var revision = UUID.randomUUID().toString()
    private val openingId = UUID.randomUUID().toString()
    private val replyId = UUID.randomUUID().toString()
    val session = AuthSession("https://chat-validation.example", UUID.randomUUID().toString(), UUID.randomUUID().toString(), "local-instrumentation", false, "synthetic-instrumentation-token", "2099-01-01T00:00:00Z")
    val messages = CopyOnWriteArrayList<JSONObject>()
    val edits = CopyOnWriteArrayList<JSONObject>()
    val lifeCommands = CopyOnWriteArrayList<JSONObject>()
    val confirmations = AtomicInteger()
    val stateReads = AtomicInteger()
    val openedAfterSave = AtomicInteger()
    @Volatile var life = false
    @Volatile var failFirstMessage = false
    @Volatile var selectedModule = ""
    private var lifeStatus = "not_started"
    private var lifeVersion = 0
    private var answered = false
    private var savedSegmentCompleted = false
    private var segmentCleared = false
    private var title = "2008年第一次工作"
    private var content = "2008年，我第一次离开家乡。"
    private var time = JSONObject().put("status", "known").put("value", "2008年").put("source_message_ids", JSONArray()).put("user_edited", false)

    @Synchronized override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val path = request.url.encodedPath
        val body = request.body?.let { Buffer().also(it::writeTo).readUtf8() }?.takeIf { it.isNotBlank() }?.let(::JSONObject)
        val response = when {
            path.endsWith("/auth/me") -> JSONObject().put("account_id", session.accountId).put("family_id", session.familyId).put("username", session.username)
            path.endsWith("/conversation/messages") -> {
                messages += requireNotNull(body)
                segmentCleared = false
                if (failFirstMessage && messages.size == 1) throw IOException("Simulated lost assistant response")
                answered = true; snapshot()
            }
            path.endsWith("/life-overview/actions") -> {
                lifeCommands += requireNotNull(body)
                lifeVersion++
                lifeStatus = when (body.getString("action")) { "begin" -> "collecting"; "answer", "correct" -> "review"; "confirm" -> "confirmed"; else -> lifeStatus }
                snapshot()
            }
            path.endsWith("/interview") -> { selectedModule = requireNotNull(body).getString("module"); snapshot() }
            path.endsWith("/conversation") -> {
                if (request.method == "GET") stateReads.incrementAndGet()
                else if (savedSegmentCompleted) {
                    savedSegmentCompleted = false; segmentCleared = true; answered = false
                    sessionId = UUID.randomUUID().toString(); openedAfterSave.incrementAndGet()
                }
                snapshot()
            }
            path.endsWith("/time-preview") -> {
                JSONObject().put("message", "请逐项核对对应的时间文字。")
                    .put("suggestions", JSONArray().put(suggestion("title-time", "title")).put(suggestion("body-time", "summary")))
            }
            path.endsWith("/confirm") -> { confirmations.incrementAndGet(); savedSegmentCompleted = true; memory() }
            path.endsWith("/draft") -> draft()
            path.endsWith("/$draftId") -> {
                if (request.method == "PATCH") {
                    edits += requireNotNull(body)
                    assertEquals(revision, body.getString("revision"))
                    title = body.getString("title"); content = body.getString("summary"); time = body.getJSONObject("time")
                    revision = UUID.randomUUID().toString()
                }
                draft()
            }
            else -> throw AssertionError("Unexpected instrumentation request: $path")
        }
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
            .body(response.toString().toResponseBody("application/json".toMediaType())).build()
    }

    private fun message(id: String, role: String, text: String) = JSONObject().put("id", id).put("role", role).put("content", text).put("attachments", JSONArray())
    private fun snapshot(): JSONObject {
        val list = JSONArray().put(message(openingId, "assistant", "想到什么就说什么，我在这里听。"))
        if (!segmentCleared) messages.lastOrNull()?.let { list.put(message(it.getString("client_request_id"), "user", it.getString("content"))) }
        if (answered) list.put(message(replyId, "assistant", "这段往事已经足够整理，可以先看看回忆草稿。"))
        val info = JSONObject().put("guided_interview", JSONObject().put("module_selected", selectedModule.isNotBlank()).put("module", selectedModule))
        return JSONObject().put("session", JSONObject().put("id", sessionId).put("status", "active").put("version", 1).put("information", info))
            .put("messages", list).put("can_generate", answered)
            .put("generation_offer", if (answered) JSONObject().put("message_id", replyId) else JSONObject.NULL)
            .put("life_overview", if (life) outline() else JSONObject.NULL)
            .put("current_message_ids", JSONArray((0 until list.length()).map { list.getJSONObject(it).getString("id") }))
    }
    private fun outline(): JSONObject {
        val ids = listOf("SK01", "SK01b", "SK01c", "SK02", "SK03", "SK03b", "SK03c", "SK03d", "SK04", "SK05", "SK06")
        return JSONObject().put("required", true).put("status", lifeStatus).put("version", lifeVersion).put("question_number", 1).put("total_questions", 11)
            .put("question", "您大概是什么时候出生的？").put("question_id", "SK01")
            .put("turns", if (lifeStatus == "collecting") JSONArray().put(message(openingId, "assistant", "您大概是什么时候出生的？")) else JSONArray())
            .put("fields", JSONArray(ids.map { JSONObject().put("topic_id", it).put("status", "skipped").put("evidence", JSONArray()) }))
    }
    private fun memory() = JSONObject().put("id", draftId).put("title", title).put("summary", content).put("version", 1)
        .put("person_ids", JSONArray().put(personId)).put("source_session_id", sessionId).put("media_assets", JSONArray())
        .put("information", JSONObject().put("time", time))
    private fun draft() = JSONObject().put("id", draftId).put("revision", revision).put("memory", memory()).put("manually_edited", edits.isNotEmpty())
    private fun suggestion(id: String, field: String) = JSONObject().put("id", id).put("field", field).put("start", 0).put("length", 5)
        .put("before", "2008年").put("after", "2010年").put("context", "2008年的往事").put("ambiguous", false).put("reason", "与用户修改的回忆时间一致")
}
