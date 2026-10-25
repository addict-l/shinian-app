package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.unit.dp
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.JournalBottomBar
import cn.shinian.app.data.*
import cn.shinian.app.ui.browse.*
import cn.shinian.app.ui.theme.*
import kotlinx.serialization.json.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Only synthetic in-memory UI data. No auth, network, account writes or system input changes. */
@RunWith(AndroidJUnit4::class)
class CareModeSyncTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val person = Person("11111111-1111-1111-1111-111111111111", "李明", "爷爷", "1940-01-01", 2)
    private val mother = Person("22222222-2222-2222-2222-222222222222", "陈芳", "妈妈", "1965-06-01", 1)
    private val story = Memory("story-1", "家门前的老槐树", "小时候，家门前有一棵老槐树。夏天傍晚，家人围坐在树下，听奶奶讲故事。", personIds = listOf(person.id), personName = person.name,
        primaryPersonId = person.id, time = InformationDimension("known", "1960年"), place = InformationDimension("known", "老家"), feeling = InformationDimension("known", "温暖"), createdAt = "2026-10-25")
    private val other = Memory("story-2", "一家人的团圆饭", "过年时，全家围在一起包饺子。", personIds = listOf(mother.id), personName = mother.name, primaryPersonId = mother.id, createdAt = "2026-10-24")
    private val preferences get() = instrumentation.targetContext.getSharedPreferences("journal_preferences", 0)
    private var oldReadingScale: Float? = null
    private var backedUpReadingScale = false

    @After fun restoreReadingPreference() {
        if (backedUpReadingScale) preferences.edit().also { edit -> oldReadingScale?.let { edit.putFloat("care.readingScale", it) } ?: edit.remove("care.readingScale") }.commit()
    }

    private fun show(content: @Composable () -> Unit) {
        compose.runOnUiThread { compose.activity.enableEdgeToEdge(); applyShinianWindowPolicy(compose.activity.window) }
        compose.setContent { ShinianTheme { JournalBackdrop(Modifier.fillMaxSize().shinianContentInsets()) { content() } } }
    }

    private fun shot(name: String) {
        compose.waitForIdle()
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "care-sync-screenshots").apply { mkdirs() }
        val target = if (compose.onAllNodes(isDialog()).fetchSemanticsNodes().isNotEmpty()) compose.onNode(isDialog()) else compose.onRoot()
        val bitmap = target.captureToImage().asAndroidBitmap()
        try { File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { bitmap.recycle() }
    }

    @Test fun homeHasTheNewStoryCardAndRecentMemoryOpens() {
        var opened = ""
        show { HomeScreen(listOf(person), listOf(story), care = true, onMemory = { opened = it.id }) }
        compose.onNodeWithTag("home.newMemory").assertIsDisplayed()
        compose.onNodeWithText("今天想起了谁？说给我听听。").assertIsDisplayed()
        shot("01-care-home")
        compose.onNodeWithTag("memory.card.${story.id}").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(story.id, opened) }
    }

    @Test fun careTabsOpenEachPageAndAnnounceTheSelectedTab() {
        var selected by mutableIntStateOf(0)
        show {
            Column(Modifier.fillMaxSize()) {
                Box(Modifier.weight(1f)) {
                    when (selected) {
                        2 -> MemoriesScreen(listOf(person, mother), listOf(story, other), care = true, isRoot = true)
                        3 -> ProfileScreen(listOf(person, mother), listOf(story, other), care = true)
                        else -> HomeScreen(listOf(person), listOf(story), care = true)
                    }
                }
                JournalBottomBar(selected, true) { selected = it }
            }
        }
        compose.onNodeWithTag("tab.0").assertIsSelected().assertIsDisplayed()
        compose.onNodeWithTag("tab.1").assertDoesNotExist()
        shot("00-care-home-with-tabs")
        compose.onNodeWithTag("tab.2").performClick().assertIsSelected()
        compose.onNodeWithTag("care.memories.search").assertIsDisplayed()
        compose.onNodeWithTag("tab.3").performClick().assertIsSelected()
        compose.onNodeWithTag("care.switchStandard").performScrollTo().assertIsDisplayed()
        shot("00-care-more-with-tabs")
        compose.onNodeWithTag("tab.0").performClick().assertIsSelected()
        compose.onNodeWithTag("home.newMemory").assertIsDisplayed()
    }

    @Test fun careCollectionFiltersByPersonAndSearchesActualStoryText() {
        show { MemoriesScreen(listOf(person, mother), listOf(story, other), care = true, isRoot = true) }
        shot("02-care-memories")
        compose.onNodeWithTag("care.filter.${mother.id}").performClick()
        compose.onNodeWithTag("memory.card.${story.id}").assertDoesNotExist()
        compose.onNodeWithTag("memory.card.${other.id}").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("care.filter.all").performScrollTo().performClick()
        compose.onNodeWithTag("care.memories.search").performScrollTo().performTextInput("老槐树")
        compose.onNodeWithTag("memory.card.${other.id}").assertDoesNotExist()
        compose.onNodeWithTag("memory.card.${story.id}").performScrollTo().assertIsDisplayed()
    }

    @Test fun moreConfirmsSwitchingAndPersonSelectionKeepsItsIdentity() {
        var mode: Boolean? = null
        show { ProfileScreen(listOf(person, mother), listOf(story, other), care = true, onCareChange = { mode = it }) }
        shot("03-care-more")
        compose.onNodeWithTag("care.switchStandard").performScrollTo().performClick()
        compose.runOnIdle { assertNull(mode) }
        compose.onNode(hasText("切换普通模式") and hasAnyAncestor(isDialog())).performClick()
        compose.runOnIdle { assertEquals(false, mode) }
    }

    @Test fun familySelectionUsesLargeCardsAndCorrectPerson() {
        var selected = ""
        show { PersonSelectionScreen(listOf(person, mother), care = true, onSelect = { selected = it.id }) }
        shot("04-care-family")
        compose.onNodeWithTag("member.${mother.id}").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(mother.id, selected) }
    }

    @Test fun addingFamilyStillRequiresNameRoleAndBirthday() {
        var added: Triple<String, String, String>? = null
        show { AddPersonScreen(care = true, onAdd = { name, role, birthday -> added = Triple(name, role, birthday) }) }
        shot("05-care-add-family")
        compose.onNodeWithTag("member.add").assertIsNotEnabled()
        compose.onNodeWithTag("member.role.爷爷").performScrollTo().performClick()
        compose.onNodeWithTag("member.realName").performScrollTo().performTextInput("李明")
        compose.onNodeWithTag("member.add").assertIsNotEnabled()
        compose.onNodeWithTag("member.birthday").performScrollTo().performClick()
        compose.onNodeWithTag("member.confirmBirthday").performClick()
        compose.onNodeWithTag("member.add").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(Triple("李明", "爷爷", "1950-01-01"), added) }
    }

    @Test fun reviewButtonsAreSymmetricAndAllOriginalQuotesRemain() {
        val overview = buildJsonObject { put("fields", buildJsonArray {
            add(buildJsonObject { put("topic_id", "SK01"); put("title", "出生时间"); put("status", "known"); put("evidence", buildJsonArray { add(buildJsonObject { put("quote", "一九四零年出生在乡下。") }) }) })
        }) }
        var confirmed = 0
        show { CareLifeOverview(overview, false, true, false, {}, {}, { confirmed++ }, {}) }
        val left = compose.onNodeWithTag("life.details").fetchSemanticsNode().boundsInRoot
        val right = compose.onNodeWithTag("care.life.history").fetchSemanticsNode().boundsInRoot
        assertEquals(left.width, right.width, 1f); assertEquals(left.height, right.height, 1f)
        compose.onNodeWithText("一九四零年出生在乡下。").assertIsDisplayed()
        shot("06-care-life-review")
        compose.onNodeWithTag("life.confirm").performClick()
        compose.runOnIdle { assertEquals(1, confirmed) }
    }

    @Test fun sixTopicsOpenDirectlyAndPendingCommandsCannotSelect() {
        var selected = ""
        var enabled by mutableStateOf(true)
        show { CareLifeOverview(null, true, enabled, false, {}, {}, {}, { selected = it }) }
        shot("07-care-topics")
        compose.onNodeWithTag("life.module.family").performScrollTo().performClick()
        compose.runOnIdle { assertEquals("family", selected); enabled = false; selected = "" }
        compose.onNodeWithTag("life.module.childhood").performScrollTo().performClick()
        compose.runOnIdle { assertEquals("", selected) }
    }

    @Test fun keyboardNarrationClearsAndCanBeTypedAgainWithoutSendingEarly() {
        var value by mutableStateOf("")
        var sent = ""
        val dictation = MandarinDictation(instrumentation.targetContext) { value = it }
        show {
            DisposableEffect(Unit) { onDispose { dictation.cancel() } }
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp)) {
                CareNarrationComposer(value, { value = it }, true, value.isNotBlank(), false, dictation, {}, { sent = value; value = "" }, "chat")
            }
        }
        compose.onNodeWithTag("chat.input.keyboard").performScrollTo().performClick()
        compose.onNodeWithTag("chat.input").performTextInput("第一段文字")
        compose.onNodeWithTag("chat.input.clear").performScrollTo().performClick()
        compose.onNodeWithTag("chat.input.keyboard").performScrollTo().performClick()
        compose.onNodeWithTag("chat.input").performTextInput("清空之后，仍能继续输入。")
        compose.runOnIdle { assertEquals("", sent) }
        shot("08-care-narration")
        compose.onNodeWithTag("chat.send").performScrollTo().assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals("清空之后，仍能继续输入。", sent) }
    }

    @Test fun readingSizeChangesOnlyTheStory() {
        backedUpReadingScale = true
        oldReadingScale = if (preferences.contains("care.readingScale")) preferences.getFloat("care.readingScale", 1f) else null
        preferences.edit().putFloat("care.readingScale", 1f).commit()
        show { CareStoryScreen(story, listOf(person), {}) }
        val before = compose.onNodeWithTag("care.story.body").fetchSemanticsNode().size.height
        compose.onNodeWithTag("care.reading.larger").performClick().performClick()
        val after = compose.onNodeWithTag("care.story.body").fetchSemanticsNode().size.height
        assertTrue(after > before)
        compose.onNodeWithTag("care.reading.speak").assertIsDisplayed()
        shot("09-care-reading")
    }

    @Test fun historyShowsOneQuestionAnswerPairAtATime() {
        val session = AuthSession("https://care-history.invalid", UUID.randomUUID().toString(), UUID.randomUUID().toString(), "synthetic", false, "synthetic-token", "2099-01-01T00:00:00Z")
        val repository = BackendRepository(session, okhttp3.OkHttpClient.Builder().addInterceptor { error("History UI must not issue a network request") }.build())
        var closed = false
        show { CareHistoryDialog(listOf(ChatMessage("q1", "assistant", "小时候的家是什么样？"), ChatMessage("a1", "user", "家里有一个小院子。"),
            ChatMessage("q2", "assistant", "后来在哪里工作？"), ChatMessage("a2", "user", "在镇上的工厂。")), repository, {}, { closed = true }) }
        compose.onNodeWithText("家里有一个小院子。").assertIsDisplayed()
        compose.onNodeWithText("在镇上的工厂。").assertDoesNotExist()
        compose.onNodeWithTag("care.history.previous").assertIsNotEnabled()
        compose.onNodeWithTag("care.history.next").performClick()
        compose.onNodeWithText("在镇上的工厂。").assertIsDisplayed()
        compose.onNodeWithText("家里有一个小院子。").assertDoesNotExist()
        compose.onNodeWithTag("care.history.previous").performClick()
        compose.onNodeWithText("家里有一个小院子。").assertIsDisplayed()
        shot("10-care-history")
        compose.onNodeWithTag("care.history.next").performClick().performClick()
        compose.runOnIdle { assertTrue(closed) }
        repository.invalidate()
    }
}
