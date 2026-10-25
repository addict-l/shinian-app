package cn.shinian.app.ui.chat

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.*
import cn.shinian.app.ui.browse.CarePixelFixtures
import cn.shinian.app.ui.browse.ProvideBrowseEnvironment
import cn.shinian.app.ui.care.CareBackdrop
import cn.shinian.app.ui.theme.ShinianTheme
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
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger

/** Current iOS JournalDemoAPI text/images; all transport terminates locally. No system settings writes. */
@OptIn(ExperimentalLayoutApi::class)
@RunWith(AndroidJUnit4::class)
class CareChatPixelReferenceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var fixture: CarePixelFixtures
    private lateinit var transport: CareReferenceTransport
    private lateinit var repository: BackendRepository
    private var usedDensity = 1f
    private var keyboard: androidx.compose.ui.platform.SoftwareKeyboardController? = null
    private val captures = JSONArray()

    @Before fun stageOnlySyntheticFamily() {
        fixture = CarePixelFixtures(instrumentation.targetContext, instrumentation.context)
        fixture.stagePortraits()
        transport = CareReferenceTransport(fixture, instrumentation.context)
        repository = BackendRepository(fixture.session, OkHttpClient.Builder().addInterceptor(transport).build())
    }

    @After fun cleanupOnlySyntheticScope() {
        try {
            // This host owns only fixture ViewModels. Cancel their scoped jobs before removing their files.
            compose.runOnUiThread { compose.activity.viewModelStore.clear() }
            if (::repository.isInitialized) repository.invalidate()
            if (::transport.isInitialized) {
                assertTrue("Every HTTP request must be served by this local fixture: ${transport.unexpected}", transport.unexpected.isEmpty())
                val report = JSONObject().put("viewport_dp", JSONArray(listOf(402, 778))).put("font_scale", 1).put("density", usedDensity)
                    .put("production_network_used", false).put("scope", fixture.scope).put("captures", captures)
                    .put("requests", JSONArray(transport.requests.toList()))
                    .put("notes", JSONArray(listOf(
                        "Uses actual ChatScreen and ChatController for opening, draft generation, editing and explicit save.",
                        "History uses the same CareHistoryPage rendered inside the production Dialog, directly in the reference viewport.",
                        "Saved reference uses CareSavedResult with the synthetic loaded list plus the one new saved draft; no production count is inferred.",
                        "System status/home/IME insets are consumed only by this composition; device font and keyboard settings are untouched."
                    )))
                File(output(), "chat-${transport.scenario}-manifest.json").writeText(report.toString(2))
            }
        } finally {
            if (::fixture.isInitialized) fixture.cleanup()
        }
    }

    private fun show(scenario: String, content: @Composable () -> Unit = { ChatScreen(fixture.grandpa, repository, true, {}, {}, {}) }) {
        transport.scenario = scenario
        compose.runOnUiThread { compose.activity.enableEdgeToEdge() }
        compose.setContent {
            ShinianTheme {
                val original = LocalDensity.current
                val context = LocalContext.current
                val scopedContext = remember(context) {
                    object : ContextWrapper(context) {
                        override fun getSharedPreferences(name: String?, mode: Int): SharedPreferences =
                            super.getSharedPreferences(if (name == "journal_preferences") fixture.preferenceName else name, mode)
                    }
                }
                CompositionLocalProvider(LocalDensity provides Density(original.density, fontScale = 1f), LocalContext provides scopedContext) {
                    SideEffect { usedDensity = original.density }
                    keyboard = LocalSoftwareKeyboardController.current
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopStart) {
                        CareBackdrop(Modifier.requiredSize(402.dp, 778.dp).consumeWindowInsets(WindowInsets.systemBars.union(WindowInsets.ime))
                            .testTag("reference.viewport")) {
                            ProvideBrowseEnvironment(fixture.repository) { content() }
                        }
                    }
                }
            }
        }
    }

    @Test fun captureChatDraftEditorHistoryAndSavedFromRealController() {
        var screen by mutableStateOf("chat")
        show("chat") {
            key(screen) {
                when (screen) {
                    "saved-reference" -> CareSavedResult(transport.savedMemory, fixture.grandpa, false, {}, {}, {},
                        memoryCount = (fixture.memories + transport.savedMemory).distinctBy { it.id }.count { fixture.grandpa.id in it.personIds })
                    else -> ChatScreen(fixture.grandpa, repository, true, {}, {}, {})
                }
            }
        }
        waitTag("chat.generate")
        capture("chat")
        compose.onNodeWithTag("chat.generate").assertIsDisplayed().performClick()
        waitTag("memory.save")
        assertEquals(0, transport.confirmations.get())
        capture("review")
        compose.onNodeWithTag("care.draft.edit").assertIsDisplayed().performClick()
        waitTag("draft.title")
        compose.runOnIdle { keyboard?.hide() }
        capture("draft-editor")
        // Unchanged edits are valid: this exercises the real editor endpoint without changing reference text.
        compose.onNodeWithTag("draft.keepEdits").assertIsDisplayed().performClick()
        waitTag("memory.save")
        assertEquals(1, transport.edits.get())
        assertEquals(0, transport.confirmations.get())
        compose.onNodeWithTag("memory.save").assertIsDisplayed().performClick()
        waitTag("care.saved.read")
        assertEquals(1, transport.confirmations.get())
        capture("saved-controller")
        compose.runOnIdle { screen = "saved-reference" }
        waitTag("care.saved.read")
        capture("saved")
    }

    @Test fun captureElevenQuestionCarePage() {
        show("care-life-question-v2")
        waitTag("life.input.keyboard")
        compose.onNodeWithText("您大概是什么时候出生的？").assertIsDisplayed()
        capture("care-life-question-v2")
    }

    @Test fun captureOriginalQuoteReviewAndRetainConfirmationBoundary() {
        var history by mutableStateOf(false)
        show("care-life-review-v2") {
            if (history) CareHistoryPage(transport.lifeMessages, repository, {}, { history = false }, fixture.grandpa)
            else ChatScreen(fixture.grandpa, repository, true, {}, {}, {})
        }
        waitTag("life.confirm")
        val left = compose.onNodeWithTag("life.details").fetchSemanticsNode().boundsInRoot
        val right = compose.onNodeWithTag("care.life.history").fetchSemanticsNode().boundsInRoot
        assertEquals(left.width, right.width, 1f); assertEquals(left.height, right.height, 1f)
        capture("care-life-review-v2")
        assertEquals(0, transport.lifeActions.get())
        compose.runOnIdle { history = true }
        waitTag("care.history.question")
        capture("history")
    }

    @Test fun captureTopicsAndOpenTheSelectedServerModule() {
        show("care-life-topics")
        waitTag("life.module.work")
        capture("care-life-topics")
        compose.onNodeWithTag("life.module.work").performScrollTo().performClick()
        waitTag("chat.generate")
        assertEquals("work", transport.selectedModule)
        assertEquals(0, transport.confirmations.get())
    }

    private fun waitTag(tag: String) = compose.waitUntil(15_000) {
        compose.onAllNodesWithTag(tag).fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
    }

    private fun capture(name: String) {
        compose.waitForIdle()
        var settledAt = 0L
        compose.waitUntil(20_000) {
            val pending = compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.ProgressBarRangeInfo)).fetchSemanticsNodes().isNotEmpty()
            val now = SystemClock.uptimeMillis()
            if (pending) settledAt = 0L else if (settledAt == 0L) settledAt = now
            !pending && now - settledAt >= 250
        }
        val dialogs = compose.onAllNodes(isDialog()).fetchSemanticsNodes()
        val node = if (dialogs.isNotEmpty()) compose.onNode(isDialog()) else compose.onNodeWithTag("reference.viewport", useUnmergedTree = true)
        val bitmap = node.captureToImage().asAndroidBitmap()
        File(output(), "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        captures.put(JSONObject().put("page", name).put("width_px", bitmap.width).put("height_px", bitmap.height).put("dialog", dialogs.isNotEmpty()))
        assertEquals(402 * usedDensity, bitmap.width.toFloat(), 1f)
        assertEquals(778 * usedDensity, bitmap.height.toFloat(), 1f)
    }

    private fun output() = File(instrumentation.targetContext.getExternalFilesDir(null), "care-pixel-reference").apply { mkdirs() }
}

private class CareReferenceTransport(private val fixture: CarePixelFixtures, testContext: Context) : Interceptor {
    var scenario = "chat"
    var selectedModule = ""
    val requests = CopyOnWriteArrayList<String>()
    val unexpected = CopyOnWriteArrayList<String>()
    val confirmations = AtomicInteger()
    val edits = AtomicInteger()
    val lifeActions = AtomicInteger()
    private val sessionID = UUID.randomUUID().toString()
    private val draftID = UUID.randomUUID().toString()
    private var revision = UUID.randomUUID().toString()
    private val messageIDs = List(3) { UUID.randomUUID().toString() }
    private val dinner = fixture.memories[2]
    private val photos = mapOf(dinner.media.first().id to "dinner", fixture.memories[3].media.first().id to "grandpa")
        .mapValues { testContext.assets.open("care-reference/${it.value}.jpg").use { stream -> stream.readBytes() } }
    // JournalDemoAPI.generate creates a new memory, retaining the preview's approximate date text.
    val savedMemory = dinner.copy(id = draftID, memoryDate = null, time = dinner.time.copy(status = "approximate"), sourceSessionId = sessionID)
    val referenceMessages = listOf(
        ChatMessage(messageIDs[0], "assistant", "早上好。说起爷爷，你最先想到的是什么画面？是他常坐的那把藤椅，还是他做的某一道菜？"),
        ChatMessage(messageIDs[1], "user", "每年除夕，爷爷都会亲手包饺子，还会偷偷在一个里面放一枚硬币。", listOf(dinner.media.first(), fixture.memories[3].media.first().copy(position = 1))),
        ChatMessage(messageIDs[2], "assistant", "真温暖。那一年是谁吃到了硬币？爷爷当时说了什么？")
    )
    val lifeMessages: List<ChatMessage> get() {
        val turns = life().getJSONArray("turns")
        return List(turns.length()) { index -> turns.getJSONObject(index).let { ChatMessage(it.getString("id"), it.getString("role"), it.getString("content")) } }
    }

    @Synchronized override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val path = request.url.encodedPath
        requests += "${request.method} $path"
        val body = request.body?.let { Buffer().also(it::writeTo).readUtf8() }?.takeIf { it.isNotBlank() }?.let(::JSONObject)
        if (request.url.host != "care-reference.invalid") error("Reference transport attempted a non-fixture host")
        if (path.startsWith("/api/v1/media/") && request.method == "GET") {
            val bytes = photos[path.substringAfterLast('/')]
            if (bytes == null) unexpected += "Missing local media $path"
            return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(if (bytes == null) 404 else 200).message("Local reference image")
                .body((bytes ?: ByteArray(0)).toResponseBody("image/jpeg".toMediaType())).build()
        }
        val response: Any = when {
            path.endsWith("/auth/me") -> JSONObject().put("account_id", fixture.session.accountId).put("family_id", fixture.session.familyId).put("username", fixture.session.username)
            path.endsWith("/family-members/") -> JSONArray(fixture.people.map { JSONObject().put("id", it.id).put("name", it.name).put("relationship", it.relationship).put("birth_date", it.birthDate) })
            path.endsWith("/memories/") -> JSONArray(fixture.memories.map(::memory))
            path.endsWith("/conversation") -> snapshot()
            path.endsWith("/interview") -> { selectedModule = requireNotNull(body).getString("module"); snapshot() }
            path.endsWith("/life-overview/actions") -> { lifeActions.incrementAndGet(); snapshot() }
            path.endsWith("/draft") -> draft()
            path.endsWith("/confirm") -> { confirmations.incrementAndGet(); memory(savedMemory) }
            path.endsWith("/time-preview") -> JSONObject().put("message", "请逐项核对对应的时间文字。").put("suggestions", JSONArray())
            path.endsWith("/$draftID") -> { if (request.method == "PATCH") { edits.incrementAndGet(); revision = UUID.randomUUID().toString() }; draft() }
            else -> { unexpected += "${request.method} $path"; error("Unexpected local reference request: $path") }
        }
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("Local reference transport")
            .body(response.toString().toResponseBody("application/json".toMediaType())).build()
    }

    private fun media(value: Media) = JSONObject().put("id", value.id).put("url", value.url).put("position", value.position)
    private fun dimension(value: InformationDimension) = JSONObject().put("status", value.status).put("value", value.value ?: JSONObject.NULL)
        .put("source_message_ids", JSONArray()).put("user_edited", value.userEdited)
    private fun memory(value: Memory) = JSONObject().put("id", value.id).put("title", value.title).put("summary", value.content).put("version", value.version)
        .put("person_ids", JSONArray(value.personIds)).put("primary_person_id", value.primaryPersonId).put("memory_date", value.memoryDate ?: JSONObject.NULL)
        .put("created_at", value.createdAt).put("source_session_id", sessionID).put("media_assets", JSONArray(value.media.map(::media)))
        .put("information", JSONObject().put("time", dimension(value.time)).put("place", dimension(value.place)).put("feeling", dimension(value.feeling)))
    private fun message(value: ChatMessage) = JSONObject().put("id", value.id).put("role", value.role).put("content", value.content).put("attachments", JSONArray(value.attachments.map(::media)))
    private fun draft() = JSONObject().put("id", draftID).put("revision", revision).put("memory", memory(savedMemory)).put("manually_edited", edits.get() > 0)
    private fun snapshot(): JSONObject {
        val guided = JSONObject().put("module_selected", selectedModule.isNotEmpty()).put("module", selectedModule.ifEmpty { "childhood" })
        val info = if (scenario.startsWith("care-life")) JSONObject().put("guided_interview", guided) else JSONObject()
        return JSONObject().put("session", JSONObject().put("id", sessionID).put("status", "active").put("version", 1).put("information", info))
            .put("messages", JSONArray(referenceMessages.map(::message))).put("can_generate", true)
            .put("generation_offer", JSONObject().put("message_id", messageIDs.last())).put("current_message_ids", JSONArray(messageIDs))
            .put("life_overview", if (scenario.startsWith("care-life")) life() else JSONObject.NULL)
    }

    private fun life(): JSONObject {
        val skeleton = scenario != "care-life-topics"
        val collecting = scenario == "care-life-question-v2"
        val ids = if (skeleton) listOf("SK01", "SK01b", "SK01c", "SK02", "SK03", "SK03b", "SK03c", "SK03d", "SK04", "SK05", "SK06")
            else listOf("home", "learning", "early_work", "later_work", "family", "changes", "present")
        val questions = if (skeleton) listOf("您大概是什么时候出生的？", "您出生在哪个地方？", "您记忆中的家乡是什么样子的？", "您知道自己的名字有什么来历吗？", "您小时候主要跟谁一起生活？", "小时候家里主要靠什么维持生活？", "您有兄弟姐妹吗？", "小时候家里人相处得怎么样？", "从小到大，家里人通常怎样教导您？", "您会怎样形容自己的性格？", "想到自己这一生，您会用什么词来概括？")
            else listOf("您小时候，住在什么样的地方？", "后来在哪里读书或学手艺？", "年轻时做过哪些工作？", "后来工作和生活有哪些变化？", "您最想聊聊哪位家人？", "有没有一次生活变化，您一直记得？", "您现在的日子是怎样的？")
        val answers = if (skeleton) listOf("我是一九四八年出生的，属鼠。", "湖南湘潭乡下，一个叫石塘的村子。", "", "建国是家里长辈取的，盼着好日子。", "跟爸妈还有奶奶一起住。", "种田，农闲时我爹去镇上做木工。", "我是老大，下面两个弟弟一个妹妹。", "一家人有商有量，吃饭时最热闹。", "", "我这人慢热，认准的事会慢慢做到底。", "")
            else listOf("小时候住在乡下，和父母一起生活。", "在村里的学校读书。", "年轻时在镇上的工厂工作。", "后来仍在工厂做工。", "我最牵挂的是家人。", "后来搬到了镇上。", "现在喜欢散步、养花。")
        val states = if (skeleton) listOf("known", "known", "skipped", "known", "known", "known", "known", "known", "unknown", "known", "declined") else List(ids.size) { "known" }
        val turns = JSONArray()
        val fields = JSONArray()
        ids.forEachIndexed { index, id ->
            val answerID = UUID.nameUUIDFromBytes((id + "answer").toByteArray()).toString()
            val status = if (collecting) "pending" else states[index]
            fields.put(JSONObject().put("id", id).put("topic_id", id).put("status", status).put("evidence", if (collecting || answers[index].isEmpty()) JSONArray()
                else JSONArray().put(JSONObject().put("message_id", answerID).put("quote", answers[index]))))
            if (!collecting || index == 0) turns.put(message(ChatMessage(UUID.nameUUIDFromBytes((id + "question").toByteArray()).toString(), "assistant", questions[index])))
            if (!collecting) turns.put(message(ChatMessage(answerID, "user", answers[index].ifEmpty { mapOf("skipped" to "这题先跳过。", "unknown" to "这个记不清了。", "declined" to "这一项暂时不想讲。")[status].orEmpty() })))
        }
        return JSONObject().put("required", true).put("status", if (collecting) "collecting" else if (scenario == "care-life-topics") "confirmed" else "review")
            .put("version", 1).put("paused", false).put("fields", fields).put("turns", turns)
            .put("question_number", if (collecting) 1 else ids.size).put("total_questions", ids.size)
            .put("question_id", if (collecting) ids.first() else JSONObject.NULL).put("question", if (collecting) questions.first() else JSONObject.NULL)
    }
}
