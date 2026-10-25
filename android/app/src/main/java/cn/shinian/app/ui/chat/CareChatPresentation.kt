package cn.shinian.app.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import cn.shinian.app.data.*
import cn.shinian.app.ui.browse.*
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.care.CareTypography as T
import cn.shinian.app.ui.theme.ShinianImmersiveWindow
import cn.shinian.app.ui.theme.shinianContentInsets
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.math.abs
import kotlin.math.sin

@Composable
internal fun CarePersonLine(person: Person, text: String = "故事") {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically) {
        LocalPortrait(person.id, person, size = 38.dp, care = true)
        Text(buildAnnotatedString {
            append("正在记录 ")
            withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(person.relationship.ifBlank { person.name } + if (person.relationship.isNotBlank()) " · ${person.name}" else "") }
            append(" 的$text")
        },
            style = T.body(18), color = CareColors.SecondaryInk)
    }
}

/** Explicit voice start/stop, editable transcript and a separate manual send, matching iOS. */
@Composable
internal fun CareNarrationComposer(value: String, onValue: (String) -> Unit, enabled: Boolean, sendEnabled: Boolean,
    retrying: Boolean, dictation: MandarinDictation, onMic: () -> Unit, onSend: () -> Unit,
    tag: String, hasPhotos: Boolean = false, pendingText: String? = null, photoContent: (@Composable () -> Unit)? = null) {
    var writing by rememberSaveable(tag) { mutableStateOf(false) }
    var startedAt by remember { mutableLongStateOf(android.os.SystemClock.elapsedRealtime()) }
    val requester = remember { FocusRequester() }
    val focus = LocalFocusManager.current
    LaunchedEffect(writing) { if (writing && !retrying && !dictation.busy) requester.requestFocus() }
    LaunchedEffect(dictation.phase) { if (dictation.phase == MandarinDictation.Phase.Recording) startedAt = android.os.SystemClock.elapsedRealtime() }
    BoxWithConstraints(Modifier.fillMaxWidth().testTag("$tag.composer")) {
        val bounded = constraints.hasBoundedHeight
        val availableHeight = maxHeight
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            if (dictation.busy) {
                CareTranscriptCard(radius = 24, gap = 8, live = true) {
                    Text("正在变成文字…", style = T.body(18, true), color = CareColors.Accent)
                    Text(value.ifBlank { "您说的话，会慢慢出现在这里。" }, style = T.body(22, lineSpacing = 6f), color = CareColors.Ink, maxLines = 4)
                }
                if (dictation.phase == MandarinDictation.Phase.Recording) CareRecordingIndicator(startedAt)
                CareMicButton(dictation.phase, enabled || dictation.busy, Modifier.testTag("$tag.dictation")) { focus.clearFocus(); onMic() }
                Text(when (dictation.phase) { MandarinDictation.Phase.Preparing -> "正在准备…"; MandarinDictation.Phase.Finishing -> "正在把话变成文字…"; else -> "说完了，再按一下" }, style = T.body(24, true), color = CareColors.Ink, textAlign = TextAlign.Center)
                if (dictation.phase == MandarinDictation.Phase.Recording) CareVoiceWave()
            } else if (value.isNotBlank() || writing || retrying || hasPhotos) {
                // Measure the fixed actions first. Only the transcript gives up space when the
                // keyboard or a shorter viewport reduces the dock's available height.
                CareTranscriptCard(radius = 26, gap = 10,
                    modifier = (if (bounded) Modifier.weight(1f, fill = false) else Modifier).testTag("$tag.transcript"),
                    maxHeight = availableHeight, scrollable = bounded) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                        Text(if (retrying) "这段话等着重新发送" else "您的讲述", style = T.body(18, true), color = CareColors.Accent, modifier = Modifier.weight(1f))
                        if (!retrying) CarePill("改文字", compact = true, icon = "edit", enabled = enabled) { writing = true; requester.requestFocus() }
                    }
                    if (retrying) SelectionContainer { Text(pendingText?.takeIf { it.isNotEmpty() } ?: value, style = T.body(22, lineSpacing = 6f), color = CareColors.Ink) }
                    else BasicTextField(value, onValue, Modifier.fillMaxWidth().focusRequester(requester)
                        .testTag("$tag.input").semantics { contentDescription = "讲述文字" }, enabled = enabled,
                        textStyle = T.body(22, lineSpacing = 6f).copy(color = CareColors.Ink), cursorBrush = SolidColor(CareColors.Accent), minLines = 2, maxLines = 5,
                        decorationBox = { inner -> Box { if (value.isEmpty()) Text("在这里写下您的回忆", style = T.body(22), color = CareColors.SecondaryInk.copy(alpha = .5f)); inner() } })
                    photoContent?.invoke()
                }
                CareButton(if (retrying) "重试这段讲述" else "发送这段话", icon = if (retrying) "refresh" else "up",
                    enabled = sendEnabled, modifier = Modifier.testTag("$tag.send")) { focus.clearFocus(); onSend(); writing = false }
                if (retrying) Text("文字已锁定，重试成功前不能说下一段。", Modifier.fillMaxWidth(), style = T.body(18), color = CareColors.SecondaryInk)
                else Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    CareButton("再说一段", icon = "mic", secondary = true, enabled = enabled, fontSize = 21,
                        modifier = Modifier.weight(1f).testTag("$tag.dictation")) { focus.clearFocus(); onMic() }
                    CareButton("清空重说", icon = "refresh", secondary = true, enabled = enabled, fontSize = 21,
                        modifier = Modifier.weight(1f).testTag("$tag.input.clear")) { onValue(""); writing = false; focus.clearFocus() }
                }
            } else {
                Column(Modifier.padding(vertical = 4.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    CareMicButton(MandarinDictation.Phase.Idle, enabled, Modifier.testTag("$tag.dictation")) { focus.clearFocus(); onMic() }
                    Text("按一下，开始说", style = T.body(26, true), color = CareColors.Ink)
                    Text("说完再按一下，会变成文字", style = T.body(18), color = CareColors.SecondaryInk, textAlign = TextAlign.Center)
                }
                CareButton("我想打字", icon = "keyboard", secondary = true, enabled = enabled,
                    modifier = Modifier.testTag("$tag.input.keyboard")) { writing = true }
            }
        }
    }
}

@Composable
private fun CareMicButton(phase: MandarinDictation.Phase, enabled: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val recording = phase == MandarinDictation.Phase.Recording || phase == MandarinDictation.Phase.Finishing
    val context = LocalContext.current
    val reduceMotion = remember { android.provider.Settings.Global.getFloat(context.contentResolver, android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    var pulse by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(phase, reduceMotion) {
        pulse = 0f
        if (phase == MandarinDictation.Phase.Recording && !reduceMotion) while (isActive) {
            pulse = ((sin(android.os.SystemClock.elapsedRealtime() / 1000.0 * 4) + 1) / 2).toFloat()
            delay(50)
        }
    }
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val radius = with(LocalDensity.current) { 132.dp.toPx() }
    Box(modifier.size(174.dp).alpha((if (phase == MandarinDictation.Phase.Preparing || !enabled) .7f else 1f) * if (pressed) .76f else 1f)
        .clickable(interactionSource = source, indication = null, enabled = enabled && phase != MandarinDictation.Phase.Finishing, role = Role.Button, onClick = onClick)
        .semantics { contentDescription = when (phase) { MandarinDictation.Phase.Recording -> "停止录音"; MandarinDictation.Phase.Preparing -> "取消准备"; MandarinDictation.Phase.Finishing -> "正在转成文字"; else -> "开始语音输入" } }, contentAlignment = Alignment.Center) {
        Box(Modifier.size((158 + pulse * 8).dp).background(CareColors.Soft.copy(alpha = .6f), CircleShape))
        Box(Modifier.size(146.dp).background(CareColors.Soft, CircleShape))
        Box(Modifier.size(132.dp).background(Brush.radialGradient(listOf(Color(0xFFD98159), CareColors.Accent), center = Offset.Zero, radius = radius), CircleShape), contentAlignment = Alignment.Center) {
            if (phase == MandarinDictation.Phase.Preparing) CircularProgressIndicator(Modifier.size(36.dp), color = Color.White)
            else if (recording) Box(Modifier.size(36.dp).background(Color.White, RoundedCornerShape(9.dp)))
            else CareSymbol("mic", 48.dp, tint = Color.White)
        }
    }
}

@Composable
private fun CareTranscriptCard(radius: Int, gap: Int, live: Boolean = false, modifier: Modifier = Modifier,
    maxHeight: Dp = Dp.Infinity, scrollable: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(radius.dp)
    val scroll = rememberScrollState()
    Column(modifier.fillMaxWidth().heightIn(max = maxHeight).background(CareColors.Surface, shape)
        .border(if (live) 2.dp else 1.dp, if (live) CareColors.Soft else CareColors.Border.copy(alpha = .7f), shape)
        .clip(shape).then(if (scrollable) Modifier.verticalScroll(scroll) else Modifier).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(gap.dp), content = content)
}

@Composable
private fun CareRecordingIndicator(startedAt: Long) {
    var seconds by remember(startedAt) { mutableLongStateOf(0) }
    LaunchedEffect(startedAt) { while (isActive) { seconds = ((android.os.SystemClock.elapsedRealtime() - startedAt) / 1000).coerceAtLeast(0); delay(1000) } }
    Row(Modifier.background(CareColors.RecordSoft, CircleShape).padding(horizontal = 14.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(CareColors.RecordDot, CircleShape))
        Text("正在听您说 · ${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}", style = T.body(18, true), color = CareColors.RecordInk)
    }
}

@Composable
private fun CareVoiceWave() {
    val context = LocalContext.current
    val reduceMotion = remember { android.provider.Settings.Global.getFloat(context.contentResolver, android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    var phase by remember { mutableDoubleStateOf(0.0) }
    LaunchedEffect(reduceMotion) { if (!reduceMotion) while (isActive) { phase = android.os.SystemClock.elapsedRealtime() / 1000.0 * 5; delay(80) } }
    Row(Modifier.height(30.dp).clearAndSetSemantics {}, horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
        repeat(19) { index -> Box(Modifier.width(4.dp).height((7 + abs(sin(if (reduceMotion) index.toDouble() else phase + index * 1.7)) * 22).dp)
            .background(CareColors.AccentTop.copy(alpha = .75f), CircleShape)) }
    }
}

@Composable
internal fun CareStoryChatScreen(model: ChatController, dictation: MandarinDictation, readingPhotos: Boolean,
    continuing: Boolean, onContinue: () -> Unit, onMic: () -> Unit, onPhoto: () -> Unit, onHistory: () -> Unit,
    onManagePhotos: () -> Unit, onGenerate: () -> Unit, onBack: () -> Unit) {
    val compact = dictation.busy || model.input.isNotEmpty() || model.photos.isNotEmpty() || model.pending != null
    val generation = model.mayGenerate && !dictation.busy && !readingPhotos && !continuing
    val canPickPhotos = !model.busy && !readingPhotos && model.pending == null && !dictation.busy && model.photos.size < 9
    val guided = model.snapshot?.information.objectAt("guided_interview")
    val modules = mapOf("childhood" to ("成长的地方" to "home"), "growth" to ("读书或学艺" to "book"),
        "work" to ("工作与生活" to "briefcase"), "family" to ("重要家人" to "users"),
        "later_life" to ("如今的生活" to "cup"), "reflection" to ("人生回望" to "sun"))
    Box(Modifier.fillMaxSize()) {
        CarePage {
            CareToolbar("慢慢讲述", onBack, backTitle = "暂停", step = "3 / 3", enabled = !model.busy && !readingPhotos, backTag = "chat.back")
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(top = 8.dp, bottom = 20.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (guided.flag("module_selected")) {
                    val module = modules[guided.text("module")] ?: ("慢慢讲述" to "chat")
                    Row(Modifier.background(CareColors.Faint, CircleShape).padding(horizontal = 14.dp, vertical = 9.dp),
                        horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
                        CareSymbol(module.second, 18.dp, tint = CareColors.Accent)
                        Text(module.first, style = T.body(18, true), color = CareColors.Accent)
                    }
                }
                CarePersonLine(model.person)
                model.messages.lastOrNull { it.role != "user" }?.let { CareQuestionCard(it.content, Modifier.testTag("care.chat.question"), compact = compact) }
                if (generation) {
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        CarePill("前面聊过的", icon = "chat", modifier = Modifier.testTag("care.chat.history"), onClick = onHistory)
                    }
                    Row(Modifier.fillMaxWidth().background(CareColors.SageSoft, RoundedCornerShape(22.dp)).padding(16.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                        CareSymbol("eye", 19.dp, tint = CareColors.SageInk)
                        Text("先看草稿，您点“保存”才会存进回忆。", style = T.body(19), color = CareColors.SageInk)
                    }
                } else if (!compact) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    CarePill("前面聊过的", icon = "chat", enabled = !model.busy, modifier = Modifier.testTag("care.chat.history"), onClick = onHistory)
                    CarePill("加照片", icon = "image", enabled = canPickPhotos, modifier = Modifier.testTag("chat.addPhotos"), onClick = onPhoto)
                }
                model.error?.let { CareError(it, if (model.pending == null) ({ model.retryOpen() }) else null) }
                model.storageError?.let { CareError(it, model::retryStorage) }
            }
            CareDock {
                if (generation) {
                    CareButton("整理这段回忆", icon = "book", enabled = !model.busy, modifier = Modifier.testTag("chat.generate"), onClick = onGenerate)
                    CareButton("我还想补充", icon = "mic", secondary = true, onClick = onContinue)
                } else if (!model.completed) CareNarrationComposer(model.input, model::updateInput,
                    enabled = !model.busy && !readingPhotos && model.pending == null,
                    sendEnabled = !model.busy && !readingPhotos && !dictation.busy && (model.pending != null || model.input.isNotBlank() || model.photos.isNotEmpty()),
                    retrying = model.pending != null, dictation = dictation, onMic = onMic,
                    onSend = { dictation.cancel(); model.send() }, tag = "chat", pendingText = model.pending?.text, hasPhotos = model.photos.isNotEmpty(),
                    photoContent = {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 3.dp),
                                horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                model.photos.forEachIndexed { index, photo ->
                                    LocalChatPhoto(photo.data, Modifier.size(76.dp).clip(RoundedCornerShape(16.dp))
                                        .clickable(role = Role.Button, onClick = onManagePhotos), label = "管理已选照片 ${index + 1}")
                                }
                                if (model.pending == null) CarePill("加照片", icon = "image", enabled = canPickPhotos, onClick = onPhoto)
                            }
                            if (model.photos.isNotEmpty()) CarePill("管理已选照片（${model.photos.size}/9）", icon = "image", compact = true,
                                modifier = Modifier.testTag("chat.managePhotos"), onClick = onManagePhotos)
                        }
                    })
                else CareButton("再讲一段", icon = "mic", enabled = !model.busy, onClick = model::continueStory)
            }
        }
        if (model.busy || readingPhotos) CareBusyOverlay(if (readingPhotos) "正在读取照片…" else model.progress.ifBlank { "正在倾听与整理…" })
    }
}

private data class CareHistoryEntry(val question: String, val answer: String? = null, val photos: List<Media> = emptyList())

@Composable
internal fun CareHistoryDialog(messages: List<ChatMessage>, repository: BackendRepository, onPhoto: (Media) -> Unit, onClose: () -> Unit, person: Person? = null) {
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        ShinianImmersiveWindow()
        CareBackdrop(Modifier.fillMaxSize(), force = true) {
            Box(Modifier.fillMaxSize().shinianContentInsets()) { CareHistoryPage(messages, repository, onPhoto, onClose, person) }
        }
    }
}

@Composable
internal fun CareHistoryPage(messages: List<ChatMessage>, repository: BackendRepository, onPhoto: (Media) -> Unit, onClose: () -> Unit, person: Person? = null) {
    val entries = remember(messages) {
        buildList<CareHistoryEntry> {
            for (message in messages) {
                if (message.role != "user") add(CareHistoryEntry(message.content))
                else if (lastOrNull()?.answer == null && isNotEmpty()) {
                    this[lastIndex] = last().copy(answer = message.content, photos = message.attachments)
                } else add(CareHistoryEntry("补充讲述", message.content, message.attachments))
            }
        }
    }
    var index by rememberSaveable { mutableIntStateOf(0) }
    val page = index.coerceIn(0, entries.lastIndex.coerceAtLeast(0))
    val historyScroll = rememberScrollState()
    LaunchedEffect(page) { historyScroll.scrollTo(0) }
    CarePage {
        CareToolbar("刚才聊过的", onClose, step = if (entries.isEmpty()) "0 条" else "${page + 1} / ${entries.size}", backTag = "care.back")
        if (entries.isNotEmpty()) CareProgressBar(page + 1, entries.size, Modifier.padding(horizontal = 20.dp).padding(bottom = 12.dp))
        Column(Modifier.weight(1f).verticalScroll(historyScroll).padding(20.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
            entries.getOrNull(page)?.let { entry ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                    CareIconTile("spark", size = 44.dp)
                    CareCard(Modifier.weight(1f), radius = 24.dp, spacing = 12.dp) {
                        Text("回忆助手问", style = T.body(18, true), color = CareColors.Accent)
                        Text(entry.question, style = T.body(23, true), color = CareColors.Ink, modifier = Modifier.testTag("care.history.question"))
                    }
                }
                Row(Modifier.padding(start = 28.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                    CareCard(Modifier.weight(1f), fill = CareColors.Soft, radius = 24.dp, spacing = 12.dp) {
                        Text("您的回答", style = T.body(18, true), color = CareColors.Accent)
                        SelectionContainer { Text(entry.answer ?: "这一个问题还没有回答。", style = T.body(22, lineSpacing = 7f), color = CareColors.Ink) }
                        entry.photos.forEach { photo -> RemoteChatPhoto(photo, repository, Modifier.fillMaxWidth().heightIn(min = 160.dp).clip(RoundedCornerShape(18.dp)), fit = true, onOpen = { onPhoto(photo) }) }
                    }
                    if (person != null) LocalPortrait(person.id, person, size = 44.dp, care = true)
                    else CareIconTile("person", CareTone.Sage, 44.dp)
                }
            } ?: Text("还没有开始讲述。", style = T.body(22), color = CareColors.SecondaryInk)
        }
        CareDock {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CareButton("上一条", icon = "back", secondary = true, enabled = page > 0, fontSize = 21,
                    modifier = Modifier.weight(1f).testTag("care.history.previous")) { index = page - 1 }
                CareButton(if (page == entries.lastIndex) "返回核对" else "下一条", icon = "chev", enabled = entries.isNotEmpty(), fontSize = 21,
                    modifier = Modifier.weight(1f).testTag("care.history.next")) { if (page == entries.lastIndex) onClose() else index = page + 1 }
            }
        }
    }
}

@Composable
internal fun CareSavedResult(memory: Memory, person: Person, busy: Boolean, onRead: () -> Unit, onContinue: () -> Unit, onHome: () -> Unit,
    memoryCount: Int? = null) {
    CarePage {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp).testTag("care.saved.scroll"),
            verticalArrangement = Arrangement.spacedBy(22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.padding(top = 24.dp).size(116.dp).background(CareColors.SageSoft, CircleShape), contentAlignment = Alignment.Center) {
                Box(Modifier.size(80.dp).background(CareColors.Sage, CircleShape), contentAlignment = Alignment.Center) {
                    CareSymbol("check", 42.dp, tint = Color.White)
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("这段回忆，保存好了", style = T.body(30, true), color = CareColors.Ink, textAlign = TextAlign.Center)
                Text("以后在「回忆」里，随时可以找到。", style = T.body(19), color = CareColors.SecondaryInk, textAlign = TextAlign.Center)
            }
            CareCard(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onRead), padding = 14.dp) {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    memory.media.firstOrNull()?.let { MemoryPhoto(it, Modifier.size(92.dp), radius = 18.dp) }
                        ?: CareIconTile("book", CareTone.Butter, 92.dp)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(listOf(person.relationship.ifBlank { person.name }, memory.dateLabel).filter { it.isNotBlank() }.joinToString(" · "), style = T.body(18), color = CareColors.SecondaryInk)
                        Text(memory.title, style = T.story(24), color = CareColors.Ink, modifier = Modifier.testTag("care.saved.title"))
                    }
                }
            }
            if (memoryCount != null) Row(Modifier.background(CareColors.SageSoft, RoundedCornerShape(22.dp)).padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                CareSymbol("book", 19.dp, tint = CareColors.SageInk)
                Text("${person.relationship.ifBlank { person.name }}的回忆，现在有 $memoryCount 段了", style = T.body(19, true), color = CareColors.SageInk)
            }
        }
        CareDock {
            CareButton("打开看看", icon = "book", modifier = Modifier.testTag("care.saved.read"), onClick = onRead)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CareButton("再讲一段", secondary = true, icon = "mic", fontSize = 21, enabled = !busy, modifier = Modifier.weight(1f).testTag("care.saved.continue"), onClick = onContinue)
                CareButton("回到首页", secondary = true, icon = "home", fontSize = 21, modifier = Modifier.weight(1f).testTag("care.saved.home"), onClick = onHome)
            }
        }
    }
}
