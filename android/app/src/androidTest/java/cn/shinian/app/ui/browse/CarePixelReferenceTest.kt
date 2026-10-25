package cn.shinian.app.ui.browse

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.os.Build
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import android.widget.DatePicker
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.JournalBottomBar
import cn.shinian.app.ui.care.CareBackdrop
import cn.shinian.app.ui.theme.ShinianTheme
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Current iOS offline fixture, measured only inside its 402 × 778 pt content viewport. */
@OptIn(ExperimentalLayoutApi::class)
@RunWith(AndroidJUnit4::class)
class CarePixelReferenceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var fixture: CarePixelFixtures
    private var usedDensity = 1f

    @Before fun stageLocalFixture() {
        fixture = CarePixelFixtures(instrumentation.targetContext, instrumentation.context)
        fixture.stagePortraits()
    }

    @After fun removeOnlyLocalFixture() { if (::fixture.isInitialized) fixture.cleanup() }

    @Test fun captureCurrentIosBrowseReferencePages() {
        var screen by mutableStateOf("home")
        compose.runOnUiThread { compose.activity.enableEdgeToEdge() }
        compose.setContent {
            ShinianTheme {
                val originalDensity = LocalDensity.current
                val context = LocalContext.current
                val scopedContext = remember(context) {
                    object : ContextWrapper(context) {
                        override fun getSharedPreferences(name: String?, mode: Int): SharedPreferences =
                            super.getSharedPreferences(if (name == "journal_preferences") fixture.preferenceName else name, mode)
                    }
                }
                CompositionLocalProvider(LocalDensity provides Density(originalDensity.density, fontScale = 1f), LocalContext provides scopedContext) {
                    SideEffect { usedDensity = originalDensity.density }
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopStart) {
                        CareBackdrop(Modifier.requiredSize(402.dp, 778.dp)
                            // Consume rather than add padding: iOS status/home safe areas are outside this reference.
                            .consumeWindowInsets(WindowInsets.systemBars.union(WindowInsets.ime)).testTag("reference.viewport")) {
                            ProvideBrowseEnvironment(fixture.repository) {
                                key(screen) { ReferencePage(screen) }
                            }
                        }
                    }
                }
            }
        }
        val screenshots = JSONArray()
        val pages = listOf("home", "profile", "select", "add", "memories", "memories-detail", "story", "film", "family-all", "person", "settings", "privacy", "memory-editor")
        pages.forEach { page ->
            compose.runOnIdle { screen = page }
            if (page == "add") fillSameAddPersonValuesAsIos()
            awaitImages(page)
            screenshots.put(capture(page))
        }
        assertTrue("All requests must be locally intercepted fixture image reads", fixture.unexpectedRequests.isEmpty())
        assertEquals(4, fixture.people.size)
        assertEquals(18, fixture.memories.size)
        val report = JSONObject().put("viewport_dp", JSONArray(listOf(402, 778))).put("font_scale", 1)
            .put("density", usedDensity).put("screenshots", screenshots).put("people", 4).put("memories", 18)
            .put("production_network_used", false).put("fixture_scope", fixture.scope)
            .put("requests", JSONArray(fixture.requests.toList()))
            .put("notes", JSONArray(listOf(
                "memories.png is the root memories page with tabs and corresponds to iOS --design-screen film; memories-detail.png has a toolbar and no tabs and corresponds to iOS --design-screen memories.",
                "film.png is a component-only family-film rendering, not an actual care root route, and is excluded from selected reference comparisons. Compare family-all for the real family-management route.",
                "add.png is filled by real role/name actions and an in-app DatePicker update/confirm to grandpa / 陈建国 / 1946-03-12; the add/submit action is never clicked.",
                "The iOS offline grandpa film applies a preview-only three-title priority; Android component keeps its production year ordering.",
                "Privacy photo-permission wording remains Android-specific and accurate; layout and typography follow current iOS.",
                "No status bars, navigation bars or keyboard insets are included in reference.viewport; no system font, keyboard or capture settings are changed.",
                "Reference reading preferences and portraits exist only in the unique synthetic fixture scope and are removed afterwards."
            )))
        File(output(), "manifest.json").writeText(report.toString(2))
    }

    @Composable
    private fun ReferencePage(screen: String) {
        val people = fixture.people
        val memories = fixture.memories
        val repository = fixture.repository
        val tab = when (screen) { "profile" -> 3; "memories" -> 2; else -> 0 }
        val hasTabs = screen in listOf("home", "profile", "memories")
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f)) {
                when (screen) {
                    "home" -> HomeScreen(people, memories, care = true)
                    "profile" -> ProfileScreen(people, memories, fixture.scope, care = true)
                    "select" -> PersonSelectionScreen(people, care = true)
                    "add" -> AddPersonScreen(care = true)
                    "memories" -> MemoriesScreen(people, memories, care = true, isRoot = true)
                    "memories-detail" -> MemoriesScreen(people, memories, care = true, isRoot = false)
                    "story" -> MemoryDetailScreen(memories.first(), people, repository, care = true)
                    "film" -> FamilyFilmScreen(people, memories, care = true, storageScope = fixture.scope)
                    "family-all" -> FamilyFilmScreen(people, memories, care = true, allPeople = true, storageScope = fixture.scope)
                    "person" -> PersonDetailScreen(fixture.grandpa, memories, care = true, storageScope = fixture.scope)
                    "settings" -> SettingsScreen(care = true)
                    "privacy" -> PrivacyScreen(care = true)
                    "memory-editor" -> MemoryEditorScreen(memories.first(), repository, care = true)
                }
            }
            if (hasTabs) JournalBottomBar(tab, true) {}
        }
    }

    private fun fillSameAddPersonValuesAsIos() {
        compose.onNodeWithTag("member.role.爷爷").performScrollTo().performClick()
        compose.onNodeWithTag("member.realName").performScrollTo().performTextInput("陈建国")
        compose.onNodeWithTag("member.realName").performImeAction()
        compose.onNodeWithTag("member.birthday").performScrollTo().performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("member.confirmBirthday").fetchSemanticsNodes().isNotEmpty() }
        // This changes only the DatePicker widget inside this test-hosted sheet.
        // It neither changes the device date/locale nor submits a person to any API.
        compose.runOnUiThread {
            fun datePickers(view: View): List<DatePicker> = if (view is DatePicker) listOf(view)
                else if (view is ViewGroup) (0 until view.childCount).flatMap { datePickers(view.getChildAt(it)) } else emptyList()
            val roots = if (Build.VERSION.SDK_INT >= 29) WindowInspector.getGlobalWindowViews() else listOf(compose.activity.window.decorView)
            val picker = roots.flatMap { datePickers(it) }.distinct().singleOrNull()
            check(picker != null) { "Expected exactly one in-app birthday DatePicker in the test host" }
            picker.updateDate(1946, 2, 12)
        }
        compose.onNodeWithTag("member.confirmBirthday").performClick()
        compose.onNodeWithTag("member.add").assertIsEnabled()
        compose.onNodeWithText("先记下家人的名字").performScrollTo()
    }

    private fun awaitImages(page: String) {
        compose.waitForIdle()
        var settledAt = 0L
        try {
            compose.waitUntil(20_000) {
                val viewport = compose.onNodeWithTag("reference.viewport", useUnmergedTree = true).fetchSemanticsNode().boundsInRoot
                val visibleLoading = compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.ProgressBarRangeInfo), useUnmergedTree = true)
                    .fetchSemanticsNodes().any { node ->
                        val bounds = node.boundsInRoot
                        val overlapWidth = minOf(bounds.right, viewport.right) - maxOf(bounds.left, viewport.left)
                        val overlapHeight = minOf(bounds.bottom, viewport.bottom) - maxOf(bounds.top, viewport.top)
                        val progress = node.config[SemanticsProperties.ProgressBarRangeInfo]
                        // PullToRefresh keeps an idle, determinate zero-progress node in its semantics tree.
                        // Only an actually visible loading indicator inside the captured viewport blocks capture.
                        bounds.width > 1f && bounds.height > 1f && overlapWidth > 1f && overlapHeight > 1f &&
                            (progress == ProgressBarRangeInfo.Indeterminate || progress.current > progress.range.start && progress.current < progress.range.endInclusive)
                    }
                val now = SystemClock.uptimeMillis()
                val requestsFinished = fixture.activeRequests.get() == 0 && now - fixture.lastRequestCompletedAt.get() >= 250
                if (visibleLoading || !requestsFinished) settledAt = 0L else if (settledAt == 0L) settledAt = now
                !visibleLoading && requestsFinished && now - settledAt >= 250
            }
        } catch (failure: Throwable) {
            recordImageWaitFailure(page, failure)
            throw AssertionError("Care pixel reference page '$page' did not finish loading; see $page-await-failure.json and $page-semantics.txt", failure)
        }
        compose.waitForIdle()
    }

    private fun recordImageWaitFailure(page: String, failure: Throwable) {
        val nodes = runCatching {
            compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.ProgressBarRangeInfo), useUnmergedTree = true).fetchSemanticsNodes()
                .map { node -> JSONObject().put("id", node.id).put("bounds", node.boundsInRoot.toString())
                    .put("progress", node.config[SemanticsProperties.ProgressBarRangeInfo].toString()) }
        }.getOrElse { emptyList() }
        val tree = runCatching {
            val roots = compose.onAllNodes(isRoot(), useUnmergedTree = true)
            roots.fetchSemanticsNodes().indices.joinToString("\n\n") { index -> "ROOT $index\n" + roots[index].printToString() }
        }.getOrElse { "Could not print semantics: ${it.message}" }
        File(output(), "$page-semantics.txt").writeText(tree)
        File(output(), "$page-await-failure.json").writeText(JSONObject().put("page", page)
            .put("error", failure.toString()).put("active_requests", fixture.activeRequests.get())
            .put("last_request_completed_at", fixture.lastRequestCompletedAt.get()).put("requests", JSONArray(fixture.requests.toList()))
            .put("unexpected_requests", JSONArray(fixture.unexpectedRequests.toList())).put("progress_nodes", JSONArray(nodes)).toString(2))
        runCatching { capture("$page-failure") }
        println("Care pixel reference loading failure on page '$page'; diagnostics: ${output().absolutePath}")
        println(tree)
    }

    private fun capture(name: String): JSONObject {
        val dialogs = compose.onAllNodes(isDialog()).fetchSemanticsNodes()
        val node = if (dialogs.isNotEmpty()) compose.onNode(isDialog()) else compose.onNodeWithTag("reference.viewport", useUnmergedTree = true)
        val bitmap = node.captureToImage().asAndroidBitmap()
        val width = bitmap.width
        val height = bitmap.height
        try { File(output(), "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { bitmap.recycle() }
        val iosRoute = when (name) { "memories" -> "film"; "memories-detail" -> "memories"; "memory-editor" -> "memory-edit"; "film" -> JSONObject.NULL; else -> name }
        return JSONObject().put("page", name).put("file", "$name.png").put("width_px", width).put("height_px", height)
            .put("dialog", dialogs.isNotEmpty()).put("ios_design_screen", iosRoute).put("selected_for_reference", name != "film")
    }

    private fun output() = File(instrumentation.targetContext.getExternalFilesDir(null), "care-pixel-reference").apply { mkdirs() }
}
