package cn.shinian.app

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.SessionStore
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Opt-in only. Reads this task's newly-created synthetic family, never a user's account. */
@RunWith(AndroidJUnit4::class)
class LiveAppFlowTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private fun visible(tag: String) = compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    private fun waitFor(tag: String, timeout: Long = 45_000) { compose.waitUntil(timeout) { visible(tag) } }
    private fun capture(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "validation-screenshots").apply { mkdirs() }
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        File(folder, "$name.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun isolatedFamilyCanLoginRestoreBrowseAndBuildMemoir() {
        compose.activityRule.scenario.onActivity {
            it.requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        }
        compose.waitUntil(10_000) {
            compose.activity.resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_PORTRAIT
        }
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val file = File(context.filesDir, "live-validation.private.json")
        assumeTrue("Run only after staging this verifier's isolated synthetic account", file.exists())
        val credentials = JSONObject(file.readText())
        assertEquals("shinian-android-20261021", credentials.getString("verification_owner"))
        compose.waitUntil(30_000) { visible("login.username") || visible("tab.0") }
        if (visible("login.username")) {
            capture("01-login")
            compose.onNodeWithTag("login.register").performScrollTo().performClick()
            waitFor("register.username")
            capture("02-register")
            compose.onNodeWithTag("register.login").performScrollTo().performClick()
            compose.onNodeWithTag("login.username").performTextReplacement(credentials.getString("username"))
            compose.onNodeWithTag("login.password").performTextReplacement(credentials.getString("password"))
            compose.onNodeWithTag("login.submit").performScrollTo().performClick()
        }
        waitFor("tab.0")
        waitFor("home.featured")
        val session = SessionStore(context).load() ?: error("Device session was not persisted")
        assertEquals(credentials.getString("family_id"), session.familyId)
        val repository = BackendRepository(session)
        val people = runBlocking { repository.members() }
        val person = people.single { it.id == credentials.getString("person_id") }
        compose.waitUntil(45_000) { compose.onAllNodesWithContentDescription("回忆照片").fetchSemanticsNodes().isNotEmpty() }
        capture("03-home")
        compose.activityRule.scenario.recreate()
        waitFor("tab.0")
        waitFor("home.featured")
        assertEquals(session.token, SessionStore(context).load()?.token)
        compose.onNodeWithTag("tab.1").performClick()
        waitFor("member.${person.id}")
        capture("04-select-person")
        compose.onNodeWithTag("members.addAnother").performScrollTo().performClick()
        waitFor("member.realName")
        capture("05-add-person")
        compose.onNodeWithTag("member.close").performClick()
        compose.onNodeWithTag("tab.2").performClick()
        waitFor("film.person.${person.name}")
        capture("06-family-film")
        compose.onNodeWithTag("film.person.${person.name}").performScrollTo().performClick()
        waitFor("person-memoir")
        capture("07-person")
        compose.onNodeWithTag("person-memoir").performScrollTo().performClick()
        waitFor("memoir-cover-preview")
        compose.waitUntil(45_000) {
            compose.onAllNodes(hasText("下一步 · 故事与照片") and isEnabled()).fetchSemanticsNodes().isNotEmpty()
        }
        val book = runBlocking { repository.getMemoir(person.id) }
        compose.waitUntil(45_000) {
            book.settings.coverPhotos.all { photo ->
                File(context.filesDir, "accounts/${session.scopeKey}/memoirs/${person.id}/photos/${photo.id}.jpg").exists()
            }
        }
        compose.waitForIdle()
        waitFor("memoir-cover-preview")
        capture("08-memoir-cover")
        compose.onNodeWithText("下一步 · 故事与照片").performClick()
        capture("09-memoir-stories")
        compose.onNodeWithText("生成整本预览").performClick()
        compose.waitUntil(90_000) { compose.onAllNodesWithContentDescription("第 1 页").fetchSemanticsNodes().isNotEmpty() }
        capture("10-memoir-pdf")
        compose.onNodeWithContentDescription("关闭回忆录").performClick()
        compose.onNodeWithTag("browse.back").performClick()
        compose.onNodeWithTag("tab.0").performClick()
        compose.onNodeWithTag("home.allMemories").performScrollTo().performClick()
        waitFor("memories.list")
        capture("11-all-memories")
        val memories = runBlocking { repository.memories() }
        val memory = memories.first()
        compose.onNodeWithTag("memories.list").performScrollToNode(hasTestTag("memory.card.${memory.id}"))
        compose.onNodeWithTag("memory.card.${memory.id}").performClick()
        capture("12-memory")
        compose.onNodeWithTag("browse.back").performClick()
        compose.onNodeWithTag("tab.3").performClick()
        capture("13-profile")
        compose.onNodeWithText("设置", substring = false).performScrollTo().performClick()
        waitFor("settings.careMode")
        capture("14-settings")
        compose.onNodeWithTag("settings.careMode").performClick()
        waitFor("home.newMemory")
        capture("15-care-home")
        compose.onNodeWithTag("tab.2").performClick()
        capture("16-care-memories")
        compose.onNodeWithTag("tab.3").performClick()
        capture("17-care-more")
        compose.onNodeWithTag("care.switchStandard").performScrollTo().performClick()
        compose.onNode(hasText("切换普通模式") and hasAnyAncestor(isDialog())).performClick()
        waitFor("tab.1")
        compose.onNodeWithTag("tab.1").performClick()
        compose.onNodeWithTag("member.${person.id}").performClick()
        waitFor("chat.history")
        compose.waitUntil(45_000) { compose.onAllNodesWithContentDescription("讲述照片", substring = true).fetchSemanticsNodes().isNotEmpty() }
        compose.waitUntil(45_000) { compose.onAllNodes(hasTestTag("chat.input") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        capture("18-interview-chat")
        file.delete()
    }
}
