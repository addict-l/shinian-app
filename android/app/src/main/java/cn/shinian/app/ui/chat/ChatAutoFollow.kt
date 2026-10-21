package cn.shinian.app.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import cn.shinian.app.ui.theme.JournalColors as C
import cn.shinian.app.ui.theme.JournalTypography as T

@Stable
internal class ChatAutoFollow {
    var following by mutableStateOf(true)
        internal set
    internal var dragging by mutableStateOf(false)
    internal var request by mutableIntStateOf(0)

    fun resume() { following = true; request++ }
}

private data class ChatViewport(
    val count: Int, val first: Int, val offset: Int, val end: Int,
    val lastOffset: Int, val lastSize: Int, val forward: Boolean, val scrolling: Boolean,
    val dragging: Boolean, val following: Boolean, val request: Int, val content: Any?,
)

/** A final sentinel lets the list reach the end of even a message taller than its viewport. */
@Composable
internal fun rememberChatAutoFollow(list: LazyListState, contentKey: Any?): ChatAutoFollow {
    val follow = remember(list) { ChatAutoFollow() }
    val content by rememberUpdatedState(contentKey)
    LaunchedEffect(list, follow) {
        launch {
            list.interactionSource.interactions.collect { interaction ->
                when (interaction) {
                    is DragInteraction.Start -> { follow.dragging = true; follow.following = false }
                    is DragInteraction.Stop, is DragInteraction.Cancel -> follow.dragging = false
                    else -> Unit
                }
            }
        }
        fun viewport(): ChatViewport {
            val layout = list.layoutInfo
            val last = layout.visibleItemsInfo.lastOrNull()
            return ChatViewport(layout.totalItemsCount, list.firstVisibleItemIndex, list.firstVisibleItemScrollOffset,
                layout.viewportEndOffset, last?.offset ?: 0, last?.size ?: 0, list.canScrollForward,
                list.isScrollInProgress, follow.dragging, follow.following, follow.request, content)
        }
        var previous: ChatViewport? = null
        snapshotFlow { viewport() }.collect { current ->
            val before = previous
            // Accessibility and mouse scrolling may move the list without a drag interaction.
            val movedBack = before != null && (current.first < before.first ||
                current.first == before.first && current.offset < before.offset)
            if (movedBack && current.end == before?.end && current.content == before?.content &&
                current.request == before?.request && current.forward) follow.following = false
            if (!current.dragging && !current.scrolling && !current.forward) follow.following = true
            previous = current
            if (follow.following && !follow.dragging && !list.isScrollInProgress && current.count > 0 && current.forward) {
                // Recheck after layout: replies, photo rows and IME animation can resize the list in this frame.
                withFrameNanos { }
                if (follow.following && !follow.dragging && !list.isScrollInProgress && list.layoutInfo.totalItemsCount > 0) {
                    // User input may cancel this scroll; keep the observer alive for later replies.
                    launch { list.scrollToItem(list.layoutInfo.totalItemsCount - 1) }.join()
                    previous = viewport()
                }
            }
        }
    }
    return follow
}

@Composable
internal fun ChatLatestButton(follow: ChatAutoFollow, list: LazyListState, care: Boolean, tag: String,
    modifier: Modifier = Modifier) {
    if (!follow.following && list.canScrollForward) {
        TextButton(follow::resume, modifier.heightIn(min = 48.dp).clip(CircleShape).background(C.Surface)
            .border(1.dp, C.Line, CircleShape).testTag("$tag.latest")) {
            Text("回到最新 ↓", style = T.body(if (care) 20 else 14), color = C.AccentDeep)
        }
    }
}
