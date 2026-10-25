package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.displayCutout
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.ChatMessage
import cn.shinian.app.data.Media
import cn.shinian.app.ui.theme.shinianContentInsets
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.theme.JournalColors as C
import cn.shinian.app.ui.theme.JournalTypography as T
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withContext

@Composable
internal fun ChatPage(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().background(C.Paper).navigationBarsPadding().imePadding(), content = content)
}

@Composable
internal fun ChatHeader(title: String, subtitle: String? = null, care: Boolean = false, onBack: () -> Unit,
    enabled: Boolean = true, backLabel: String = "暂停并返回", trailing: @Composable RowScope.() -> Unit = {}) {
    if (care) { CareToolbar(title, onBack, backTitle = if (backLabel == "暂停并返回") "暂停" else "返回", step = subtitle?.takeIf { "/" in it }, enabled = enabled, backTag = "chat.back"); return }
    Row(Modifier.fillMaxWidth().heightIn(min = if (care) 68.dp else 58.dp).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack, enabled = enabled, modifier = Modifier.testTag("chat.back").semantics { contentDescription = backLabel }) {
            JournalGlyph("back", tint = C.Ink)
        }
        Column(Modifier.weight(1f).padding(horizontal = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(title, style = if (care) T.body(24, true) else T.body(16, true), color = C.Ink,
                textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
            subtitle?.let { Text(it, style = T.body(if (care) 18 else 12), color = C.SecondaryInk, textAlign = TextAlign.Center) }
        }
        Row(Modifier.heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically, content = trailing)
    }
    HorizontalDivider(color = C.Line)
}

@Composable
internal fun ChatButton(title: String, enabled: Boolean = true, busy: Boolean = false, secondary: Boolean = false,
    care: Boolean = false, modifier: Modifier = Modifier, onClick: () -> Unit) {
    if (care) { CareButton(title, modifier, secondary = secondary, enabled = enabled, loading = busy, onClick = onClick); return }
    val content: @Composable RowScope.() -> Unit = {
        if (busy) CircularProgressIndicator(Modifier.size(20.dp).padding(end = 4.dp), color = if (secondary) C.AccentDeep else Color.White, strokeWidth = 2.dp)
        Text(title, style = T.body(if (care) 22 else 17, true), textAlign = TextAlign.Center)
    }
    if (secondary) OutlinedButton(onClick, enabled = enabled && !busy,
        modifier = modifier.fillMaxWidth().heightIn(min = if (care) 64.dp else 56.dp), shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = C.AccentDeep), content = content)
    else Button(onClick, enabled = enabled && !busy,
        modifier = modifier.fillMaxWidth().heightIn(min = if (care) 64.dp else 56.dp), shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(containerColor = C.AccentDeep, contentColor = Color.White), content = content)
}

@Composable
internal fun ChatError(message: String, title: String = "重试", care: Boolean = false, enabled: Boolean = true, onRetry: () -> Unit) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.RoseSoft).padding(14.dp)) {
        Text(message, color = C.Danger, style = T.body(if (care) 20 else 14))
        TextButton(onRetry, enabled = enabled, modifier = Modifier.heightIn(min = 48.dp)) { Text(title, style = T.body(if (care) 20 else 15, true)) }
    }
}

/** Small repo-native stroke icons keep the same quiet visual vocabulary without font glyph icons. */
@Composable
internal fun JournalGlyph(name: String, modifier: Modifier = Modifier, size: Dp = 23.dp, tint: Color = C.SecondaryInk) {
    Canvas(modifier.size(size)) {
        val unit = this.size.minDimension / 24f
        fun line(x: Float, y: Float, x2: Float, y2: Float) = drawLine(tint, Offset(x * unit, y * unit), Offset(x2 * unit, y2 * unit), 1.65f * unit, StrokeCap.Round)
        fun path(vararg points: Pair<Float, Float>) {
            val path = Path()
            points.forEachIndexed { i, pair -> if (i == 0) path.moveTo(pair.first * unit, pair.second * unit) else path.lineTo(pair.first * unit, pair.second * unit) }
            drawPath(path, tint, style = Stroke(1.65f * unit, cap = StrokeCap.Round))
        }
        when (name) {
            "back" -> { path(14f to 5f, 7f to 12f, 14f to 19f) }
            "up" -> { line(12f, 19f, 12f, 5f); path(6f to 11f, 12f to 5f, 18f to 11f) }
            "close" -> { line(6f, 6f, 18f, 18f); line(6f, 18f, 18f, 6f) }
            "check" -> path(5f to 12f, 10f to 17f, 20f to 6f)
            "mic" -> {
                drawRoundRect(tint, Offset(9f * unit, 3f * unit), androidx.compose.ui.geometry.Size(6f * unit, 11f * unit), androidx.compose.ui.geometry.CornerRadius(3f * unit), style = Stroke(1.65f * unit))
                path(6f to 10f, 6f to 14f, 9f to 17f, 15f to 17f, 18f to 14f, 18f to 10f)
                line(12f, 17f, 12f, 21f); line(9f, 21f, 15f, 21f)
            }
            "stop" -> drawRoundRect(tint, Offset(6f * unit, 6f * unit), androidx.compose.ui.geometry.Size(12f * unit, 12f * unit), androidx.compose.ui.geometry.CornerRadius(3f * unit))
            "photo" -> {
                drawRoundRect(tint, Offset(3f * unit, 4f * unit), androidx.compose.ui.geometry.Size(18f * unit, 16f * unit), androidx.compose.ui.geometry.CornerRadius(3f * unit), style = Stroke(1.65f * unit))
                drawCircle(tint, 1.6f * unit, Offset(8f * unit, 9f * unit)); path(4f to 18f, 11f to 12f, 15f to 16f, 18f to 13f, 21f to 16f)
            }
            "book" -> { path(12f to 5f, 7f to 3f, 2f to 4f, 2f to 20f, 7f to 19f, 12f to 21f, 17f to 19f, 22f to 20f, 22f to 4f, 17f to 3f, 12f to 5f, 12f to 21f); line(5f, 8f, 9f, 9f); line(15f, 9f, 19f, 8f) }
            "history" -> { drawCircle(tint, 8f * unit, Offset(13f * unit, 12f * unit), style = Stroke(1.65f * unit)); path(13f to 7f, 13f to 12f, 17f to 14f); path(2f to 5f, 2f to 10f, 7f to 10f) }
            "retry" -> {
                drawArc(tint, -40f, 290f, false, Offset(4f * unit, 4f * unit), androidx.compose.ui.geometry.Size(16f * unit, 16f * unit), style = Stroke(1.65f * unit, cap = StrokeCap.Round))
                path(16f to 3f, 21f to 3f, 21f to 8f)
            }
            "edit" -> { path(4f to 17f, 15f to 6f, 19f to 10f, 8f to 21f, 3f to 22f, 4f to 17f); path(15f to 6f, 18f to 3f, 22f to 7f, 19f to 10f) }
            "spark" -> { path(12f to 2f, 15f to 9f, 22f to 12f, 15f to 15f, 12f to 22f, 9f to 15f, 2f to 12f, 9f to 9f, 12f to 2f) }
            "heart" -> { val p = Path().apply { moveTo(12f * unit, 21f * unit); cubicTo(-6f * unit, 10f * unit, 4f * unit, -3f * unit, 12f * unit, 6f * unit); cubicTo(20f * unit, -3f * unit, 30f * unit, 10f * unit, 12f * unit, 21f * unit) }; drawPath(p, tint, style = Stroke(1.65f * unit)) }
            else -> { drawCircle(tint, 8f * unit, center, style = Stroke(1.65f * unit)); line(12f, 7f, 12f, 13f); drawCircle(tint, unit, Offset(12f * unit, 17f * unit)) }
        }
    }
}

private fun displayBitmap(data: ByteArray, maxPixelSize: Int): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / sample > maxPixelSize.coerceAtLeast(1)) sample *= 2
    return BitmapFactory.decodeByteArray(data, 0, data.size, BitmapFactory.Options().apply { inSampleSize = sample })
}

@Composable
internal fun RemoteChatPhoto(
    media: Media, repository: BackendRepository, modifier: Modifier = Modifier, fit: Boolean = false,
    thumbnailMaxPixelSize: Int = 400, label: String = "讲述照片", onOpen: (() -> Unit)? = null,
) {
    val scope = repository.session.scopeKey
    val pixels = if (fit) 2048 else thumbnailMaxPixelSize
    var retry by remember(scope, media.id) { mutableIntStateOf(0) }
    var failure by remember(scope, media.id, retry, pixels) { mutableStateOf<String?>(null) }
    val bitmap by produceState<Bitmap?>(null, scope, media.id, retry, pixels) {
        value = null
        failure = null
        try {
            value = withContext(Dispatchers.IO) { displayBitmap(repository.loadMedia(media), pixels) }
                ?: throw IllegalStateException("照片无法读取，请重新加载。")
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) { failure = error.message ?: "照片暂时无法读取，请重试。" }
    }
    val action: (() -> Unit)? = if (failure != null) ({ retry++ }) else if (bitmap != null) onOpen else null
    Box(modifier.clip(RoundedCornerShape(14.dp)).background(C.Surface)
        .then(if (action != null) Modifier.clickable(role = Role.Button, onClick = action) else Modifier)
        .testTag("chat.photo.${media.id}").semantics {
            contentDescription = if (failure != null) "重新加载$label" else label
            stateDescription = if (failure != null) "照片加载失败" else if (bitmap == null) "照片加载中" else "照片已加载"
        }, contentAlignment = Alignment.Center) {
        bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = if (fit) ContentScale.Fit else ContentScale.Crop) }
            ?: if (failure != null) {
                // The fixed photo cell remains stable; accessibility text can scroll at large font sizes.
                BoxWithConstraints(Modifier.fillMaxSize()) {
                    val minimumHeight = maxHeight
                    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).heightIn(min = minimumHeight).padding(8.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterVertically)) {
                        JournalGlyph("retry", size = 22.dp)
                        Text(if (fit) failure!! else "加载失败", style = T.body(12), color = C.SecondaryInk, textAlign = TextAlign.Center)
                        if (fit) Text("轻点重新加载", style = T.body(13), color = C.SecondaryInk, textAlign = TextAlign.Center)
                    }
                }
            } else CircularProgressIndicator(Modifier.size(22.dp).testTag("chat.photo.loading.${media.id}"), color = C.AccentDeep, strokeWidth = 2.dp)
    }
}

@Composable
internal fun LocalChatPhoto(
    data: ByteArray, modifier: Modifier = Modifier, label: String = "已选讲述照片", fit: Boolean = false,
    thumbnailMaxPixelSize: Int = 256,
) {
    val bitmap by produceState<Bitmap?>(null, data, fit, thumbnailMaxPixelSize) {
        value = null
        try { value = withContext(Dispatchers.IO) { displayBitmap(data, if (fit) 2048 else thumbnailMaxPixelSize) } }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { value = null }
    }
    Box(modifier.background(C.Soft).semantics { contentDescription = label }, contentAlignment = Alignment.Center) {
        bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = if (fit) ContentScale.Fit else ContentScale.Crop) }
            ?: JournalGlyph("photo", tint = C.Muted)
    }
}

/** Cells are measured from the message width, never from the image pixels or the last row's count. */
@Composable
private fun MessagePhotoGrid(count: Int, messageId: String, cell: @Composable (Int, Modifier) -> Unit) {
    val columns = minOf(3, count)
    val aspect = when (count) { 1 -> 4f / 3f; 2 -> 129f / 96f; else -> 1f }
    Column(Modifier.fillMaxWidth().testTag("chat.message.photos.$messageId"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (start in 0 until count step columns) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                repeat(columns) { column ->
                    val index = start + column
                    val modifier = Modifier.weight(1f).aspectRatio(aspect).clip(RoundedCornerShape(14.dp))
                    if (index < count) cell(index, modifier) else Spacer(modifier)
                }
            }
        }
    }
}

@Composable
internal fun ChatMessageView(message: ChatMessage, repository: BackendRepository, care: Boolean = false,
    localPhotos: List<SelectedPhoto> = emptyList(), onPhoto: (Media) -> Unit = {}) {
    if (message.role == "user") {
        val pending = localPhotos.take(9)
        val attachments = message.attachments.take(9)
        Box(Modifier.fillMaxWidth().padding(start = 60.dp), contentAlignment = Alignment.TopEnd) {
            Column(Modifier.widthIn(max = 264.dp), horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (pending.isNotEmpty()) MessagePhotoGrid(pending.size, message.id) { index, modifier ->
                    val photo = pending[index]
                    LocalChatPhoto(photo.data, modifier.testTag("chat.pendingPhoto.${photo.id}"),
                        label = "待发送照片 ${index + 1}，共 ${pending.size} 张", thumbnailMaxPixelSize = if (pending.size < 3) 1024 else 400)
                } else if (attachments.isNotEmpty()) MessagePhotoGrid(attachments.size, message.id) { index, modifier ->
                    val media = attachments[index]
                    RemoteChatPhoto(media, repository, modifier, thumbnailMaxPixelSize = if (attachments.size < 3) 1024 else 400,
                        label = "讲述照片 ${index + 1}，共 ${attachments.size} 张", onOpen = { onPhoto(media) })
                }
                if (message.content.isNotBlank()) {
                    val bubble = RoundedCornerShape(topStart = 20.dp, topEnd = 4.dp, bottomEnd = 20.dp, bottomStart = 20.dp)
                    Box(Modifier.clip(bubble).background(C.Soft).testTag("chat.message.text.${message.id}").padding(horizontal = 14.dp, vertical = 12.dp)) {
                        Text(message.content, style = T.body(if (care) 22 else 14).copy(fontSize = if (care) 22.sp else 14.5.sp),
                            color = Color(0xFF6E3D25), lineHeight = if (care) 34.sp else 23.sp, modifier = Modifier.testTag("chat.message.${message.id}"))
                    }
                }
            }
        }
        return
    }
    Column(Modifier.fillMaxWidth().padding(end = 8.dp), horizontalAlignment = Alignment.Start) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            JournalGlyph("spark", size = 14.dp)
            Text("AI 回忆助手", style = T.body(if (care) 18 else 12), color = C.SecondaryInk)
        }
        Column(Modifier.padding(top = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (message.content.isNotBlank()) Text(message.content, style = if (care) T.body(22) else T.story(16), color = C.StoryInk,
                lineHeight = if (care) 34.sp else 26.sp, modifier = Modifier.testTag("chat.message.${message.id}"))
            if (message.attachments.isNotEmpty()) MessagePhotoGrid(message.attachments.size, message.id) { index, modifier ->
                val media = message.attachments[index]
                RemoteChatPhoto(media, repository, modifier, onOpen = { onPhoto(media) })
            }
        }
    }
}

@Composable
internal fun ChatFullDialog(title: String, onClose: () -> Unit, care: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        cn.shinian.app.ui.theme.ShinianImmersiveWindow()
        Surface(Modifier.fillMaxSize(), color = C.Paper) {
            Column(Modifier.fillMaxSize().shinianContentInsets().systemBarsPadding().imePadding()) {
                ChatHeader(title, care = care, onBack = onClose, backLabel = if (care) "返回" else "暂停并返回")
                content()
            }
        }
    }
}

@Composable
internal fun ChatHistoryDialog(messages: List<ChatMessage>, repository: BackendRepository, care: Boolean,
    onPhoto: (Media) -> Unit = {}, person: cn.shinian.app.data.Person? = null, onClose: () -> Unit) {
    if (care) { CareHistoryDialog(messages, repository, onPhoto, onClose, person = person); return }
    ChatFullDialog("前面聊过的", onClose) {
        LazyColumn(Modifier.weight(1f).padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            if (messages.isEmpty()) item { Text("还没有聊过的内容。", Modifier.padding(vertical = 24.dp), style = T.body(if (care) 22 else 16), color = C.SecondaryInk) }
            items(messages, key = { it.id }) { ChatMessageView(it, repository, care, onPhoto = onPhoto) }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}
