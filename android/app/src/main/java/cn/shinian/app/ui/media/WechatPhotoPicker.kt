package cn.shinian.app.ui.media

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import cn.shinian.app.media.DevicePhoto
import cn.shinian.app.media.DevicePhotoLibrary
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.max
import kotlin.math.min

private object PickerColors {
    val Background = Color(0xFF111111)
    val Bar = Color(0xFF202020)
    val Muted = Color(0xFFB5B5B5)
    val Line = Color(0xFF3A3A3A)
    val Green = Color(0xFF07C160)
    val SelectedGreen = Color(0xFF078444)
    val White = Color(0xFFF5F5F5)
}

private enum class PhotoAccess { Full, Partial, None }
private const val ALL_ALBUMS = "__all_photos__"

private fun photoPermissions(): Array<String> = when {
    Build.VERSION.SDK_INT >= 34 -> arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
    Build.VERSION.SDK_INT >= 33 -> arrayOf(Manifest.permission.READ_MEDIA_IMAGES)
    else -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
}

private fun photoAccess(context: android.content.Context): PhotoAccess {
    fun granted(permission: String) = context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
    return when {
        Build.VERSION.SDK_INT >= 33 && granted(Manifest.permission.READ_MEDIA_IMAGES) -> PhotoAccess.Full
        Build.VERSION.SDK_INT < 33 && granted(Manifest.permission.READ_EXTERNAL_STORAGE) -> PhotoAccess.Full
        Build.VERSION.SDK_INT >= 34 && granted(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) -> PhotoAccess.Partial
        else -> PhotoAccess.None
    }
}

/** Selection is returned only after Done. Closing, browsing and permission changes never send a message. */
@Composable
fun WechatPhotoPicker(
    maxSelection: Int,
    onDismiss: () -> Unit,
    onConfirm: (List<Uri>) -> Unit,
    onSystemPicker: () -> Unit,
) {
    val context = LocalContext.current
    val library = remember(context.applicationContext) { DevicePhotoLibrary(context.applicationContext) }
    val scope = rememberCoroutineScope()
    val grid = rememberLazyGridState()
    val limit = maxSelection.coerceAtLeast(1)
    var selected by rememberSaveable { mutableStateOf(listOf<String>()) }
    var album by rememberSaveable { mutableStateOf(ALL_ALBUMS) }
    var albumsOpen by rememberSaveable { mutableStateOf(false) }
    var previewKeys by rememberSaveable { mutableStateOf<List<String>?>(null) }
    var previewIndex by rememberSaveable { mutableIntStateOf(0) }
    var previewSession by rememberSaveable { mutableIntStateOf(0) }
    var didRequest by rememberSaveable { mutableStateOf(false) }
    var photos by remember { mutableStateOf<List<DevicePhoto>>(emptyList()) }
    var access by remember { mutableStateOf(photoAccess(context)) }
    var loading by remember { mutableStateOf(true) }
    var failure by remember { mutableStateOf<String?>(null) }
    var loadJob by remember { mutableStateOf<Job?>(null) }
    var loadGeneration by remember { mutableIntStateOf(0) }
    var notice by remember { mutableStateOf("") }
    var noticeSequence by remember { mutableIntStateOf(0) }
    LaunchedEffect(album) { grid.scrollToItem(0) }
    fun inform(message: String) { notice = message; noticeSequence++ }
    LaunchedEffect(noticeSequence) { if (notice.isNotEmpty()) { delay(2800); notice = "" } }

    fun refresh() {
        val generation = ++loadGeneration
        loadJob?.cancel()
        loading = true
        access = photoAccess(context)
        loadJob = scope.launch(Dispatchers.Main.immediate) {
            try {
                val allowed = library.load()
                if (generation != loadGeneration) return@launch
                val allowedKeys = allowed.mapTo(hashSetOf()) { it.uri.toString() }
                val remaining = selected.filter { it in allowedKeys }.take(limit)
                if (remaining.size < selected.size) inform("部分照片已无法访问，已移出选择。")
                selected = remaining
                photos = allowed
                if (album != ALL_ALBUMS && allowed.none { it.albumId == album }) album = ALL_ALBUMS
                access = photoAccess(context)
                failure = null
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: SecurityException) {
                photos = emptyList(); selected = emptyList(); access = photoAccess(context)
                failure = "照片访问权限已变化，请重新允许访问或使用系统选图。"
            } catch (_: Exception) { failure = "暂时无法读取照片，请重试或使用系统选图。" }
            finally { if (generation == loadGeneration) loading = false }
        }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { refresh() }
    fun requestAccess() { didRequest = true; permission.launch(photoPermissions()) }
    fun settings() {
        try { context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))) }
        catch (_: Exception) { inform("请在系统设置中允许拾年访问照片。") }
    }
    LaunchedEffect(library) {
        if (!didRequest && photoAccess(context) == PhotoAccess.None) requestAccess() else refresh()
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, library) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) refresh() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); loadJob?.cancel() }
    }
    fun removeUnreadable(photo: DevicePhoto) {
        val key = photo.uri.toString()
        photos = photos.filterNot { it.uri.toString() == key }
        if (key in selected) { selected = selected - key; inform("这张照片已无法访问，已移出选择。") }
    }
    fun toggle(photo: DevicePhoto) {
        if (loading || failure != null) return
        val key = photo.uri.toString()
        if (key in selected) selected = selected - key
        else if (selected.size < limit) selected = selected + key
        else inform("最多只能选择 $limit 张照片")
    }
    fun openPreview(keys: List<String>, index: Int) {
        if (keys.isEmpty()) return
        previewKeys = keys; previewIndex = index; previewSession++
    }
    val byUri = remember(photos) { photos.associateBy { it.uri.toString() } }
    val previewPhotos = previewKeys?.mapNotNull { byUri[it] }.orEmpty()
    val visible = remember(photos, album) { if (album == ALL_ALBUMS) photos else photos.filter { it.albumId == album } }
    val currentPreview = previewPhotos.getOrNull(previewIndex.coerceIn(0, max(0, previewPhotos.lastIndex)))
    LaunchedEffect(loading, previewPhotos.isEmpty()) { if (!loading && previewKeys != null && previewPhotos.isEmpty()) previewKeys = null }
    fun back() {
        when { previewKeys != null -> previewKeys = null; albumsOpen -> albumsOpen = false; else -> onDismiss() }
    }
    fun confirm() {
        if (loading || failure != null) return
        val allowed = selected.mapNotNull { byUri[it]?.uri }
        if (allowed.isNotEmpty()) onConfirm(allowed)
    }

    Dialog(onDismissRequest = ::back, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false, dismissOnClickOutside = false)) {
        PickerSystemBars()
        Column(Modifier.fillMaxSize().background(PickerColors.Background)
            .windowInsetsPadding(WindowInsets.safeDrawing).testTag("picker.root")) {
            if (previewKeys != null) {
                PickerPreviewHeader(previewIndex, previewPhotos.size, currentPreview?.let { selected.indexOf(it.uri.toString()).takeIf { index -> index >= 0 } },
                    enabled = !loading && failure == null && currentPreview != null,
                    onClose = { previewKeys = null }, onSelect = { currentPreview?.let(::toggle) }, photo = currentPreview)
            } else {
                PickerHeader(if (album == ALL_ALBUMS) "全部照片" else visible.firstOrNull()?.albumName ?: "相册", albumsOpen,
                    onDismiss, { albumsOpen = !albumsOpen })
            }
            if (access != PhotoAccess.Full && previewKeys == null && !loading && failure == null && photos.isNotEmpty()) {
                PermissionNotice(if (access == PhotoAccess.Partial) "仅显示你允许访问的照片" else "仅显示当前可访问的照片，可允许访问更多照片。",
                    if (access == PhotoAccess.Partial) "管理" else "允许访问", ::requestAccess, onSystemPicker, ::settings)
            }
            Box(Modifier.weight(1f).fillMaxWidth().background(if (previewKeys != null) Color.Black else PickerColors.Background)) {
                when {
                    loading -> PickerLoading()
                    failure != null -> PickerEmpty(failure!!, true, ::refresh, ::requestAccess, ::settings, onSystemPicker)
                    photos.isEmpty() -> PickerEmpty(when (access) {
                        PhotoAccess.Full -> "还没有可选照片"
                        PhotoAccess.Partial -> "目前没有可访问的照片，请管理照片权限或使用系统选图。"
                        PhotoAccess.None -> "允许访问照片后，在这里选择想分享的照片。"
                    }, false, ::refresh, ::requestAccess, ::settings, onSystemPicker)
                    previewKeys != null -> key(previewSession) {
                        PickerPreview(library, previewPhotos, previewIndex, { previewIndex = it }, ::removeUnreadable)
                    }
                    albumsOpen -> PickerAlbums(library, photos, album, { album = it; albumsOpen = false }, ::removeUnreadable)
                    else -> LazyVerticalGrid(columns = GridCells.Fixed(4), state = grid, modifier = Modifier.fillMaxSize().testTag("picker.grid"),
                        horizontalArrangement = Arrangement.spacedBy(2.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        items(visible, key = { it.uri.toString() }) { photo ->
                            PickerPhotoCell(library, photo, selected.indexOf(photo.uri.toString()).takeIf { it >= 0 },
                                onOpen = { openPreview(visible.map { it.uri.toString() }, visible.indexOf(photo)) },
                                onSelect = { toggle(photo) }, onUnreadable = ::removeUnreadable)
                        }
                    }
                }
                if (notice.isNotEmpty()) Text(notice, color = PickerColors.White, fontSize = 14.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xEE363636)).padding(14.dp)
                        .semantics { liveRegion = LiveRegionMode.Polite }.testTag("picker.notice"))
            }
            PickerFooter(selected.size, limit, enabled = !loading && failure == null,
                onPreview = { openPreview(selected, 0) }, onConfirm = ::confirm)
        }
    }
}

@Composable
private fun PickerSystemBars() {
    cn.shinian.app.ui.theme.ShinianImmersiveWindow(darkBackground = true)
}

@Composable
private fun PickerHeader(title: String, open: Boolean, onClose: () -> Unit, onAlbums: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(PickerColors.Bar).heightIn(min = 56.dp).padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClose, Modifier.size(48.dp).testTag("picker.close")) { Icon(Icons.Outlined.Close, "关闭照片选择", tint = PickerColors.White) }
        Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
            Row(Modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(26.dp)).background(PickerColors.Line)
                .clickable(onClick = onAlbums).padding(horizontal = 12.dp).testTag("picker.album"), verticalAlignment = Alignment.CenterVertically) {
                Text(if (open) "相册" else title, color = PickerColors.White, fontSize = 17.sp, fontWeight = FontWeight.Medium, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                Icon(if (open) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, "切换相册", tint = PickerColors.White, modifier = Modifier.size(22.dp))
            }
        }
        Spacer(Modifier.size(48.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PermissionNotice(message: String, action: String, onManage: () -> Unit, onSystem: () -> Unit, onSettings: () -> Unit) {
    Column(Modifier.fillMaxWidth().background(PickerColors.Bar).padding(horizontal = 14.dp, vertical = 8.dp)) {
        Text(message, color = PickerColors.Muted, fontSize = 13.sp)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onManage, Modifier.heightIn(min = 48.dp).testTag("picker.permission")) { Text(action, color = PickerColors.Green) }
            TextButton(onSystem, Modifier.heightIn(min = 48.dp).testTag("picker.systemPicker")) { Text("系统选图", color = PickerColors.White) }
            TextButton(onSettings, Modifier.heightIn(min = 48.dp).testTag("picker.settings")) { Text("打开设置", color = PickerColors.Muted) }
        }
    }
}

@Composable
private fun PickerLoading() {
    Box(Modifier.fillMaxSize().testTag("picker.loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(Modifier.size(28.dp), color = PickerColors.Green, strokeWidth = 2.dp)
    }
}

@Composable
private fun PickerEmpty(message: String, retry: Boolean, onRetry: () -> Unit, onPermission: () -> Unit, onSettings: () -> Unit, onSystem: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically)) {
        Icon(Icons.Outlined.PhotoLibrary, null, Modifier.size(44.dp), tint = PickerColors.Muted)
        Text(message, color = PickerColors.White, fontSize = 17.sp, textAlign = TextAlign.Center)
        if (retry) TextButton(onRetry, Modifier.heightIn(min = 48.dp).testTag("picker.retry")) { Text("重新读取", color = PickerColors.Green) }
        TextButton(onPermission, Modifier.heightIn(min = 48.dp).testTag("picker.permission")) { Text("允许访问照片", color = PickerColors.Green) }
        TextButton(onSystem, Modifier.heightIn(min = 48.dp).testTag("picker.systemPicker")) { Text("使用系统选图", color = PickerColors.White) }
        TextButton(onSettings, Modifier.heightIn(min = 48.dp).testTag("picker.settings")) { Text("打开应用设置", color = PickerColors.Muted) }
    }
}

private data class DeviceImage(val bitmap: Bitmap? = null, val state: String = "照片加载中")

@Composable
private fun rememberDeviceImage(library: DevicePhotoLibrary, photo: DevicePhoto, large: Boolean, retry: Int = 0, onUnreadable: (DevicePhoto) -> Unit): State<DeviceImage> {
    val report by rememberUpdatedState(onUnreadable)
    return produceState(DeviceImage(), library, photo.uri, large, retry) {
        withContext(Dispatchers.Main.immediate) { value = DeviceImage() }
        try {
            val bitmap = if (large) library.preview(photo, 2048) else library.thumbnail(photo, 256)
            withContext(Dispatchers.Main.immediate) { value = DeviceImage(bitmap, if (bitmap == null) "照片加载失败" else "照片已加载") }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: SecurityException) { withContext(Dispatchers.Main.immediate) { value = DeviceImage(state = "照片加载失败"); report(photo) } }
        catch (_: Exception) { withContext(Dispatchers.Main.immediate) { value = DeviceImage(state = "照片加载失败") } }
    }
}

@Composable
private fun PickerPhotoCell(library: DevicePhotoLibrary, photo: DevicePhoto, selectedIndex: Int?, onOpen: () -> Unit, onSelect: () -> Unit, onUnreadable: (DevicePhoto) -> Unit) {
    val image by rememberDeviceImage(library, photo, false, onUnreadable = onUnreadable)
    Box(Modifier.fillMaxWidth().aspectRatio(1f).background(PickerColors.Bar).clickable(onClick = onOpen).testTag("picker.photo.${photo.id}")
        .semantics { contentDescription = photo.displayName.ifBlank { "照片" }; stateDescription = image.state }) {
        DeviceImageContent(image, Modifier.fillMaxSize())
        SelectionCircle(selectedIndex, true, onSelect, Modifier.align(Alignment.BottomEnd).testTag("picker.select.${photo.id}"))
    }
}

@Composable
private fun DeviceImageContent(image: DeviceImage, modifier: Modifier) {
    Box(modifier, contentAlignment = Alignment.Center) {
        image.bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            ?: if (image.state == "照片加载中") CircularProgressIndicator(Modifier.size(20.dp), color = PickerColors.Muted, strokeWidth = 2.dp)
            else Icon(Icons.Outlined.PhotoLibrary, "照片暂时无法预览", Modifier.size(26.dp), tint = PickerColors.Muted)
    }
}

@Composable
private fun SelectionCircle(index: Int?, enabled: Boolean, onToggle: () -> Unit, modifier: Modifier = Modifier) {
    val scale = LocalDensity.current.fontScale.coerceAtLeast(1f)
    Box(modifier.size(48.dp).clip(CircleShape).toggleable(index != null, enabled, Role.Checkbox) { onToggle() }.semantics {
        contentDescription = if (index == null) "选择照片" else "取消选择照片"
        stateDescription = if (index == null) "未选择" else "已选择，第 ${index + 1} 张"
    }, contentAlignment = Alignment.Center) {
        Box(Modifier.size(24.dp).clip(CircleShape).background(if (index != null) PickerColors.SelectedGreen else Color.Black.copy(alpha = .25f))
            .border(if (index != null) 0.dp else 1.5.dp, if (index != null) Color.Transparent else Color.White.copy(alpha = .9f), CircleShape), contentAlignment = Alignment.Center) {
            if (index != null) Text("${index + 1}", color = Color.White, fontSize = (14f / scale).sp, fontWeight = FontWeight.Medium)
        }
    }
}

@Composable
private fun PickerAlbums(library: DevicePhotoLibrary, photos: List<DevicePhoto>, selectedAlbum: String, onAlbum: (String) -> Unit, onUnreadable: (DevicePhoto) -> Unit) {
    val groups = remember(photos) { photos.groupBy { it.albumId } }
    LazyColumn(Modifier.fillMaxSize().testTag("picker.albums")) {
        item("all") { AlbumRow(library, "全部照片", photos, selectedAlbum == ALL_ALBUMS, "all", { onAlbum(ALL_ALBUMS) }, onUnreadable) }
        items(groups.entries.toList(), key = { it.key }) { entry ->
            AlbumRow(library, entry.value.first().albumName.ifBlank { "其他照片" }, entry.value, selectedAlbum == entry.key, entry.key, { onAlbum(entry.key) }, onUnreadable)
        }
    }
}

@Composable
private fun AlbumRow(library: DevicePhotoLibrary, title: String, photos: List<DevicePhoto>, selected: Boolean, tagId: String, onClick: () -> Unit, onUnreadable: (DevicePhoto) -> Unit) {
    val cover by rememberDeviceImage(library, photos.first(), false, onUnreadable = onUnreadable)
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).testTag("picker.album.$tagId").semantics { this.selected = selected }
        .padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        DeviceImageContent(cover, Modifier.size(62.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, color = PickerColors.White, fontSize = 17.sp)
            Text("${photos.size} 张", color = PickerColors.Muted, fontSize = 13.sp)
        }
        if (selected) Icon(Icons.Outlined.Check, "当前相册", tint = PickerColors.Green, modifier = Modifier.size(24.dp))
    }
    HorizontalDivider(color = PickerColors.Line, thickness = .5.dp)
}

@Composable
private fun PickerFooter(count: Int, max: Int, enabled: Boolean, onPreview: () -> Unit, onConfirm: () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth().background(PickerColors.Bar).padding(horizontal = 12.dp, vertical = 8.dp)) {
        val large = LocalDensity.current.fontScale > 1.3f || maxWidth < 330.dp
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            if (large) SelectedCount(count)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onPreview, enabled = enabled && count > 0, modifier = Modifier.heightIn(min = 48.dp).testTag("picker.preview")) {
                    Text("预览", color = if (enabled && count > 0) PickerColors.White else PickerColors.Muted.copy(alpha = .5f), fontSize = 16.sp)
                }
                if (large) Spacer(Modifier.weight(1f)) else Box(Modifier.weight(1f), contentAlignment = Alignment.Center) { SelectedCount(count) }
                Button(onConfirm, enabled = enabled && count > 0, modifier = Modifier.heightIn(min = 48.dp).testTag("picker.done"), shape = RoundedCornerShape(6.dp),
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp), colors = ButtonDefaults.buttonColors(containerColor = PickerColors.SelectedGreen, contentColor = Color.White,
                        disabledContainerColor = PickerColors.Line, disabledContentColor = PickerColors.Muted.copy(alpha = .5f))) {
                    Text("完成（$count/$max）", fontSize = 15.sp, fontWeight = FontWeight.Medium, textAlign = TextAlign.Center)
                }
            }
        }
    }
}

@Composable
private fun SelectedCount(count: Int) {
    Text("已选 $count 张", color = PickerColors.Muted, fontSize = 13.sp, modifier = Modifier.testTag("picker.count"))
}

@Composable
private fun PickerPreviewHeader(index: Int, count: Int, selection: Int?, enabled: Boolean, onClose: () -> Unit, onSelect: () -> Unit, photo: DevicePhoto?) {
    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).background(Color.Black).padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClose, Modifier.size(48.dp).testTag("picker.preview.close")) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "关闭照片预览", tint = PickerColors.White) }
        Text("${if (count == 0) 0 else index.coerceAtMost(count - 1) + 1} / $count", color = PickerColors.White, fontSize = 17.sp, textAlign = TextAlign.Center, modifier = Modifier.weight(1f).testTag("picker.preview.page"))
        if (photo != null) SelectionCircle(selection, enabled, onSelect, Modifier.testTag("picker.select.${photo.id}")) else Spacer(Modifier.size(48.dp))
    }
}

@Composable
private fun PickerPreview(library: DevicePhotoLibrary, photos: List<DevicePhoto>, initial: Int, onPage: (Int) -> Unit, onUnreadable: (DevicePhoto) -> Unit) {
    if (photos.isEmpty()) return
    val pager = rememberPagerState(initialPage = initial.coerceIn(0, photos.lastIndex), pageCount = { photos.size })
    var currentZoom by remember(pager.currentPage) { mutableFloatStateOf(1f) }
    LaunchedEffect(pager.currentPage) { onPage(pager.currentPage) }
    LaunchedEffect(photos.map { it.uri }) { if (pager.currentPage > photos.lastIndex) pager.scrollToPage(photos.lastIndex) }
    HorizontalPager(pager, Modifier.fillMaxSize(), userScrollEnabled = currentZoom <= 1.001f, key = { photos[it].uri.toString() }) { page ->
        PreviewPhoto(library, photos[page], page == pager.currentPage, { if (page == pager.currentPage) currentZoom = it }, onUnreadable)
    }
}

@Composable
private fun PreviewPhoto(library: DevicePhotoLibrary, photo: DevicePhoto, active: Boolean, onZoom: (Float) -> Unit, onUnreadable: (DevicePhoto) -> Unit) {
    var retry by remember(photo.uri) { mutableIntStateOf(0) }
    val image by rememberDeviceImage(library, photo, true, retry, onUnreadable)
    var scale by remember(photo.uri) { mutableFloatStateOf(1f) }
    var pan by remember(photo.uri) { mutableStateOf(Offset.Zero) }
    var size by remember { mutableStateOf(IntSize.Zero) }
    val bitmap by rememberUpdatedState(image.bitmap)
    val reportZoom by rememberUpdatedState(onZoom)
    LaunchedEffect(active) { if (!active) { scale = 1f; pan = Offset.Zero } }
    fun clamp(value: Offset, zoom: Float): Offset {
        val picture = bitmap ?: return Offset.Zero
        if (size.width <= 0 || size.height <= 0) return Offset.Zero
        val fit = min(size.width.toFloat() / picture.width, size.height.toFloat() / picture.height)
        val x = max(0f, (picture.width * fit * zoom - size.width) / 2)
        val y = max(0f, (picture.height * fit * zoom - size.height) / 2)
        return Offset(value.x.coerceIn(-x, x), value.y.coerceIn(-y, y))
    }
    Box(Modifier.fillMaxSize().background(Color.Black).clipToBounds().onSizeChanged { size = it }
        .testTag(if (active) "picker.previewImage" else "picker.previewImage.${photo.id}")
        .semantics {
            contentDescription = photo.displayName.ifBlank { "照片预览" }
            stateDescription = image.state
            customActions = listOf(CustomAccessibilityAction("还原照片大小") { scale = 1f; pan = Offset.Zero; reportZoom(1f); true },
                CustomAccessibilityAction("放大照片") { scale = (scale + 1f).coerceAtMost(5f); reportZoom(scale); true })
        }
        .pointerInput(photo.uri) { detectTapGestures(onDoubleTap = {
            scale = if (scale > 1.001f) 1f else 2.5f
            pan = Offset.Zero; reportZoom(scale)
        }) }
        .pointerInput(photo.uri) {
            awaitEachGesture {
                awaitFirstDown(requireUnconsumed = false)
                var dragging = false
                var accumulated = Offset.Zero
                do {
                    val event = awaitPointerEvent()
                    val multiple = event.changes.count { it.pressed } >= 2 || event.changes.count { it.previousPressed } >= 2
                    val moved = event.calculatePan()
                    if (multiple) {
                        val center = Offset(size.width / 2f, size.height / 2f)
                        val centroid = event.calculateCentroid(useCurrent = false)
                        val anchor = if (centroid.x.isFinite() && centroid.y.isFinite()) centroid else center
                        val next = (scale * event.calculateZoom()).coerceIn(1f, 5f)
                        pan = clamp(anchor - center - (anchor - center - pan) * (next / scale) + moved, next)
                        scale = next; reportZoom(scale); dragging = true
                        event.changes.forEach { it.consume() }
                    } else if (scale > 1.001f) {
                        accumulated += moved
                        if (!dragging && accumulated.getDistance() > viewConfiguration.touchSlop) dragging = true
                        if (dragging) { pan = clamp(pan + moved, scale); event.changes.forEach { it.consume() } }
                    }
                } while (event.changes.any { it.pressed })
            }
        }, contentAlignment = Alignment.Center) {
        image.bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize().graphicsLayer { scaleX = scale; scaleY = scale; translationX = pan.x; translationY = pan.y }, contentScale = ContentScale.Fit) }
            ?: if (image.state == "照片加载中") CircularProgressIndicator(Modifier.size(28.dp), color = PickerColors.Green, strokeWidth = 2.dp)
            else Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icons.Outlined.PhotoLibrary, null, Modifier.size(42.dp), tint = PickerColors.Muted)
                Text("这张照片暂时无法读取", color = PickerColors.White, fontSize = 16.sp, textAlign = TextAlign.Center)
                TextButton({ retry++ }, Modifier.heightIn(min = 48.dp).testTag("picker.preview.retry")) { Icon(Icons.Outlined.Refresh, null, tint = PickerColors.Green); Text("重新加载", color = PickerColors.Green) }
            }
    }
}
