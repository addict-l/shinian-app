package cn.shinian.app.ui.chat

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import cn.shinian.app.data.AuthException
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.ChatMessage
import cn.shinian.app.data.ChatSnapshot
import cn.shinian.app.data.Draft
import cn.shinian.app.data.InformationDimension
import cn.shinian.app.data.Memory
import cn.shinian.app.data.Person
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

internal fun JsonObject?.text(key: String): String? = (this?.get(key) as? JsonPrimitive)?.contentOrNull
internal fun JsonObject?.number(key: String, fallback: Int = 0): Int = (this?.get(key) as? JsonPrimitive)?.intOrNull ?: fallback
internal fun JsonObject?.flag(key: String): Boolean = (this?.get(key) as? JsonPrimitive)?.booleanOrNull == true
internal fun JsonObject?.objectAt(key: String): JsonObject? = this?.get(key) as? JsonObject
internal fun JsonObject?.objects(key: String): List<JsonObject> = (this?.get(key) as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()

internal fun dimensionJson(value: InformationDimension) = buildJsonObject {
    put("status", value.status)
    put("value", value.value?.let(::JsonPrimitive) ?: JsonNull)
    put("source_message_ids", JsonArray(value.sourceMessageIds.map(::JsonPrimitive)))
    put("user_edited", value.userEdited)
}

/** Mirrors the Swift send contract: persist identity, upload in order, then send exactly once. */
internal class ChatController(context: Context, val person: Person, private val repository: BackendRepository) : ViewModel() {
    private val store = ChatDraftStore(context.applicationContext, repository.session.scopeKey, person.id)
    private val writes = Mutex()
    private var persistJob: Job? = null
    private var unreadableLocal = false
    private var hydrated = false
    private var finishedLocal = false
    private var startId = UUID.randomUUID().toString()
    private var sessionId: String? = null
    private var openedReviewRequestId: String? = null
    var cacheInvalidated by mutableStateOf(false); private set
    var snapshot by mutableStateOf<ChatSnapshot?>(null); private set
    var input by mutableStateOf(""); private set
    var lifeInput by mutableStateOf(""); private set
    var pending by mutableStateOf<PendingNarration?>(null); private set
    var pendingLife by mutableStateOf<LifeCommand?>(null); private set
    var photos by mutableStateOf<List<SelectedPhoto>>(emptyList()); private set
    var busy by mutableStateOf(true); private set
    var progress by mutableStateOf("正在打开故事…"); private set
    var error by mutableStateOf<String?>(null)
    var storageError by mutableStateOf<String?>(null); private set
    var showLife by mutableStateOf(false)
    var review by mutableStateOf<Draft?>(null); private set
    var edits by mutableStateOf<DraftEdits?>(null); private set
    var latestDraft by mutableStateOf<Draft?>(null); private set
    var timePreview by mutableStateOf<JsonObject?>(null); private set
    private var timeCapture: DraftEdits? = null
    var timePreviewOpen by mutableStateOf(false); private set
    var savedMemory by mutableStateOf<Memory?>(null); private set

    val overview get() = snapshot?.lifeOverview
    val lifeStatus get() = overview.text("status").orEmpty()
    val collectingLife get() = lifeStatus == "collecting"
    val needsLife get() = overview.flag("required") && !snapshot?.information.objectAt("guided_interview").flag("module_selected")
    val completed get() = snapshot?.status == "completed"
    val messages: List<ChatMessage> get() {
        val saved = snapshot?.messages.orEmpty().ifEmpty {
            if (person.hasChatHistory == false) listOfNotNull(person.openingMessage) else emptyList()
        }
        val local = pending
        return if (local == null || saved.any { it.id == local.id }) saved
            else saved + ChatMessage(local.id, "user", local.text)
    }
    val mayGenerate get() = snapshot?.canGenerate == true && pending == null && photos.isEmpty() && input.isBlank() && !busy && !completed
    val generationOffered get() = mayGenerate && snapshot?.generationOfferMessageId != null &&
        messages.lastOrNull()?.id == snapshot?.generationOfferMessageId && messages.lastOrNull()?.role != "user"

    init {
        val seen = ChatCacheInvalidations.latest.value?.sequence ?: 0L
        viewModelScope.launch {
            ChatCacheInvalidations.latest.collect { event ->
                if (event != null && event.sequence > seen && event.scope == repository.session.scopeKey) {
                    cacheInvalidated = true
                    snapshot = null; review = null; latestDraft = null; timePreviewOpen = false
                }
            }
        }
        viewModelScope.launch { open() }
    }

    /** Activity-scoped ViewModels must re-read server history on every navigation entry. */
    fun enter() {
        if (!busy && hydrated) {
            savedMemory = null
            viewModelScope.launch { open() }
        }
    }

    fun updateInput(value: String) { input = value; persistLater() }
    fun updateLifeInput(value: String) { lifeInput = value; persistLater() }

    private fun local() = LocalChatDraft(person.id, sessionId, startId, input, pending,
        photos.map { StoredPhoto(it.id, it.attachment) }, snapshot, lifeInput, pendingLife, review, edits,
        openedReviewRequestId)

    private suspend fun persist(): Boolean {
        if (!hydrated || unreadableLocal || finishedLocal || cacheInvalidated) return !unreadableLocal
        val value = local()
        val images = photos.toList()
        return try {
            writes.withLock { withContext(Dispatchers.IO) { store.save(value, images) } }
            storageError = null
            true
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) {
            storageError = "未能保存本机待发送内容，请检查设备存储空间并重试；当前内容仍在此页面。"
            false
        }
    }

    private fun persistLater() {
        if (!hydrated) return
        persistJob?.cancel()
        persistJob = viewModelScope.launch { delay(250); persist() }
    }

    fun pause() { persistJob?.cancel(); viewModelScope.launch { persist() } }
    fun retryStorage() { viewModelScope.launch { if (unreadableLocal) open() else persist() } }
    fun retryOpen() { if (!busy) viewModelScope.launch { open() } }

    private suspend fun open() {
        busy = true; progress = "正在打开故事…"; error = null
        try {
            if (!hydrated || unreadableLocal || cacheInvalidated) {
                val loaded = try { withContext(Dispatchers.IO) { store.load() } }
                catch (_: Exception) {
                    unreadableLocal = true
                    storageError = "本机聊天或照片暂时无法读取，原文件仍保留。请稍后重试。"
                    return
                }
                loaded?.let { (draft, selected) ->
                    sessionId = draft.sessionId; startId = draft.startRequestId
                    input = draft.restoredInput
                    pending = draft.pending; photos = selected; snapshot = draft.snapshot
                    lifeInput = draft.lifeInput; pendingLife = draft.pendingLife; review = draft.review; edits = draft.edits
                    openedReviewRequestId = draft.openedReviewRequestId
                }
                hydrated = true; unreadableLocal = false; cacheInvalidated = false; storageError = null
            }
            if (!persist()) return
            val value = sessionId?.let {
                try { repository.chatState(it) }
                catch (failure: AuthException) {
                    if (failure.statusCode != 404) throw failure
                    sessionId = null; startId = UUID.randomUUID().toString()
                    photos = photos.map { photo -> photo.copy(attachment = null, status = "selected") }
                    if (photos.isNotEmpty()) pending = pending?.copy(attachmentIds = emptyList())
                    if (!persist()) return
                    repository.startConversation(person.id, startId)
                }
            }
                ?: repository.startConversation(person.id, startId)
            accept(value)
            if (value.status == "completed") beginNextInternal()
            else if (value.messages.isEmpty() && value.lifeOverview == null) {
                accept(repository.startConversation(person.id, startId))
            }
            if (review != null) {
                try {
                    val remote = repository.getDraft(review!!.id)
                    if (edits != null && remote.revision != review?.revision) latestDraft = remote
                    else review = remote
                }
                catch (failure: Exception) { error = failure.message ?: "读取草稿失败，请重试。" }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { error = failure.message ?: "暂时无法打开故事，请重试。" }
        finally { busy = false }
        if (pendingLife != null) performLifeInternal(pendingLife!!)
        else autoReview()
    }

    private suspend fun accept(value: ChatSnapshot) {
        snapshot = value; sessionId = value.sessionId
        val ids = value.currentMessageIds ?: value.messages.map { it.id }
        pending?.let { request ->
            val index = ids.indexOf(request.id)
            if (index >= 0 && index + 1 < ids.size) clearPending()
        }
        val last = value.messages.lastOrNull()
        if (pending == null && last?.role == "user" && last.id in ids && value.status != "completed") {
            pending = PendingNarration(last.id, last.content, last.attachments.map { it.id })
            error = "上次讲述已保存，回复尚未完成。点击重试继续，不会重复保存。"
        }
        value.lifeOverview.objectAt("pending_action")?.let { command ->
            command.text("client_request_id")?.let { id ->
                pendingLife = LifeCommand(command.text("action") ?: "answer", command.number("expected_version"), id,
                    command.text("text").orEmpty(), command.text("topic_id"))
            }
        }
        persist()
    }

    private fun clearPending() { pending = null; photos = emptyList() }

    fun appendPhotos(values: List<ByteArray>) {
        if (busy || pending != null) { error = "请先完成当前消息的发送或重试。"; return }
        if (photos.size + values.size > 9) { error = "每条消息最多 9 张照片，更多照片可以分多条发送。"; return }
        if (values.any { it.isEmpty() || it.size > 8 * 1024 * 1024 }) { error = "每张照片压缩后不能超过 8 MB。"; return }
        photos = photos + values.map { SelectedPhoto(UUID.randomUUID().toString(), it) }
        pause()
    }

    fun removePhoto(id: String) {
        if (busy || pending != null) return
        val photo = photos.firstOrNull { it.id == id } ?: return
        viewModelScope.launch {
            busy = true; progress = "正在移除未发送的照片…"; error = null
            try {
                if (photo.attachment != null && sessionId != null) repository.removeChatPhoto(sessionId!!, photo.attachment.id)
                photos = photos.filterNot { it.id == id }; persist()
            } catch (failure: Exception) { error = failure.message ?: "移除照片失败，请重试。" }
            finally { busy = false }
        }
    }

    fun send() {
        if (busy || unreadableLocal) return
        viewModelScope.launch {
            val text = pending?.text ?: input.trim()
            val retrying = pending != null
            if (completed) { error = "这段回忆已保存，请开始新的故事。"; return@launch }
            if (text.length > 12_000) { error = "单条文字最多 12000 字，请分多条发送。"; return@launch }
            if (text.isBlank() && photos.isEmpty() && pending == null) return@launch
            if (pending == null) pending = PendingNarration(UUID.randomUUID().toString(), text)
            if (!persist()) return@launch
            if (!retrying || input.trim() == text) input = ""
            busy = true; error = null
            try {
                if (sessionId == null) accept(repository.startConversation(person.id, startId))
                val sid = sessionId ?: throw IllegalStateException("聊天会话尚未建立。")
                for (index in photos.indices) {
                    val photo = photos[index]
                    if (photo.attachment != null) continue
                    progress = "正在上传照片 ${index + 1}/${photos.size}…"
                    photos = photos.toMutableList().also { it[index] = photo.copy(status = "uploading") }
                    try {
                        val media = repository.uploadChatPhoto(sid, photo.data, photo.id)
                        photos = photos.toMutableList().also { it[index] = photo.copy(attachment = media, status = "uploaded") }
                        if (!persist()) return@launch
                    } catch (failure: Exception) {
                        photos = photos.toMutableList().also { it[index] = photo.copy(status = "failed") }; throw failure
                    }
                }
                if (photos.isNotEmpty()) pending = pending?.copy(attachmentIds = photos.mapNotNull { it.attachment?.id })
                if (!persist()) return@launch
                val request = pending ?: return@launch
                progress = if (request.text.isBlank()) "正在保存照片消息…" else "正在倾听与整理…"
                val value = repository.sendMessage(sid, request.text, request.attachmentIds, request.id)
                clearPending(); accept(value)
            } catch (cancelled: CancellationException) { persist(); throw cancelled }
            catch (failure: Exception) {
                error = failure.message ?: "发送未完成，请重试这条讲述。"
                sessionId?.let { sid -> runCatching { repository.chatState(sid) }.getOrNull()?.let { accept(it) } }
                if (pending == null) error = null
                else if (failure is AuthException && (failure.statusCode ?: 0) in 400..499 && failure.statusCode != 408 && failure.statusCode != 429) {
                    pending = null
                    input = listOf(text, input).filter { it.isNotBlank() }.distinct().joinToString("\n")
                }
                persist()
            } finally { busy = false }
            autoReview()
        }
    }

    fun performLife(action: String, text: String = "", topic: String? = null) {
        if (busy || unreadableLocal) return
        val command = pendingLife ?: LifeCommand(action, overview.number("version"), UUID.randomUUID().toString(), text, topic)
        viewModelScope.launch { performLifeInternal(command) }
    }

    private suspend fun performLifeInternal(command: LifeCommand) {
        if (busy) return
        pendingLife = command
        if (!persist()) return
        busy = true; progress = "正在记录与核对…"; error = null
        try {
            val sid = sessionId ?: return
            val value = repository.lifeAction(sid, command.action, command.version, command.requestId, command.text, command.topicId)
            pendingLife = null
            if (command.action == "answer") lifeInput = ""
            accept(value)
            if (value.reviewRequestMessageId != null) showLife = false
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            error = failure.message ?: "本次操作未完成，请重试。"
            if (failure is AuthException && failure.statusCode == 409) pendingLife = null
            sessionId?.let { runCatching { repository.chatState(it) }.getOrNull()?.let { accept(it) } }
            persist()
        } finally { busy = false }
        autoReview()
    }

    fun chooseModule(module: String) {
        if (busy || pendingLife != null) return
        viewModelScope.launch {
            busy = true; error = null; progress = "正在打开这段日子…"
            try {
                val value = repository.selectInterview(sessionId ?: return@launch, module, snapshot?.version ?: 1)
                accept(value); showLife = false
            } catch (failure: Exception) {
                error = failure.message ?: "板块暂时无法打开，请重试。"
                sessionId?.let { runCatching { repository.chatState(it) }.getOrNull()?.let { accept(it) } }
                val guided = snapshot?.information.objectAt("guided_interview")
                if (guided.flag("module_selected") && guided.text("module") == module) { showLife = false; error = null }
            } finally { busy = false }
        }
    }

    fun pauseLife(after: () -> Unit) {
        if (busy) return
        viewModelScope.launch {
            if (collectingLife && pendingLife == null) {
                performLifeInternal(LifeCommand("pause", overview.number("version"), UUID.randomUUID().toString()))
            }
            persist(); after()
        }
    }

    private suspend fun autoReview() {
        val request = snapshot?.reviewRequestMessageId ?: return
        if (request == openedReviewRequestId || !mayGenerate || messages.lastOrNull()?.id != request || review != null) return
        generateInternal()
        if (review != null) { openedReviewRequestId = request; persist() }
    }

    fun generate() { if (mayGenerate && review == null) viewModelScope.launch { generateInternal() } }
    private suspend fun generateInternal() {
        val sid = sessionId ?: return
        if (!mayGenerate) return
        busy = true; error = null; progress = "正在整理回忆草稿…"
        try { review = repository.generateDraft(sid); persist() }
        catch (failure: Exception) { error = failure.message ?: "草稿暂时无法整理，请重试。" }
        finally { busy = false }
    }

    fun closeReview() { if (!busy) { review = null; latestDraft = null; error = null; pause() } }
    fun beginEdit() {
        val draft = review ?: return
        if (edits?.draftId != draft.id) edits = DraftEdits(draft.id, draft.memory.title, draft.memory.content,
            draft.memory.time, draft.timeReviewFrom ?: draft.memory.time)
        error = null; pause()
    }
    fun changeEdits(value: DraftEdits) { edits = value; persistLater() }
    fun cancelEdit() { if (!busy) { edits = null; latestDraft = null; error = null; timePreviewOpen = false; pause() } }

    fun saveEdits(overwriteLatest: Boolean = false) {
        val draft = if (overwriteLatest) latestDraft else review
        val value = edits
        if (busy || draft == null || value?.valid != true || value.draftId != draft.id) return
        viewModelScope.launch {
            busy = true; error = null; progress = "正在保留修改…"
            try {
                review = repository.editDraft(draft, value.title, value.content, value.time)
                edits = null; latestDraft = null; persist()
            } catch (failure: Exception) { conflict(failure) }
            finally { busy = false }
        }
    }

    fun restorePreviousEdits() {
        val draft = review ?: return
        val old = edits ?: return
        if (busy) return
        edits = old.copy(draftId = draft.id, anchor = draft.timeReviewFrom ?: draft.memory.time)
        error = null; pause()
    }

    private suspend fun conflict(failure: Exception) {
        error = failure.message ?: "草稿操作失败，请重试。"
        if (failure is AuthException && failure.statusCode == 409) {
            review?.let { draft ->
                try { latestDraft = repository.getDraft(draft.id) }
                catch (_: Exception) { error = "读取最新草稿失败，本机修改仍保留，请重试。" }
            }
        }
    }

    fun readLatestDraft() { latestDraft?.let { review = it; edits = null; latestDraft = null; error = null; pause() } }
    fun regenerate() {
        val draft = review ?: return
        if (busy) return
        viewModelScope.launch {
            busy = true; error = null; progress = "正在重新整理草稿…"
            try {
                review = repository.regenerateDraft(draft, true); edits = null; latestDraft = null
                if (review?.timeReviewFrom != null) beginEdit()
                persist()
            } catch (failure: Exception) { conflict(failure) }
            finally { busy = false }
        }
    }

    fun previewTime() {
        val draft = review ?: return
        val value = edits ?: return
        if (busy || !value.valid) return
        timePreviewOpen = true; timePreview = null; timeCapture = value
        viewModelScope.launch {
            busy = true; error = null; progress = "正在核对时间…"
            try {
                timePreview = repository.previewDraftTime(latestDraft ?: draft, buildJsonObject {
                    put("title", value.title); put("summary", value.content)
                    put("old_time", dimensionJson(value.anchor)); put("new_time", dimensionJson(value.time))
                })
            } catch (failure: Exception) { error = failure.message ?: "时间暂时无法核对，请重试。" }
            finally { busy = false }
        }
    }

    fun closeTimePreview() { if (!busy) { timePreviewOpen = false; timePreview = null; error = null } }
    fun applyTime(selected: Set<String>) {
        val captured = timeCapture ?: return
        val preview = timePreview ?: return
        if (edits != captured) { error = "编辑内容已变化，请重新核对时间。"; return }
        try {
            edits = applyDraftTime(captured, preview, selected)
            timePreviewOpen = false; timePreview = null; error = null; pause()
        } catch (failure: Exception) { error = failure.message ?: "文字已变化，请重新核对时间。" }
    }

    fun save(onSuccess: () -> Unit, continueAfterSave: Boolean = false) {
        val draft = review ?: return
        if (busy || draft.hasNewNarration) return
        viewModelScope.launch {
            busy = true; error = null; progress = "正在珍藏这段回忆…"
            try {
                savedMemory = repository.saveDraft(draft)
                finishedLocal = true
                review = null; edits = null; pendingLife = null; input = ""; lifeInput = ""; clearPending()
                persistJob?.cancel()
                try { writes.withLock { withContext(Dispatchers.IO) { store.remove() } }; storageError = null }
                catch (_: Exception) { storageError = "回忆已保存，但本机缓存清理失败。" }
                if (continueAfterSave) {
                    savedMemory = null
                    snapshot = snapshot?.copy(status = "completed", canGenerate = false)
                    progress = "正在打开新的故事…"
                    try { beginNextInternal() }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { error = "回忆已保存，新的故事暂时无法打开，请点击继续聊天重试。" }
                }
                onSuccess()
            } catch (failure: Exception) { conflict(failure) }
            finally { busy = false }
        }
    }

    fun continueStory() {
        if (busy) return
        viewModelScope.launch {
            busy = true; progress = "正在打开新的故事…"; error = null
            try { savedMemory = null; beginNextInternal() }
            catch (failure: Exception) { error = failure.message ?: "新的故事暂时无法打开，请重试。" }
            finally { busy = false }
        }
    }

    private suspend fun beginNextInternal() {
        finishedLocal = false
        val retained = listOf(input, pending?.text.orEmpty()).filter { it.isNotBlank() }.distinct().joinToString("\n")
        val retainedPhotos = photos.map { it.copy(id = UUID.randomUUID().toString(), attachment = null, status = "selected") }
        startId = UUID.randomUUID().toString()
        if (!persist()) return
        val value = repository.startConversation(person.id, startId)
        if (value.status == "completed") return
        clearPending(); photos = retainedPhotos; input = retained; review = null; edits = null
        openedReviewRequestId = null; accept(value)
    }
}
