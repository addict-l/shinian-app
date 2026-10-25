package cn.shinian.app.ui.browse

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Role
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.intl.LocaleList
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import cn.shinian.app.data.Memory
import cn.shinian.app.data.Media
import cn.shinian.app.data.Person
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.chat.MandarinDictation
import cn.shinian.app.ui.care.CareTypography as T
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.ceil

@Composable
internal fun rememberCareMicrophone(dictation: MandarinDictation, initialText: String): () -> Unit {
    val context = LocalContext.current
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (allowed) dictation.start(initialText)
        else dictation.error = "请在系统设置中允许麦克风，或使用键盘输入。已有文字会保留。"
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(dictation, lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) dictation.cancel() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); dictation.cancel() }
    }
    return {
        when (dictation.phase) {
            MandarinDictation.Phase.Recording -> dictation.stop()
            MandarinDictation.Phase.Preparing -> dictation.cancel()
            MandarinDictation.Phase.Finishing -> Unit
            MandarinDictation.Phase.Idle -> if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
                dictation.start(initialText) else permission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }
}

@Composable
internal fun CareStoryScreen(memory: Memory, people: List<Person>, onBack: () -> Unit,
    onActions: (() -> Unit)? = null, onHome: (() -> Unit)? = null, identityOverride: String? = null,
    extra: @Composable ColumnScope.() -> Unit = {}) {
    val context = LocalContext.current
    val preferences = remember { context.getSharedPreferences("journal_preferences", 0) }
    var readingScale by remember { mutableFloatStateOf(preferences.getFloat("care.readingScale", 1f).coerceIn(1f, 1.6f)) }
    val speech = remember(memory.id) { CareSpeech(context.applicationContext) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(speech, lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_PAUSE || event == Lifecycle.Event.ON_STOP) speech.stop() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); speech.close() }
    }
    fun scale(delta: Float) { readingScale = (readingScale + delta).coerceIn(1f, 1.6f); preferences.edit().putFloat("care.readingScale", readingScale).apply() }
    CarePage {
        CareReadingToolbar(readingScale, speech.speaking, ::scale, onBack) { speech.toggle(memory.title, memory.content) }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(top = 12.dp, bottom = 24.dp)
            .testTag("care.reading.scroll"), verticalArrangement = Arrangement.spacedBy(20.dp)) {
            memory.media.firstOrNull()?.let { MemoryPhoto(it, Modifier.fillMaxWidth().height(200.dp), radius = 24.dp) }
            val person = people.firstOrNull { it.id == (memory.primaryPersonId ?: memory.personIds.firstOrNull()) }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                person?.let { LocalPortrait(it.id, it, size = 34.dp, care = true) }
                Text(identityOverride ?: memoryIdentity(memory, people), style = T.body(18), color = CareColors.SecondaryInk)
            }
            Text(memory.title, style = T.story(31), color = CareColors.Ink)
            CareMemoryFacts(memory)
            SelectionContainer {
                Text(memory.content, style = T.story(22 * readingScale, lineSpacing = 10f),
                    color = CareColors.Ink, modifier = Modifier.fillMaxWidth().testTag("care.story.body"))
            }
            memory.media.drop(1).forEach { CareReadingPhoto(it) }
            extra()
        }
        onActions?.let { CareDock { CareButton("回忆操作", icon = "more", secondary = true, modifier = Modifier.testTag("memory.actions"), onClick = it) } }
        if (onActions == null) onHome?.let { CareDock { CareButton("回到首页", icon = "home", secondary = true,
            modifier = Modifier.testTag("care.saved.home"), onClick = it) } }
    }
    speech.error?.let { message -> AlertDialog(onDismissRequest = { speech.error = null }, title = { Text("朗读") }, text = { Text(message) },
        confirmButton = { TextButton({ speech.error = null }) { Text("确定") } }) }
}

@Composable
private fun CareReadingToolbar(readingScale: Float, speaking: Boolean, onScale: (Float) -> Unit, onBack: () -> Unit, onListen: () -> Unit) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val listenTitle = if (speaking) "停一下" else "听一听"
    val backWidth = with(density) { measurer.measure(AnnotatedString("返回"), T.body(20)).size.width.toDp() } + (20f * .733333333f).dp + 35.dp
    val listenWidth = with(density) { measurer.measure(AnnotatedString(listenTitle), T.body(19, true)).size.width.toDp() } + (19f * if (speaking) 1f else 1.4f).dp + 31.dp
    val back: @Composable () -> Unit = { CareReadingControl("返回", "back", 20, false, false, "care.back", onBack) }
    val sizes: @Composable () -> Unit = { CareReadingSizeControls(readingScale, onScale) }
    val listen: @Composable () -> Unit = { CareReadingControl(listenTitle, if (speaking) "stop" else "speaker", 19, true, true, "care.reading.speak", onListen) }
    BoxWithConstraints(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)) {
        if (backWidth + 97.dp + listenWidth + 24.dp <= maxWidth) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                back(); Spacer(Modifier.weight(1f)); sizes(); listen()
            }
        } else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            back()
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) { sizes(); listen() }
        }
    }
}

@Composable
private fun CareReadingSizeControls(readingScale: Float, onScale: (Float) -> Unit) {
    Row(Modifier.clip(CircleShape).background(CareColors.Surface).border(1.5.dp, CareColors.Border, CircleShape), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.width(48.dp).heightIn(min = 52.dp).clickable(enabled = readingScale > 1f, role = Role.Button) { onScale(-.15f) }
            .testTag("care.reading.smaller").semantics { contentDescription = "缩小正文" }, contentAlignment = Alignment.Center) {
            Text("A−", style = T.body(20, true), color = CareColors.Ink)
        }
        Box(Modifier.width(1.dp).height(30.dp).background(CareColors.Border))
        Box(Modifier.width(48.dp).heightIn(min = 52.dp).clickable(enabled = readingScale < 1.6f, role = Role.Button) { onScale(.15f) }
            .testTag("care.reading.larger").semantics { contentDescription = "放大正文" }, contentAlignment = Alignment.Center) {
            Text("A+", style = T.body(23, true), color = CareColors.Ink)
        }
    }
}

@Composable
private fun CareReadingControl(title: String, icon: String, size: Int, bold: Boolean, faint: Boolean, tag: String, action: () -> Unit) {
    Box(Modifier.heightIn(min = 52.dp).clip(CircleShape).background(if (faint) CareColors.Faint else CareColors.Surface)
        .border(if (faint) 1.dp else 1.5.dp, CareColors.Border, CircleShape).clickable(role = Role.Button, onClick = action)
        .testTag(tag).padding(horizontal = if (faint) 12.dp else 14.dp), contentAlignment = Alignment.Center) {
        Row(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
            CareSymbol(icon, size.dp, tint = CareColors.Accent)
            Text(title, style = T.body(size, bold), color = CareColors.Accent, maxLines = 1, softWrap = false)
        }
    }
}

@Composable
internal fun CareMemoryFacts(memory: Memory) {
    val values = listOf("时间" to careMeaningful(memory.dateLabel), "地点" to careMeaningful(memory.place.value), "感受" to careMeaningful(memory.feeling.value))
    if (values.all { it.second == null }) return
    Row(Modifier.fillMaxWidth().background(CareColors.Surface, RoundedCornerShape(22.dp))
        .border(1.dp, CareColors.Border, RoundedCornerShape(22.dp))) {
            values.forEachIndexed { index, (label, value) ->
                Column(Modifier.weight(1f).drawWithContent {
                    drawContent()
                    if (index < values.lastIndex) {
                        val x = size.width - .5.dp.toPx()
                        drawLine(CareColors.Line, Offset(x, 0f), Offset(x, size.height), strokeWidth = 1.dp.toPx())
                    }
                }.padding(horizontal = 10.dp, vertical = 16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(label, style = T.body(17), color = CareColors.SecondaryInk)
                    CareReadingFactValue(value ?: "待补充", if (label == "感受") CareColors.Accent else CareColors.Ink)
                }
            }
    }
}

@Composable
private fun CareReadingFactValue(value: String, color: androidx.compose.ui.graphics.Color) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val style = T.body(21, true).copy(textAlign = TextAlign.Start, lineBreak = LineBreak.Heading, localeList = LocaleList("zh-CN"))
    BoxWithConstraints(Modifier.fillMaxWidth(), contentAlignment = Alignment.TopCenter) {
        val layout = measurer.measure(AnnotatedString(value), style, constraints = Constraints(maxWidth = with(density) { maxWidth.roundToPx() }))
        val lineWidth = (0 until layout.lineCount).maxOfOrNull { layout.getLineRight(it) - layout.getLineLeft(it) } ?: 0f
        val blockWidth = with(density) { ceil(lineWidth).toInt().toDp() }.coerceAtMost(maxWidth)
        Text(value, style = style, color = color, modifier = Modifier.width(blockWidth))
    }
}

/** The reading page's additional photos keep their own aspect ratio, inside a minimum 160pt area. */
@Composable
private fun CareReadingPhoto(media: Media) {
    val repository = LocalBrowseRepository.current
    var bitmap by remember(media.id, repository?.session?.scopeKey) { mutableStateOf<ImageBitmap?>(null) }
    var error by remember(media.id) { mutableStateOf(false) }
    var retry by remember(media.id) { mutableIntStateOf(0) }
    LaunchedEffect(media.id, repository, retry) {
        if (repository == null) return@LaunchedEffect
        error = false
        try {
            bitmap = withContext(Dispatchers.IO) {
                val bytes = repository.loadMedia(media)
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                var sample = 1
                while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 2000) sample *= 2
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })?.asImageBitmap()
            }
            if (bitmap == null) error = true
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { error = true }
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val image = bitmap
        val imageHeight = image?.let { maxWidth * (it.height.toFloat() / it.width.coerceAtLeast(1)) } ?: 160.dp
        Box(Modifier.fillMaxWidth().height(imageHeight.coerceAtLeast(160.dp)).clip(RoundedCornerShape(24.dp)).background(CareColors.PaperSecondary), contentAlignment = Alignment.Center) {
            if (image != null) Image(image, "回忆照片", Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
            else if (error) TextButton({ retry++ }) { Text("重试照片", style = T.body(18), color = CareColors.Accent) }
            else CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = CareColors.SecondaryInk)
        }
    }
}

private class CareSpeech(context: android.content.Context) {
    var speaking by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
    private var ready = false
    private var closed = false
    private var currentID: String? = null
    private val main = Handler(Looper.getMainLooper())
    private var engine: TextToSpeech? = null
    init {
        engine = TextToSpeech(context) { status -> main.post {
            if (!closed) ready = status == TextToSpeech.SUCCESS
        } }
        engine?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String?) = Unit
            override fun onDone(id: String?) { main.post { if (id == currentID) { speaking = false; currentID = null } } }
            @Deprecated("Platform callback")
            override fun onError(id: String?) { main.post {
                val active = currentID
                if (active != null && (id == active || id?.startsWith("$active-") == true)) { stop(); error = "朗读暂时不可用，请稍后再试。" }
            } }
        })
    }
    fun toggle(title: String, body: String) {
        if (speaking) { stop(); return }
        val value = engine
        if (!ready || value == null) { error = "中文朗读服务尚未准备好，请稍后再试，或在系统设置中安装中文语音。"; return }
        if (value.setLanguage(Locale.SIMPLIFIED_CHINESE) < TextToSpeech.LANG_AVAILABLE) { error = "设备尚未安装中文朗读语音，请在系统设置中添加。"; return }
        val id = UUID.randomUUID().toString()
        currentID = id
        val text = "$title。\n$body"
        // Engines have a fixed input limit. Queue complete chunks and let only the final one finish this reading.
        val chunks = careSpeechChunks(text, TextToSpeech.getMaxSpeechInputLength())
        value.setSpeechRate(.85f)
        for ((index, chunk) in chunks.withIndex()) {
            val result = value.speak(chunk, if (index == 0) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null,
                if (index == chunks.lastIndex) id else "$id-$index")
            if (result == TextToSpeech.ERROR) { stop(); error = "朗读暂时不可用，请稍后再试。"; return }
        }
        speaking = true
    }
    fun stop() { currentID = null; engine?.stop(); speaking = false }
    fun close() { closed = true; stop(); engine?.shutdown(); engine = null }
}

/** Preserve UTF-16 pairs while respecting the engine's maximum input length. */
internal fun careSpeechChunks(text: String, limit: Int): List<String> {
    require(limit >= 2)
    val result = mutableListOf<String>()
    var start = 0
    while (start < text.length) {
        var end = minOf(start + limit, text.length)
        if (end < text.length && text[end - 1].isHighSurrogate() && text[end].isLowSurrogate()) end--
        result += text.substring(start, end)
        start = end
    }
    return result
}
