package cn.shinian.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.*
import cn.shinian.app.ui.browse.MemoryDetailScreen
import cn.shinian.app.ui.browse.MemoriesScreen
import cn.shinian.app.ui.theme.ShinianTheme
import java.io.File
import kotlinx.coroutines.CompletableDeferred
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MemoryDeleteFeedbackTest {
    @get:Rule val compose = createComposeRule()
    private val person = Person("fc15d63d-6a8c-4572-8743-d08cf1f6c5c1", "外婆", "外婆", "1948-06-01", 1)
    private val memory = Memory("50847b40-175f-4a9e-89aa-576c72f3a1dd", "院子里的桂花香", "小时候，外婆总在院子里等我们回来。",
        personIds = listOf(person.id), personName = person.name)
    private fun repository() = BackendRepository(AuthSession("http://127.0.0.1", "ea28ff04-a728-4efa-8c2c-9dbdc111cace",
        "b19a6d11-f176-4189-a532-d5ff36495451", "synthetic_family", false, "test-token", "2030-01-01T00:00:00Z"))

    @Test fun deletionWaitsForAcknowledgementThenReturnsToUpdatedList() {
        val acknowledgement = CompletableDeferred<Unit>()
        var deleted by mutableStateOf(false)
        val repository = repository()
        compose.setContent { ShinianTheme {
            if (deleted) MemoriesScreen(listOf(person.copy(memoryCount = 0)), emptyList())
            else MemoryDetailScreen(memory, listOf(person), repository,
                deleteMemory = { acknowledgement.await() }, onDeleted = { deleted = true })
        } }
        capture("android-memory-before-delete")
        confirmDelete()
        compose.runOnIdle { assertFalse(deleted) }
        compose.onNodeWithTag("browse.back").assertIsNotEnabled()
        acknowledgement.complete(Unit)
        compose.waitUntil(5_000) { deleted }
        compose.onAllNodesWithText(memory.title).assertCountEquals(0)
        capture("android-memory-after-delete")
        repository.invalidate()
    }

    @Test fun rejectedDeletionLeavesStoryAvailableAndActionsCanBeRetried() {
        var deleted = false
        val repository = repository()
        compose.setContent { ShinianTheme {
            MemoryDetailScreen(memory, listOf(person), repository, deleteMemory = {
                throw AuthException(AuthErrorKind.Network, "暂时无法删除，请重试。")
            }, onDeleted = { deleted = true })
        } }
        confirmDelete()
        compose.onNodeWithText("暂时无法删除，请重试。").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("memory.actions").assertIsEnabled()
        compose.runOnIdle { assertFalse(deleted) }
        repository.invalidate()
    }

    private fun confirmDelete() {
        compose.onNodeWithTag("memory.actions").performClick()
        compose.onNodeWithText("删除整段回忆", substring = false).performClick()
        compose.onNodeWithText("确认删除整段", substring = false).performClick()
    }

    private fun capture(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        val directory = File(instrumentation.targetContext.getExternalFilesDir(null), "performance-validation").apply { mkdirs() }
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        File(directory, "$name.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
