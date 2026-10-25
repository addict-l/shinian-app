package cn.shinian.app.ui.chat

import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.union
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import cn.shinian.app.ui.care.CareBackdrop
import cn.shinian.app.ui.care.CareColors
import cn.shinian.app.ui.theme.ShinianTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercise reduced dock space directly; no keyboard, input-method or system settings change. */
@RunWith(AndroidJUnit4::class)
class CareNarrationLayoutTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun show(height: Dp, content: @Composable (MandarinDictation) -> Unit) {
        compose.setContent {
            ShinianTheme {
                val density = LocalDensity.current
                CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale = 1f)) {
                    val context = LocalContext.current
                    val dictation = remember { MandarinDictation(context) {} }
                    DisposableEffect(dictation) { onDispose { dictation.cancel() } }
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopStart) {
                        CareBackdrop(Modifier.requiredSize(363.dp, height)
                            .consumeWindowInsets(WindowInsets.systemBars.union(WindowInsets.ime)).testTag("dock.viewport")) {
                            content(dictation)
                        }
                    }
                }
            }
        }
    }

    private fun assertFullyInsideViewport(tag: String) {
        val viewport = compose.onNodeWithTag("dock.viewport").fetchSemanticsNode().boundsInRoot
        val bounds = compose.onNodeWithTag(tag).assertIsDisplayed().fetchSemanticsNode().boundsInRoot
        assertTrue("$tag has no usable height", bounds.height > 1f)
        assertTrue("$tag starts above the dock", bounds.top >= viewport.top - 1f)
        assertTrue("$tag extends below the dock", bounds.bottom <= viewport.bottom + 1f)
    }

    @Test fun longLockedNarrationScrollsWhileRetryRemainsReachable() {
        val locked = (1..100).joinToString("\n") { "第${it}段：那年夏天，我们一家人坐在院子里慢慢聊天。" }
        var retries = 0
        var writes = 0
        show(320.dp) { dictation ->
            CareNarrationComposer("", { writes++ }, enabled = false, sendEnabled = true,
                retrying = true, dictation = dictation, onMic = {}, onSend = { retries++ }, tag = "chat", pendingText = locked)
        }
        compose.onNodeWithTag("chat.input").assertDoesNotExist()
        val scroll = compose.onNodeWithTag("chat.transcript").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange]
        compose.runOnIdle { assertTrue("The complete locked text must remain scrollable", scroll.maxValue() > 0f) }
        assertFullyInsideViewport("chat.send")
        compose.onNodeWithTag("chat.transcript").performTouchInput { swipeUp() }
        compose.runOnIdle { assertTrue("The locked transcript did not scroll", scroll.value() > 0f) }
        compose.onNodeWithTag("chat.send").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(1, retries); assertEquals(0, writes) }
    }

    @Test fun fiveLineNarrationAndPhotosKeepAllActionsAboveTheDockBottom() {
        val text = "第一行讲述\n第二行讲述\n第三行讲述\n第四行讲述\n第五行讲述"
        var submitted = ""
        show(360.dp) { dictation ->
            CareNarrationComposer(text, {}, enabled = true, sendEnabled = true,
                retrying = false, dictation = dictation, onMic = {}, onSend = { submitted = text }, tag = "chat", hasPhotos = true,
                photoContent = { Box(Modifier.fillMaxWidth().height(138.dp).background(CareColors.Soft).testTag("selected.photos")) })
        }
        assertFullyInsideViewport("chat.send")
        assertFullyInsideViewport("chat.dictation")
        assertFullyInsideViewport("chat.input.clear")
        val scroll = compose.onNodeWithTag("chat.transcript").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange]
        compose.runOnIdle { assertTrue("Photos and the full transcript must remain available by scrolling", scroll.maxValue() > 0f) }
        compose.onNodeWithTag("chat.send").performClick()
        compose.runOnIdle { assertEquals(text, submitted) }
    }

    @Test fun roomyDockRetainsTheNaturalTranscriptHeight() {
        show(700.dp) { dictation ->
            CareNarrationComposer("这段讲述只有一行。", {}, enabled = true, sendEnabled = true,
                retrying = false, dictation = dictation, onMic = {}, onSend = {}, tag = "chat")
        }
        val viewport = compose.onNodeWithTag("dock.viewport").fetchSemanticsNode().boundsInRoot
        val composer = compose.onNodeWithTag("chat.composer").fetchSemanticsNode().boundsInRoot
        val scroll = compose.onNodeWithTag("chat.transcript").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange]
        compose.runOnIdle {
            assertEquals(0f, scroll.maxValue(), 1f)
            assertTrue("A flexible transcript must not stretch an ordinary dock", composer.height < viewport.height * .7f)
        }
        assertFullyInsideViewport("chat.send")
        assertFullyInsideViewport("chat.input.clear")
    }
}
