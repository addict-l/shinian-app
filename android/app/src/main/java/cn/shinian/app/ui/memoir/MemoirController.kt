package cn.shinian.app.ui.memoir

import android.content.Context
import android.util.AtomicFile
import android.graphics.BitmapFactory
import cn.shinian.app.data.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File
import java.time.LocalDate
import java.util.UUID

@Serializable
data class PendingMemoirSave(val version: Int, val settings: MemoirSettings, val requestId: String)

@Serializable
data class LocalMemoir(
    val snapshot: MemoirSnapshot,
    val settings: MemoirSettings,
    val dirty: Boolean,
    val pending: PendingMemoirSave? = null,
)

data class BookPreview(val file: File, val revision: String, val settings: MemoirSettings, val pages: Int)

data class MemoirState(
    val snapshot: MemoirSnapshot? = null,
    val settings: MemoirSettings,
    val busy: Boolean = false,
    val label: String = "正在读取",
    val error: String? = null,
    val conflict: MemoirSnapshot? = null,
    val preview: BookPreview? = null,
    val missingPhotos: List<String> = emptyList(),
)

class MemoirController(
    private val context: Context,
    val person: Person,
    private val repository: BackendRepository,
    private val scope: CoroutineScope,
) {
    private val root = File(context.filesDir, "accounts/${repository.session.scopeKey}/memoirs/${person.id}").apply { mkdirs() }
    private val stateFile = AtomicFile(File(root, "state.json"))
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val initialSettings = MemoirSettings(title = "${person.name}的回忆录")
    private val mutable = MutableStateFlow(MemoirState(
        snapshot = MemoirSnapshot(person.id, person.name, 0, initialSettings, emptyList(), ""),
        settings = initialSettings,
    ))
    val state = mutable.asStateFlow()
    private val mutex = Mutex()
    private var dirty = false
    private var pending: PendingMemoirSave? = null
    private var scheduled: Job? = null

    init {
        if (stateFile.baseFile.exists()) {
            try {
                val value = json.decodeFromString<LocalMemoir>(stateFile.openRead().bufferedReader().use { it.readText() })
                if (value.snapshot.personId == person.id) {
                    dirty = value.dirty; pending = value.pending
                    mutable.value = MemoirState(value.snapshot, value.settings, label = if (dirty) "待同步" else "已保存")
                }
            } catch (_: Exception) { mutable.update { it.copy(error = "本机制作设置暂时无法读取，请重试。") } }
        }
    }

    val stories: List<Memory> get() = orderedStories(state.value.settings, state.value.snapshot?.stories.orEmpty())
    fun photoFile(id: String): File = File(root, "photos/$id.jpg").also { it.parentFile?.mkdirs() }

    private fun persist() {
        val current = state.value
        val snapshot = current.snapshot ?: return
        val output = stateFile.startWrite()
        try {
            output.write(json.encodeToString(LocalMemoir(snapshot, current.settings, dirty, pending)).toByteArray())
            stateFile.finishWrite(output)
        } catch (error: Exception) { stateFile.failWrite(output); throw error }
    }

    fun update(settings: MemoirSettings) {
        mutable.update { it.copy(settings = settings, label = "待同步", error = null) }
        dirty = true
        try { persist() }
        catch (_: Exception) { mutable.update { it.copy(label = "本机保存失败", error = "无法保存本机设置，请腾出空间后重试。") }; return }
        scheduled?.cancel()
        scheduled = scope.launch { delay(650); sync() }
    }

    private fun reconcile(remote: MemoirSnapshot) {
        val old = state.value.snapshot
        val sent = pending
        if (dirty && old != null) {
            if (sent != null && remote.version == sent.version + 1 && remote.settings == sent.settings) {
                pending = null; dirty = state.value.settings != sent.settings
                mutable.update { it.copy(snapshot = remote, conflict = null, label = if (dirty) "待同步" else "已保存") }
            } else if (old.version != remote.version) {
                mutable.update { it.copy(conflict = remote, label = "需要核对版本") }
                return
            } else mutable.update { it.copy(snapshot = remote) }
        } else {
            mutable.update { it.copy(snapshot = remote, settings = remote.settings, label = "已保存", conflict = null) }
        }
        persist()
    }

    fun load() = scope.launch {
        if (state.value.busy) return@launch
        mutable.update { it.copy(busy = true, error = null) }
        try { mutex.withLock { reconcile(repository.getMemoir(person.id)) }; sync() }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) { mutable.update { it.copy(error = error.message, label = if (dirty) "待同步" else "暂时离线") } }
        finally { mutable.update { it.copy(busy = false) } }
    }

    suspend fun sync(): Boolean = mutex.withLock {
        val value = state.value
        if (value.conflict != null || value.snapshot == null) return@withLock false
        if (value.settings.title.isBlank() || value.settings.title.length > 200 || value.settings.subtitle.length > 300) {
            mutable.update { it.copy(error = "请填写书名（最多 200 字），副标题最多 300 字。") }; return@withLock false
        }
        try {
            while (dirty || pending != null) {
                if (pending == null) {
                    pending = PendingMemoirSave(state.value.snapshot!!.version, state.value.settings, UUID.randomUUID().toString())
                    persist()
                }
                val sent = pending!!
                sent.settings.coverPhotos.take(coverLimit(sent.settings)).filter { it.sourceMemoryId == null }.forEach { photo ->
                    val file = photoFile(photo.id)
                    if (file.exists()) repository.uploadCover(person.id, withContext(Dispatchers.IO) { file.readBytes() }, photo.id)
                }
                val remote = repository.saveMemoir(person.id, sent.version, sent.settings, sent.requestId)
                if (remote.version != sent.version + 1 || remote.settings != sent.settings) {
                    mutable.update { it.copy(conflict = remote, label = "需要核对版本") }; return@withLock false
                }
                pending = null
                dirty = state.value.settings != sent.settings
                mutable.update { it.copy(snapshot = remote, label = if (dirty) "待同步" else "已保存", error = null) }
                persist()
            }
            true
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            val conflict = (error as? AuthException)?.statusCode == 409
            if (conflict) {
                try { reconcile(repository.getMemoir(person.id)) }
                catch (_: Exception) { mutable.update { it.copy(error = "版本核对暂时失败，本机修改已保留。") } }
            } else {
                if ((error as? AuthException)?.statusCode == 422) { pending = null; persist() }
                mutable.update { it.copy(error = error.message, label = "待同步") }
            }
            false
        }
    }

    fun chooseCloud() {
        val cloud = state.value.conflict ?: return
        dirty = false; pending = null
        mutable.update { it.copy(snapshot = cloud, settings = cloud.settings, conflict = null, error = null, label = "已保存") }
        try { persist() } catch (_: Exception) { mutable.update { it.copy(error = "无法保存本机设置，请重试。") } }
    }

    fun chooseLocal() {
        val cloud = state.value.conflict ?: return
        pending = null; dirty = true
        mutable.update { it.copy(snapshot = cloud, conflict = null, error = null) }
        try { persist() } catch (_: Exception) { return }
        scope.launch { sync() }
    }

    suspend fun importCover(data: ByteArray) {
        val id = UUID.randomUUID().toString()
        withContext(Dispatchers.IO) { storePhoto(photoFile(id), data) }
        addCover(MemoirCoverPhoto(id = id))
    }

    fun addCover(photo: MemoirCoverPhoto) {
        val settings = state.value.settings
        val limit = coverLimit(settings)
        if (limit == 0) return
        val photos = settings.coverPhotos.take(limit).filter { it.id != photo.id }.toMutableList()
        if (photos.size >= limit) photos.removeAt(photos.lastIndex)
        photos.add(photo)
        update(settings.copy(coverPhotos = photos))
    }

    suspend fun image(id: String): File {
        val file = photoFile(id)
        if (!withContext(Dispatchers.IO) { readableImage(file) }) {
            val bytes = repository.loadMedia(Media(id = id, url = "/api/v1/media/$id"))
            withContext(Dispatchers.IO) { storePhoto(file, bytes) }
        }
        return file
    }

    private fun readableImage(file: File): Boolean {
        if (!file.exists() || file.length() == 0L) return false
        return try {
            val image = BitmapFactory.decodeFile(file.absolutePath, BitmapFactory.Options().apply { inSampleSize = 16 })
            val valid = image != null && image.width > 0 && image.height > 0
            image?.recycle(); valid
        } catch (_: Exception) { false }
    }

    private fun storePhoto(file: File, bytes: ByteArray) {
        val image = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = 16 })
            ?: throw IllegalStateException("照片无法读取，请重试或重新选择。")
        image.recycle()
        val atomic = AtomicFile(file)
        val output = atomic.startWrite()
        try { output.write(bytes); atomic.finishWrite(output) }
        catch (error: Exception) { atomic.failWrite(output); throw error }
    }

    fun generate() = scope.launch {
        if (state.value.busy) return@launch
        mutable.update { it.copy(busy = true, error = null, missingPhotos = emptyList()) }
        try {
            if (!sync()) return@launch
            mutex.withLock { reconcile(repository.getMemoir(person.id)) }
            val current = state.value
            if (current.conflict != null) return@launch
            val snapshot = current.snapshot ?: return@launch
            val settings = current.settings
            val stories = orderedStories(settings, snapshot.stories)
            require(stories.isNotEmpty()) { "先保存一段回忆，就可以制作回忆录。" }
            val chosen = settings.coverPhotos.take(coverLimit(settings))
            require(settings.coverTemplate == "text" || chosen.isNotEmpty()) { "请选择封面照片，或改用纯文字封面。" }
            chosen.forEach { photo ->
                require(photo.sourceMemoryId == null || snapshot.stories.any { it.id == photo.sourceMemoryId && it.media.any { media -> media.id == photo.id } }) {
                    "封面原故事照片已被移除，请重新选择。"
                }
            }
            val required = (stories.flatMap { selectedPhotos(settings, it).map(Media::id) } + chosen.map { it.id }).distinct()
            val photos = linkedMapOf<String, File>()
            val failures = mutableListOf<String>()
            required.forEach { id -> try { photos[id] = image(id) } catch (cancelled: CancellationException) { throw cancelled } catch (_: Exception) { failures.add(id) } }
            if (failures.isNotEmpty()) {
                mutable.update { it.copy(missingPhotos = failures) }
                throw IllegalStateException("部分照片未能准备好，请重试，或取消选择失败照片。")
            }
            val output = File(root, "pdfs/${UUID.randomUUID()}/${safeFilename(settings.title)}.pdf").apply { parentFile?.mkdirs() }
            val pages = withContext(Dispatchers.Default) { MemoirPdf.render(context, snapshot, settings, photos, output) }
            require(state.value.settings == settings) { "设置已调整，请重新生成预览。" }
            val old = state.value.preview
            mutable.update { it.copy(preview = BookPreview(output, snapshot.contentRevision, settings, pages)) }
            old?.file?.takeIf { it != output }?.delete()
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) { mutable.update { it.copy(error = error.message ?: "回忆录生成失败，请重试。") } }
        finally { mutable.update { it.copy(busy = false) } }
    }

    suspend fun verifiedFile(): File? {
        val preview = state.value.preview ?: return null
        if (!sync()) return null
        return try {
            val remote = repository.getMemoir(person.id)
            reconcile(remote)
            if (state.value.conflict != null || remote.contentRevision != preview.revision || state.value.settings != preview.settings) {
                mutable.update { it.copy(error = "故事或制作设置已变化，请重新生成预览后再分享。") }; null
            } else preview.file
        } catch (error: Exception) { mutable.update { it.copy(error = error.message) }; null }
    }
}

fun coverLimit(settings: MemoirSettings): Int = when (settings.coverTemplate) { "photo" -> 1; "collage" -> 3; else -> 0 }
fun safeFilename(value: String): String = value.replace(Regex("[/\\\\:\\n\\r]"), " ").trim().take(80).ifBlank { "回忆录" }

fun storyTimeKey(story: Memory): String? = MemoirSettings.timeKey(story)

fun orderedStories(settings: MemoirSettings, stories: List<Memory>): List<Memory> = settings.ordered(stories)

fun selectedPhotos(settings: MemoirSettings, story: Memory): List<Media> {
    return settings.selectedPhotos(story)
}
