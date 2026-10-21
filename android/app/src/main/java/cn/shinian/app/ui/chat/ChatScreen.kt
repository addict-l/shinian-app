package cn.shinian.app.ui.chat

import android.Manifest
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.ChatMessage
import cn.shinian.app.data.Media
import cn.shinian.app.data.Person
import cn.shinian.app.media.preparePhoto
import cn.shinian.app.ui.media.rememberPhotoPicker
import cn.shinian.app.ui.theme.JournalColors as C
import cn.shinian.app.ui.theme.JournalTypography as T
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException

@Composable
fun ChatScreen(person: Person, repository: BackendRepository, care: Boolean, onBack: () -> Unit, onSaved: () -> Unit,
    onHome: () -> Unit = {}) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val focus = LocalFocusManager.current
    val scope = rememberCoroutineScope()
    val factory = remember(repository, person.id) {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <V : ViewModel> create(modelClass: Class<V>): V = ChatController(context.applicationContext, person, repository) as V
        }
    }
    val model: ChatController = viewModel(key = "chat-${repository.session.scopeKey}-${repository.session.token.hashCode()}-${person.id}", factory = factory)
    val dictation = remember(model) { MandarinDictation(context.applicationContext) { value ->
        if (model.needsLife || model.showLife) model.updateLifeInput(value) else model.updateInput(value)
    } }
    var history by remember { mutableStateOf<List<ChatMessage>?>(null) }
    var photoPreview by remember { mutableStateOf<Media?>(null) }
    var readingPhotos by remember { mutableStateOf(false) }
    var mediaError by remember { mutableStateOf<String?>(null) }
    var careContinuing by rememberSaveable(person.id) { mutableStateOf(false) }
    var managePhotos by rememberSaveable { mutableStateOf(false) }
    var readingSaved by rememberSaveable { mutableStateOf(false) }
    val careGenerationReady = model.mayGenerate && !dictation.busy && !readingPhotos
    val openedAt = remember(person.id) { SimpleDateFormat("M月d日 HH:mm", Locale.CHINA).format(Date()) }

    DisposableEffect(lifecycle, dictation, model) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { dictation.cancel(); model.pause() }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); dictation.cancel(); model.pause() }
    }
    LaunchedEffect(model) { model.enter() }
    LaunchedEffect(model.cacheInvalidated, model.busy) {
        if (model.cacheInvalidated && !model.busy) model.enter()
    }
    LaunchedEffect(model.messages.lastOrNull()?.id) { careContinuing = false }
    val microphone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (allowed) dictation.start(if (model.needsLife || model.showLife) model.lifeInput else model.input)
        else dictation.error = "请在系统设置中允许麦克风，或使用键盘输入。已有文字会保留。"
    }
    fun mic() {
        focus.clearFocus()
        when (dictation.phase) {
            MandarinDictation.Phase.Recording -> dictation.stop()
            MandarinDictation.Phase.Preparing -> dictation.cancel()
            MandarinDictation.Phase.Finishing -> Unit
            MandarinDictation.Phase.Idle -> {
                if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
                    dictation.start(if (model.needsLife || model.showLife) model.lifeInput else model.input)
                else microphone.launch(Manifest.permission.RECORD_AUDIO)
            }
        }
    }
    fun readPhotos(uris: List<Uri>) {
        if (uris.isEmpty()) return
        if (uris.size + model.photos.size > 9) { mediaError = "每条消息最多 9 张照片，请重新选择。"; return }
        readingPhotos = true
        scope.launch {
            try {
                val prepared = mutableListOf<ByteArray>()
                for (uri in uris) {
                    try { prepared += preparePhoto(context, uri) }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (failure: Exception) { mediaError = failure.message ?: "照片读取失败，请重新选择。" }
                }
                model.appendPhotos(prepared)
            } finally { readingPhotos = false }
        }
    }
    val launchPhotos = rememberPhotoPicker(9 - model.photos.size, ::readPhotos)
    fun pickPhoto() {
        focus.clearFocus(); dictation.cancel()
        launchPhotos()
    }
    fun leave() {
        if (model.busy) return
        dictation.cancel(); focus.clearFocus(); model.pause()
        if (model.showLife || model.needsLife) model.pauseLife { if (model.showLife) model.showLife = false else onBack() }
        else onBack()
    }
    fun generateDraft() {
        if (dictation.busy || readingPhotos) return
        focus.clearFocus()
        model.generate()
    }
    BackHandler { if (!model.busy) {
        if (care && model.savedMemory != null) { if (readingSaved) readingSaved = false else onHome() }
        else if (model.review != null) model.closeReview() else leave()
    } }

    when {
        model.savedMemory != null -> ChatPage {
            ChatHeader(if (readingSaved) "珍藏的回忆" else "回忆已珍藏", care = care,
                onBack = { if (readingSaved) readingSaved = false else onHome() },
                backLabel = if (readingSaved) "返回保存结果" else "回到首页", trailing = { Spacer(Modifier.size(48.dp)) })
            if (readingSaved) {
                LazyColumn(Modifier.weight(1f).padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    item { Text(model.savedMemory!!.title, style = if (care) T.body(28, true) else T.story(28), color = C.Ink) }
                    items(model.savedMemory!!.media, key = { it.id }) { media -> RemoteChatPhoto(media, repository, Modifier.fillMaxWidth().height(240.dp).clip(RoundedCornerShape(16.dp)), fit = true) }
                    item { Text(model.savedMemory!!.content, style = if (care) T.body(23) else T.story(17), color = C.StoryInk, lineHeight = if (care) 37.sp else 29.sp) }
                    item { ChatButton("回到首页", secondary = true, care = care, onClick = onHome) }
                }
            } else {
            BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).heightIn(min = maxHeight).padding(28.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                JournalGlyph("heart", size = 72.dp, tint = C.AccentDeep)
                Text("这段故事，已经留下了", Modifier.padding(top = 26.dp, bottom = 12.dp), style = if (care) T.body(28, true) else T.story(28), color = C.Ink, textAlign = TextAlign.Center)
                Text(model.savedMemory!!.title, style = T.body(if (care) 23 else 18), color = C.SecondaryInk, textAlign = TextAlign.Center)
                TextButton({ readingSaved = true }) { Text("读读这段回忆", style = T.body(if (care) 22 else 17)) }
                Spacer(Modifier.height(32.dp))
                ChatButton("继续记录", busy = model.busy, care = care) { readingSaved = false; model.continueStory() }
                Spacer(Modifier.height(14.dp))
                ChatButton("回到首页", secondary = true, care = care, onClick = onHome)
                model.storageError?.let { Text(it, style = T.body(14), color = C.Danger, modifier = Modifier.padding(top = 16.dp)) }
            }
            }
            }
        }
        model.review != null -> DraftReviewScreen(model, repository, care, onSaved)
        model.snapshot == null -> ChatPage {
            ChatHeader("开始记录 · ${person.name}", onBack = ::leave, trailing = { Spacer(Modifier.size(48.dp)) })
            Column(Modifier.weight(1f).fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                if (model.error != null || model.storageError != null) ChatError(model.storageError ?: model.error.orEmpty(), care = care, enabled = !model.busy) {
                    if (model.storageError != null) model.retryStorage() else model.retryOpen()
                } else { CircularProgressIndicator(color = C.AccentDeep); Text("正在打开记录…", Modifier.padding(top = 20.dp), style = T.body(if (care) 22 else 16), color = C.SecondaryInk) }
            }
        }
        model.needsLife || model.showLife -> LifeInterviewScreen(model, care, dictation, ::mic, ::leave) { history = it }
        else -> ChatPage {
            ChatHeader(if (care) "慢慢讲述" else "关于${person.relationship.takeIf { it.isNotBlank() }?.let { "$it · " }.orEmpty()}${person.name}",
                if (care) "3 / 3" else "AI 回忆助手", care, ::leave) {
                IconButton({ history = model.messages }, modifier = Modifier.semantics { contentDescription = "前面聊过的" }) { JournalGlyph("history") }
            }
            if (model.overview != null) TextButton({ dictation.cancel(); model.showLife = true }, Modifier.fillMaxWidth().heightIn(min = 44.dp), enabled = !model.busy) {
                Text("人生概览", style = T.body(if (care) 20 else 13), color = C.SecondaryInk)
            }
            val listState = rememberLazyListState()
            val follow = rememberChatAutoFollow(listState, listOf(model.messages.lastOrNull()?.id,
                model.messages.lastOrNull()?.content, model.messages.size, model.busy, model.progress, model.error, model.storageError))
            Box(Modifier.weight(1f).fillMaxWidth()) {
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 22.dp).testTag("chat.history"), state = listState,
                verticalArrangement = Arrangement.spacedBy(if (care) 20.dp else 14.dp)) {
                item { Text(if (care) "正在记录${person.name}的故事" else openedAt, Modifier.fillMaxWidth().padding(top = 14.dp),
                    style = T.body(if (care) 18 else 12), color = C.Muted, textAlign = TextAlign.Center) }
                if (care) {
                    model.messages.lastOrNull { it.role != "user" }?.let { latest -> item {
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(C.Surface).padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text("回忆助手", style = T.body(18), color = C.AccentDeep)
                            Text(latest.content, style = T.body(26, true), color = C.Ink, lineHeight = 39.sp, textAlign = TextAlign.Center, modifier = Modifier.testTag("care.chat.question"))
                        }
                    } }
                    item { TextButton({ history = model.messages }, Modifier.fillMaxWidth()) { Text("前面聊过的", style = T.body(20)) } }
                } else items(model.messages, key = { it.id }) { message ->
                    ChatMessageView(message, repository, localPhotos = if (message.id == model.pending?.id) model.photos else emptyList(), onPhoto = { photoPreview = it })
                }
                if (model.busy) item {
                    Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(18.dp), color = C.AccentDeep, strokeWidth = 2.dp)
                        Text(model.progress, style = T.body(if (care) 20 else 13), color = C.SecondaryInk)
                    }
                }
                model.error?.let { message -> item { ChatError(message, if (model.pending != null) "重试这条讲述" else "重试", care, !model.busy) {
                    if (model.pending != null) model.send() else model.retryOpen()
                } } }
                model.storageError?.let { message -> item { ChatError(message, "重试本机保存", care, !model.busy, model::retryStorage) } }
                if (model.completed) item { ChatButton("继续聊天", secondary = true, care = care, busy = model.busy, onClick = model::continueStory) }
                item(key = "chat.bottom") { Spacer(Modifier.fillMaxWidth().height(8.dp).testTag("chat.bottom")) }
            }
            ChatLatestButton(follow, listState, care, "chat", Modifier.align(Alignment.BottomEnd).padding(12.dp))
            }
            Column(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (if (care) careGenerationReady && !careContinuing else model.generationOffered && !dictation.busy && !readingPhotos) {
                    if (care) {
                        ChatButton("整理这段回忆", care = true, modifier = Modifier.padding(horizontal = 20.dp).testTag("chat.generate"), onClick = ::generateDraft)
                        Text("先看草稿，您点保存才会存入回忆。", style = T.body(18), color = C.SecondaryInk)
                        TextButton({ careContinuing = true }) { Text("我还想补充", style = T.body(20)) }
                    } else TextButton(::generateDraft, Modifier.clip(CircleShape).background(C.Surface).border(1.dp, C.Soft, CircleShape).testTag("chat.generate")) {
                        JournalGlyph("book", size = 18.dp, tint = C.AccentDeep)
                        Text("整理成一段回忆", Modifier.padding(start = 8.dp), style = T.body(14), color = C.AccentDeep)
                        Text(" · 先看草稿再保存", style = T.body(12), color = C.Muted)
                    }
                }
                if (care && model.photos.isNotEmpty()) TextButton({ managePhotos = true }, Modifier.testTag("chat.managePhotos")) {
                    Text("管理已选照片（${model.photos.size}/9）", style = T.body(20))
                }
                if (readingPhotos) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(18.dp), color = C.AccentDeep, strokeWidth = 2.dp)
                    Text(if (care) "正在读取照片…" else "正在读取与压缩照片…", style = T.body(if (care) 18 else 13), color = C.SecondaryInk)
                }
                val compactPhotos = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE || LocalDensity.current.fontScale > 1.3f
                val selection: (@Composable () -> Unit)? = if (!care && model.photos.isNotEmpty() && model.pending == null) {
                    {
                        if (compactPhotos) TextButton({ managePhotos = true }, Modifier.fillMaxWidth().testTag("chat.managePhotos")) {
                            Text("管理已选照片（${model.photos.size}/9）", style = T.body(14))
                        } else SelectedPhotoStrip(model.photos, !model.busy && model.pending == null, model::removePhoto, Modifier.padding(top = 8.dp))
                    }
                } else null
                if (!care || !careGenerationReady || careContinuing) NarrationComposer(model.input, model::updateInput, care,
                    enabled = !model.busy && !readingPhotos && model.pending == null && !model.completed,
                    sendEnabled = !model.busy && !readingPhotos && !dictation.busy && !model.completed && (model.pending != null || model.input.isNotBlank() || model.photos.isNotEmpty()),
                    retrying = model.pending != null, dictation = dictation, onMic = ::mic,
                    onSend = { follow.resume(); focus.clearFocus(); dictation.cancel(); model.send() }, onPhoto = ::pickPhoto,
                    photosEnabled = !model.busy && !readingPhotos && model.pending == null && !dictation.busy && model.photos.size < 9,
                    hasPhotos = model.photos.isNotEmpty(), selectedPhotos = selection)
                else TextButton(::pickPhoto, enabled = !readingPhotos && model.photos.size < 9) { Text("添加照片", style = T.body(19)) }
            }
        }
    }
    dictation.error?.let { message -> AlertDialog(onDismissRequest = { dictation.error = null }, title = { Text("语音输入") }, text = { Text(message) }, confirmButton = { TextButton({ dictation.error = null }) { Text("确定") } }) }
    mediaError?.let { message -> AlertDialog(onDismissRequest = { mediaError = null }, title = { Text("照片读取失败") }, text = { Text(message) }, confirmButton = { TextButton({ mediaError = null }) { Text("确定") } }) }
    history?.let { entries -> ChatHistoryDialog(entries, repository, care, onPhoto = { photoPreview = it }) { history = null } }
    photoPreview?.let { media -> ChatPhotoSheet("讲述照片", "关闭", { photoPreview = null }) {
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
            RemoteChatPhoto(media, repository, Modifier.fillMaxWidth().height(minOf(400.dp, maxHeight)), fit = true)
        }
    } }
    if (managePhotos) ChatPhotoSheet("已选照片", "完成", { managePhotos = false }) {
        Box(Modifier.weight(1f).fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
            SelectedPhotoStrip(model.photos, !model.busy && model.pending == null, model::removePhoto)
        }
    }
}

@Composable
internal fun NarrationComposer(value: String, onValue: (String) -> Unit, care: Boolean, enabled: Boolean,
    sendEnabled: Boolean, retrying: Boolean, dictation: MandarinDictation, onMic: () -> Unit, onSend: () -> Unit,
    onPhoto: (() -> Unit)? = null, photosEnabled: Boolean = false, tag: String = "chat",
    hasPhotos: Boolean = false, selectedPhotos: (@Composable () -> Unit)? = null) {
    val large = care || LocalDensity.current.fontScale > 1.3f
    Column(Modifier.fillMaxWidth().padding(horizontal = if (care) 20.dp else 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (dictation.busy) Text(dictation.status, style = T.body(if (care) 19 else 13), color = C.AccentDeep)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.Surface).border(1.dp, C.Line, RoundedCornerShape(28.dp)).padding(5.dp)
            .testTag("$tag.composer"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            selectedPhotos?.invoke()
            val input: @Composable (Modifier) -> Unit = { modifier ->
                OutlinedTextField(value, onValue, modifier.testTag("$tag.input").semantics { contentDescription = "讲述文字" }, enabled = enabled && !dictation.busy,
                    placeholder = { Text(if(hasPhotos) "也可以写几句话…" else "继续讲讲那一天…", style = T.body(if (care) 21 else 15), color = C.Placeholder) },
                    textStyle = T.body(if (care) 23 else 15), minLines = 1, maxLines = if (care) 5 else 4, shape = RoundedCornerShape(22.dp),
                    colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
                        disabledContainerColor = Color.Transparent, focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent, disabledIndicatorColor = Color.Transparent,
                        disabledTextColor = C.Ink, disabledLabelColor = C.SecondaryInk))
            }
            if (large) input(Modifier.fillMaxWidth())
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                if (onPhoto != null) IconButton(onPhoto, enabled = photosEnabled, modifier = Modifier.testTag("chat.addPhotos").semantics { contentDescription = "添加照片，每条消息最多九张" }) {
                    Box(Modifier.size(40.dp).clip(CircleShape).background(C.PaperSecondary), contentAlignment = Alignment.Center) { JournalGlyph("photo") }
                }
                if (!large) input(Modifier.weight(1f)) else Spacer(Modifier.weight(1f))
                IconButton(onMic, enabled = (enabled || dictation.busy) && dictation.phase != MandarinDictation.Phase.Finishing,
                    modifier = Modifier.testTag("$tag.dictation").semantics { contentDescription = if (dictation.busy) "停止语音输入" else "普通话语音输入" }) {
                    JournalGlyph(if (dictation.busy) "stop" else "mic", tint = if (dictation.busy) C.AccentDeep else C.SecondaryInk)
                }
                IconButton(onSend, enabled = sendEnabled, modifier = Modifier.size(if (care) 58.dp else 48.dp).testTag("$tag.send")
                    .semantics { contentDescription = if (retrying) "重试发送" else "发送" }) {
                    Box(Modifier.size(if (care) 48.dp else 40.dp).clip(CircleShape).background(C.Accent.copy(alpha = if (sendEnabled) 1f else 0.4f)), contentAlignment = Alignment.Center) {
                        JournalGlyph("up", tint = Color.White)
                    }
                }
            }
        }
    }
}

@Composable
internal fun SelectedPhotoStrip(photos: List<SelectedPhoto>, enabled: Boolean, onRemove: (String) -> Unit, modifier: Modifier = Modifier) {
    LazyRow(modifier.fillMaxWidth().padding(horizontal = 8.dp).testTag("chat.selectedPhotos"), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(photos, key = { it.id }) { photo ->
            val index = photos.indexOf(photo)
            Column(Modifier.width(84.dp)) {
                Box(Modifier.size(84.dp)) {
                    Box(Modifier.size(72.dp).align(Alignment.BottomStart).clip(RoundedCornerShape(10.dp))) {
                        LocalChatPhoto(photo.data, Modifier.fillMaxSize().testTag("chat.selectedPhoto.${photo.id}"), label = "待发送照片 ${index + 1}")
                        if(photo.status == "uploading") Box(Modifier.size(32.dp).align(Alignment.Center).clip(CircleShape).background(C.Surface), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(Modifier.size(20.dp).semantics { contentDescription = "照片 ${index + 1} 上传中" }, strokeWidth = 2.dp, color = C.AccentDeep)
                        }
                    }
                    IconButton({ onRemove(photo.id) }, enabled = enabled,
                        modifier = Modifier.size(48.dp).align(Alignment.TopEnd).testTag("chat.removePhoto.${photo.id}").semantics { contentDescription = "移除照片 ${index + 1}" }) {
                        Box(Modifier.size(24.dp).clip(CircleShape).background(C.Surface).border(1.dp, C.Line, CircleShape), contentAlignment = Alignment.Center) { JournalGlyph("close", size = 10.dp, tint = C.Ink) }
                    }
                }
                if(photo.status == "failed") Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
                    JournalGlyph("warning", size = 12.dp, tint = C.Accent)
                    Text("上传失败", style = T.body(11), color = C.Accent)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ChatPhotoSheet(title: String, closeLabel: String, onClose: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    val actionWidth = maxOf(64.dp, (32 * LocalDensity.current.fontScale + 32).dp)
    ModalBottomSheet(onDismissRequest = onClose, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        modifier = Modifier.testTag("chat.photos.sheet"), containerColor = C.Paper, dragHandle = null) {
        cn.shinian.app.ui.theme.ShinianImmersiveWindow()
        Column(Modifier.fillMaxWidth().fillMaxHeight(.92f)) {
            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.width(actionWidth))
                Text(title, style = T.body(18, true), color = C.Ink, textAlign = TextAlign.Center, modifier = Modifier.weight(1f))
                TextButton(onClose, Modifier.width(actionWidth).heightIn(min = 48.dp).testTag("chat.photos.close")) { Text(closeLabel, color = C.AccentDeep, style = T.body(16)) }
            }
            HorizontalDivider(color = C.Line)
            content()
        }
    }
}
