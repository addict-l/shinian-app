package cn.shinian.app.ui.memoir

import android.content.ClipData
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.ConnectivityManager
import android.net.Network
import android.provider.DocumentsContract
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import cn.shinian.app.data.*
import cn.shinian.app.media.preparePhoto
import cn.shinian.app.ui.media.rememberPhotoPicker
import cn.shinian.app.ui.theme.*
import kotlinx.coroutines.*

@Composable
fun MemoirScreen(person: Person, repository: BackendRepository, care: Boolean, onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val model = remember(person.id, repository.session.scopeKey) { MemoirController(context.applicationContext, person, repository, scope) }
    val state by model.state.collectAsState()
    var step by rememberSaveable { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<String?>(null) }
    var photoStory by remember { mutableStateOf<Memory?>(null) }
    var cropId by remember { mutableStateOf<String?>(null) }
    var localError by remember { mutableStateOf<String?>(null) }
    var confirmReset by remember { mutableStateOf(false) }
    var comparingVersions by remember { mutableStateOf(false) }
    var coverRetry by remember { mutableIntStateOf(0) }
    val activeCover = state.settings.coverPhotos.take(coverLimit(state.settings))
    val invalidCover = state.settings.coverTemplate != "text" && (activeCover.isEmpty() || activeCover.any { photo ->
        photo.sourceMemoryId != null && state.snapshot?.stories.orEmpty().none { story ->
            story.id == photo.sourceMemoryId && story.media.any { it.id == photo.id }
        }
    })
    val canGenerate = !state.busy && state.conflict == null && state.settings.isValid && !invalidCover && state.snapshot != null && model.stories.isNotEmpty()
    val bodySize = if (care) 22 else 15
    LaunchedEffect(model) { model.load() }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(model, lifecycle) {
        var resumed = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) { if (resumed) model.load(); resumed = true }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    DisposableEffect(model) {
        val connectivity = context.getSystemService(ConnectivityManager::class.java)
        var initialConnection = connectivity.activeNetwork != null
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                if (initialConnection) initialConnection = false else model.load()
            }
        }
        connectivity.registerDefaultNetworkCallback(callback)
        onDispose { connectivity.unregisterNetworkCallback(callback) }
    }
    val importPhoto = rememberPhotoPicker(1) { uris ->
        val uri = uris.firstOrNull()
        if (uri != null) scope.launch {
            try { model.importCover(preparePhoto(context, uri)) }
            catch (error: Exception) { localError = error.message ?: "无法读取照片，请重新选择。" }
        }
    }
    val saveDocument = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { uri ->
        if (uri != null) scope.launch {
            var saved = false
            try {
                val file = model.verifiedFile() ?: return@launch
                withContext(Dispatchers.IO) {
                    val destination = context.contentResolver.openOutputStream(uri) ?: error("无法打开保存位置。")
                    destination.use { output -> file.inputStream().use { it.copyTo(output) } }
                }
                saved = true
                Toast.makeText(context, "回忆录已保存", Toast.LENGTH_SHORT).show()
            } catch (error: CancellationException) { throw error
            } catch (error: Exception) { localError = error.message ?: "保存失败，请重试。" }
            finally {
                if (!saved) withContext(NonCancellable + Dispatchers.IO) {
                    // CreateDocument already created this destination; keep a rejected/failed export from leaving an empty PDF.
                    runCatching { DocumentsContract.deleteDocument(context.contentResolver, uri) }
                }
            }
        }
    }
    Column(Modifier.fillMaxSize().navigationBarsPadding().background(JournalColors.Paper)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "关闭回忆录") }
            Text("制作回忆录", style = JournalTypography.body(if (care) 26 else 18, true), modifier = Modifier.weight(1f))
            if (state.busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
            Text(state.label, style = JournalTypography.body(11), color = JournalColors.SecondaryInk, modifier = Modifier.padding(start = 6.dp).testTag("memoir-sync-status"))
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            listOf("封面", "故事与照片", "整本预览").forEachIndexed { i, title ->
                Text("${i + 1}  $title", color = if (step == i) JournalColors.AccentDeep else JournalColors.SecondaryInk,
                    style = JournalTypography.body(if (care) 16 else 12, step == i), modifier = Modifier.padding(vertical = 10.dp))
            }
        }
        if (state.conflict != null) {
            BookCard(Modifier.padding(horizontal = 22.dp)) {
                Text("制作设置有更新，请核对版本。", style = JournalTypography.body(bodySize, true))
                Text("本机：${state.settings.title}\n云端：${state.conflict!!.settings.title}", style = JournalTypography.body(bodySize))
                Text("封面照片、取景、副标题、章节和照片顺序会使用所选版本。", style = JournalTypography.body(if (care) 18 else 12), color = JournalColors.SecondaryInk)
                TextButton(onClick = { comparingVersions = true }, modifier = Modifier.testTag("memoir-conflict-compare")) { Text("查看完整差异") }
                Row { TextButton(onClick = model::chooseCloud) { Text("使用云端设置") }; TextButton(onClick = model::chooseLocal) { Text("保留本机设置") } }
            }
        }
        (localError ?: state.error)?.let { error ->
            Column(Modifier.fillMaxWidth().padding(horizontal = 22.dp)) {
                Text(error, color = JournalColors.Danger, style = JournalTypography.body(if (care) 20 else 13), modifier = Modifier.testTag("memoir-error"))
                if (state.conflict == null) TextButton(onClick = { localError = null; coverRetry++; model.load() }, modifier = Modifier.testTag("memoir-sync-retry")) { Text("重试同步") }
            }
        }
        when (step) {
            0 -> Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                val cover by rememberBookCover(model, state.settings, person.name, "${state.snapshot?.contentRevision}:$coverRetry") { localError = it }
                Spacer(Modifier.height(20.dp))
                cover?.let { Image(it.asImageBitmap(), "回忆录封面", Modifier.width(200.dp).aspectRatio(148f / 210).border(1.dp, JournalColors.Line).testTag("memoir-cover-preview")) }
                    ?: Box(Modifier.width(200.dp).aspectRatio(148f / 210).background(JournalColors.Film), contentAlignment = Alignment.Center) {
                        if (localError != null) Text("封面暂时无法读取", style = JournalTypography.body(bodySize), color = JournalColors.SecondaryInk) else CircularProgressIndicator()
                    }
                Text("${person.name}的回忆录 · A5 竖版", color = JournalColors.SecondaryInk, style = JournalTypography.body(12), modifier = Modifier.padding(top = 20.dp, bottom = 30.dp))
                BookCard {
                    SettingRow("封面样式", when (state.settings.coverTemplate) { "photo" -> "单照片"; "collage" -> "照片拼贴"; else -> "素雅文字" }, care) { panel = "style" }
                    HorizontalDivider(color = JournalColors.Line)
                    SettingRow("封面照片", if (state.settings.coverTemplate == "text") "素雅封面使用纯文字" else "更换照片与调整取景", care) { panel = "cover" }
                    HorizontalDivider(color = JournalColors.Line)
                    SettingRow("书名与副标题", state.settings.title, care) { panel = "name" }
                }
                Spacer(Modifier.height(24.dp))
                if (invalidCover) Text("请选择可用的封面照片，或改用素雅封面。", style = JournalTypography.body(bodySize), color = JournalColors.SecondaryInk)
                if (state.snapshot?.stories?.isEmpty() == true) Text("先保存一段回忆，就可以制作这本书。", style = JournalTypography.body(bodySize))
                Spacer(Modifier.height(24.dp))
            }
            1 -> LazyColumn(Modifier.weight(1f).padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(bottom = 24.dp)) {
                item {
                    BookCard {
                        SettingRow("正文字号", "${state.settings.textSize} pt", care) { panel = "reading" }
                        Text("${model.stories.size} 段回忆 · ${if (state.settings.ordering == "manual") "手动排序" else "按故事时间排序"}", style = JournalTypography.body(bodySize))
                        if (state.settings.ordering == "manual") TextButton(onClick = { confirmReset = true }) { Text("恢复时间排序") }
                    }
                }
                items(model.stories, key = { it.id }) { story ->
                    val index = model.stories.indexOf(story)
                    BookCard {
                        Text(story.title, style = JournalTypography.story(if (care) 25 else 20))
                        Text(story.dateLabel, color = JournalColors.SecondaryInk, style = JournalTypography.body(12))
                        Text(story.content, maxLines = 3, style = JournalTypography.body(bodySize))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            TextButton(onClick = { photoStory = story }) { Text("照片 ${selectedPhotos(state.settings, story).size}/${story.media.size}") }
                            Spacer(Modifier.weight(1f))
                            IconButton(enabled = index > 0, onClick = { model.update(state.settings.copy(ordering = "manual", storyOrder = moved(model.stories.map { it.id }, index, -1))) }) { Icon(Icons.Outlined.ArrowUpward, "上移${story.title}") }
                            IconButton(enabled = index < model.stories.lastIndex, onClick = { model.update(state.settings.copy(ordering = "manual", storyOrder = moved(model.stories.map { it.id }, index, 1))) }) { Icon(Icons.Outlined.ArrowDownward, "下移${story.title}") }
                        }
                    }
                }
            }
            else -> {
                val preview = state.preview
                if (preview != null) MemoirPdfPreview(preview, Modifier.weight(1f), care) { localError = it }
                else Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Outlined.MenuBook, null, Modifier.size(48.dp), tint = JournalColors.Accent)
                        Text("准备好后，看看整本回忆录。", style = JournalTypography.body(bodySize))
                        TextButton(enabled = canGenerate, onClick = { model.generate() }) { Text("生成整本预览") }
                    }
                }
            }
        }
        val failedPhotos = state.missingPhotos.filter { id ->
            activeCover.any { it.id == id } || model.stories.any { story -> selectedPhotos(state.settings, story).any { it.id == id } }
        }
        if (failedPhotos.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().heightIn(max = if (care) 190.dp else 150.dp).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp).testTag("memoir-missing-photos")) {
                failedPhotos.forEach { id ->
                    val isCover = activeCover.any { it.id == id }
                    val story = state.snapshot?.stories.orEmpty().firstOrNull { it.media.any { photo -> photo.id == id } }
                    Text("${if (isCover) "封面照片" else story?.title ?: "故事照片"} · 照片未加载", style = JournalTypography.body(if (care) 20 else 12), color = JournalColors.Danger)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        TextButton(enabled = canGenerate, onClick = { localError = null; coverRetry++; model.generate() }, modifier = Modifier.testTag("memoir-photo-retry.$id")) { Text("重试") }
                        if (isCover) {
                            TextButton(onClick = { step = 0; panel = "cover" }) { Text("更换") }
                            TextButton(onClick = { model.update(state.settings.copy(coverTemplate = "text")) }) { Text("改用素雅封面") }
                        } else TextButton(onClick = {
                            model.update(state.settings.copy(excludedPhotoIds = (state.settings.excludedPhotoIds + id).distinct()))
                        }, modifier = Modifier.testTag("memoir-photo-exclude.$id")) { Text("取消本故事照片选择") }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (step > 0) OutlinedButton(onClick = { step-- }, enabled = !state.busy, modifier = Modifier.heightIn(min = 48.dp)) { Text("上一步") }
            if (step < 2) Button(onClick = { step++; if (step == 2) model.generate() }, enabled = canGenerate,
                modifier = Modifier.weight(1f).heightIn(min = if (care) 60.dp else 48.dp), shape = RoundedCornerShape(24.dp)) { Text(if (step == 0) "下一步 · 故事与照片" else "生成整本预览") }
            else {
                OutlinedButton(enabled = canGenerate, onClick = { model.generate() }, modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text("重新生成") }
                Button(enabled = state.preview != null && !state.busy && state.conflict == null, onClick = { panel = "share" }, modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text("保存 / 分享") }
            }
        }
    }
    if (comparingVersions) state.conflict?.let { cloud ->
        MemoirConflictDialog(model, person, state.settings, state.snapshot?.stories.orEmpty(), cloud, care,
            onClose = { comparingVersions = false }, onCloud = { comparingVersions = false; model.chooseCloud() },
            onLocal = { comparingVersions = false; model.chooseLocal() }, onError = { localError = it })
    }
    if (confirmReset) AlertDialog(onDismissRequest = { confirmReset = false }, title = { Text("恢复时间排序？") }, text = { Text("这会替换手动调整的故事顺序。") },
        confirmButton = { TextButton(onClick = { model.update(state.settings.copy(ordering = "time")); confirmReset = false }) { Text("恢复时间排序") } },
        dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("取消") } })
    panel?.let { selected ->
        AlertDialog(onDismissRequest = { panel = null }, title = { Text(when (selected) { "style" -> "封面样式"; "name" -> "书名与副标题"; "cover" -> "封面照片"; "reading" -> "阅读设置"; else -> "保存与分享" }) },
            text = {
                Column(Modifier.heightIn(max = 500.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    when (selected) {
                        "name" -> {
                            OutlinedTextField(state.settings.title, { model.update(state.settings.copy(title = it)) }, label = { Text("书名") }, modifier = Modifier.testTag("memoir-title"))
                            OutlinedTextField(state.settings.subtitle, { model.update(state.settings.copy(subtitle = it)) }, label = { Text("副标题（选填）") }, modifier = Modifier.testTag("memoir-subtitle"))
                        }
                        "style" -> listOf("photo" to "单照片", "collage" to "照片拼贴", "text" to "素雅文字").forEach { (id, title) ->
                            Row(Modifier.fillMaxWidth().clickable { model.update(state.settings.copy(coverTemplate = id)) }.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(state.settings.coverTemplate == id, onClick = { model.update(state.settings.copy(coverTemplate = id)) }); Text(title)
                            }
                        }
                        "reading" -> listOf(16 to "大字 · 16 pt", 14 to "标准 · 14 pt").forEach { (size, title) ->
                            Row(Modifier.fillMaxWidth().clickable { model.update(state.settings.copy(textSize = size)) }, verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(state.settings.textSize == size, onClick = { model.update(state.settings.copy(textSize = size)) }); Text(title)
                            }
                        }
                        "cover" -> {
                            if (coverLimit(state.settings) == 0) Text("素雅封面使用纯文字。选择单照片或拼贴后，可设置封面照片。")
                            else {
                                TextButton(onClick = importPhoto) { Text("从相册导入") }
                                state.settings.coverPhotos.take(coverLimit(state.settings)).forEach { photo ->
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        BookPhoto(model, photo.id, Modifier.size(72.dp))
                                        TextButton(onClick = { cropId = photo.id }) { Text("调整取景") }
                                        IconButton(onClick = { model.update(state.settings.copy(coverPhotos = state.settings.coverPhotos.filterNot { it.id == photo.id })) }) { Icon(Icons.Outlined.Close, "移除封面照片") }
                                    }
                                }
                                Text("也可以使用故事中的照片", style = JournalTypography.body(bodySize, true))
                                state.snapshot?.stories.orEmpty().filter { it.media.isNotEmpty() }.forEach { story ->
                                    Text(story.title)
                                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        story.media.forEach { photo ->
                                            BookPhoto(model, photo.id, Modifier.size(82.dp).clickable { model.addCover(MemoirCoverPhoto(photo.id, story.id)) })
                                        }
                                    }
                                }
                            }
                        }
                        "share" -> {
                            TextButton(onClick = { panel = null; saveDocument.launch(safeFilename(state.settings.title) + ".pdf") }) { Text("保存 PDF 到文件") }
                            TextButton(onClick = {
                                panel = null
                                scope.launch {
                                    try {
                                        val file = model.verifiedFile() ?: return@launch
                                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                                        val intent = Intent(Intent.ACTION_SEND).apply {
                                            type = "application/pdf"; putExtra(Intent.EXTRA_STREAM, uri)
                                            clipData = ClipData.newRawUri("回忆录", uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                        }
                                        context.startActivity(Intent.createChooser(intent, "分享回忆录"))
                                    } catch (error: Exception) { localError = error.message ?: "无法打开分享，请重试。" }
                                }
                            }) { Text("分享 PDF") }
                        }
                    }
                }
            }, confirmButton = { TextButton(onClick = { panel = null }) { Text("完成") } })
    }
    cropId?.let { id ->
        MemoirCropDialog(model, person, state.settings, state.snapshot?.contentRevision, id, care,
            onSelect = { cropId = it }, onClose = { cropId = null }, onError = { localError = it })
    }
    photoStory?.let { story ->
        AlertDialog(onDismissRequest = { photoStory = null }, title = { Text("故事照片") }, text = {
            Column(Modifier.heightIn(max = 450.dp).verticalScroll(rememberScrollState())) {
                if (story.media.isEmpty()) Text("这段回忆还没有照片。")
                state.settings.photos(story).forEachIndexed { index, photo ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(photo.id !in state.settings.excludedPhotoIds, onCheckedChange = { checked ->
                            model.update(state.settings.copy(excludedPhotoIds = if (checked) state.settings.excludedPhotoIds - photo.id else (state.settings.excludedPhotoIds + photo.id).distinct()))
                        })
                        BookPhoto(model, photo.id, Modifier.size(60.dp))
                        IconButton(enabled = index > 0, onClick = { model.update(state.settings.copy(photoOrders = state.settings.photoOrders + (story.id.lowercase() to moved(state.settings.photos(story).map { it.id }, index, -1)))) }) { Icon(Icons.Outlined.ArrowUpward, "照片上移") }
                        IconButton(enabled = index < story.media.lastIndex, onClick = { model.update(state.settings.copy(photoOrders = state.settings.photoOrders + (story.id.lowercase() to moved(state.settings.photos(story).map { it.id }, index, 1)))) }) { Icon(Icons.Outlined.ArrowDownward, "照片下移") }
                    }
                }
            }
        }, confirmButton = { TextButton(onClick = { photoStory = null }) { Text("完成") } })
    }
}

private fun moved(ids: List<String>, index: Int, direction: Int): List<String> = ids.toMutableList().apply { add((index + direction).coerceIn(0, lastIndex), removeAt(index)) }

@Composable
private fun BookCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp), color = JournalColors.Surface, border = BorderStroke(1.dp, JournalColors.Line)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
    }
}

@Composable
private fun SettingRow(title: String, value: String, care: Boolean, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).heightIn(min = if (care) 76.dp else 60.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) { Text(title, style = JournalTypography.body(if (care) 22 else 15, true)); Text(value, style = JournalTypography.body(if (care) 18 else 12), color = JournalColors.SecondaryInk) }
        Icon(Icons.Outlined.ChevronRight, null, tint = JournalColors.SecondaryInk)
    }
}

@Composable
internal fun BookPhoto(model: MemoirController, id: String, modifier: Modifier) {
    val bitmap by produceState<Bitmap?>(null, id) {
        try {
            val file = model.image(id)
            value = withContext(Dispatchers.IO) {
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(file.absolutePath, bounds)
                var sample = 1
                while (bounds.outWidth / sample > 384 || bounds.outHeight / sample > 384) sample *= 2
                BitmapFactory.decodeFile(file.absolutePath, BitmapFactory.Options().apply { inSampleSize = sample })
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { value = null }
    }
    if (bitmap != null) Image(bitmap!!.asImageBitmap(), "回忆照片", modifier, contentScale = ContentScale.Crop)
    else Box(modifier.background(JournalColors.PaperSecondary), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Image, "照片正在读取") }
}
