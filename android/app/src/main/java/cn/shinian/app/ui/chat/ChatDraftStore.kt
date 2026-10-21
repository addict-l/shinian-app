package cn.shinian.app.ui.chat

import android.content.Context
import android.util.AtomicFile
import cn.shinian.app.data.ChatSnapshot
import cn.shinian.app.data.Draft
import cn.shinian.app.data.InformationDimension
import cn.shinian.app.data.Media
import java.io.File
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
internal data class PendingNarration(val id: String, val text: String, val attachmentIds: List<String> = emptyList())

@Serializable
internal data class StoredPhoto(val id: String, val attachment: Media? = null)

internal data class SelectedPhoto(val id: String, val data: ByteArray, val attachment: Media? = null, val status: String = "selected")

@Serializable
internal data class LifeCommand(
    val action: String,
    val version: Int,
    val requestId: String,
    val text: String = "",
    val topicId: String? = null,
)

@Serializable
internal data class DraftEdits(
    val draftId: String,
    val title: String,
    val content: String,
    val time: InformationDimension,
    val anchor: InformationDimension,
) {
    val valid get() = title.isNotBlank() && title.length <= 200 && content.isNotBlank() &&
        content.length <= 100_000 && (time.status == "missing" || !time.value.isNullOrBlank())
}

@Serializable
internal data class LocalChatDraft(
    val personId: String,
    val sessionId: String? = null,
    val startRequestId: String,
    val input: String = "",
    val pending: PendingNarration? = null,
    val photos: List<StoredPhoto> = emptyList(),
    val snapshot: ChatSnapshot? = null,
    val lifeInput: String = "",
    val pendingLife: LifeCommand? = null,
    val review: Draft? = null,
    val edits: DraftEdits? = null,
    val openedReviewRequestId: String? = null,
    val updatedAt: Long = System.currentTimeMillis(),
) {
    val restoredInput: String get() = if (pending != null && input.trim() == pending.text) "" else input
}

internal fun LocalChatDraft.withoutDownloadedHistory(deletedSession: String?): LocalChatDraft {
    val deleted = deletedSession != null && sessionId == deletedSession
    return copy(snapshot = null, review = null,
        sessionId = if (deleted) null else sessionId,
        startRequestId = if (deleted) UUID.randomUUID().toString() else startRequestId,
        photos = if (deleted) photos.map { it.copy(attachment = null) } else photos,
        pending = if (deleted && photos.isNotEmpty()) pending?.copy(attachmentIds = emptyList()) else pending)
}

/** App-private, excluded from backup, isolated by server/account/family and person. No token is written. */
internal class ChatDraftStore(context: Context, scope: String, personId: String) {
    private val scopeKey = scope
    private val directory = File(File(File(context.noBackupFilesDir, "PendingStories"), scope), personId)
    private val gate = ChatDraftLocks.forPath(directory.absolutePath)
    private var loadedEpoch = 0L
    private val manifest get() = AtomicFile(File(directory, "draft.json"))
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    fun load(): Pair<LocalChatDraft, List<SelectedPhoto>>? = synchronized(gate) {
        loadedEpoch = ChatCacheInvalidations.current(scopeKey)?.sequence ?: 0L
        if (!manifest.baseFile.exists() && !File(directory, "draft.json.bak").exists()) return@synchronized null
        val draft = manifest.openRead().use { json.decodeFromString<LocalChatDraft>(it.readBytes().decodeToString()) }
        val photos = draft.photos.map { stored ->
            val data = File(directory, "${stored.id}.jpg").readBytes()
            check(data.isNotEmpty()) { "本机照片暂时无法读取，原文件仍保留，请重试读取。" }
            SelectedPhoto(stored.id, data, stored.attachment, if (stored.attachment == null) "selected" else "uploaded")
        }
        draft to photos
    }

    fun save(original: LocalChatDraft, photos: List<SelectedPhoto>) = synchronized(gate) {
        // A disk write captured before invalidation must never put deleted history back.
        val event = ChatCacheInvalidations.current(scopeKey)
        val draft = if (event != null && event.sequence > loadedEpoch) original.withoutDownloadedHistory(event.sourceSessionId) else original
        check(directory.exists() || directory.mkdirs()) { "未能建立本机草稿目录。" }
        photos.forEach { photo ->
            val path = File(directory, "${photo.id}.jpg")
            if (!path.exists()) {
                val atomic = AtomicFile(path)
                val output = atomic.startWrite()
                try { output.write(photo.data); atomic.finishWrite(output) }
                catch (error: Throwable) { atomic.failWrite(output); throw error }
            }
        }
        val output = manifest.startWrite()
        try { output.write(json.encodeToString(draft).toByteArray()); manifest.finishWrite(output) }
        catch (error: Throwable) { manifest.failWrite(output); throw error }
        // Delete orphaned files only after the manifest references a complete durable set.
        val retained = draft.photos.map { "${it.id}.jpg" }.toSet()
        directory.listFiles()?.filter { it.extension == "jpg" && it.name !in retained }?.forEach { it.delete() }
    }

    fun remove() = synchronized(gate) { check(!directory.exists() || directory.deleteRecursively()) { "回忆已保存，但本机缓存清理失败。" } }

    /** A memory's source session can be deleted; narration/photo identities remain stable. */
    fun invalidateHistory(deletedSession: String?) = synchronized(gate) {
        if (!manifest.baseFile.exists() && !File(directory, "draft.json.bak").exists()) return@synchronized
        val value = manifest.openRead().use { json.decodeFromString<LocalChatDraft>(it.readBytes().decodeToString()) }
        save(value.withoutDownloadedHistory(deletedSession), emptyList())
    }
}

private object ChatDraftLocks {
    private val locks = ConcurrentHashMap<String, Any>()
    fun forPath(path: String): Any = locks.getOrPut(path) { Any() }
}

internal data class ChatCacheInvalidation(val scope: String, val sequence: Long, val sourceSessionId: String?)
internal object ChatCacheInvalidations {
    private val sequence = AtomicLong()
    private val events = ConcurrentHashMap<String, ChatCacheInvalidation>()
    val latest = MutableStateFlow<ChatCacheInvalidation?>(null)
    fun current(scope: String) = events[scope]
    fun notify(scope: String, sourceSessionId: String?) {
        val event = ChatCacheInvalidation(scope, sequence.incrementAndGet(), sourceSessionId)
        events[scope] = event
        latest.value = event
    }
}

/** Call after editing a memory; pass its sourceSessionId after deletion. Await before navigating. */
suspend fun invalidateChatAfterMemoryChange(context: Context, scopeKey: String, sourceSessionId: String? = null) {
    ChatCacheInvalidations.notify(scopeKey, sourceSessionId)
    try {
        withContext(Dispatchers.IO) {
            val root = File(File(context.noBackupFilesDir, "PendingStories"), scopeKey)
            var failed: Exception? = null
            root.listFiles()?.filter { it.isDirectory }?.forEach { directory ->
                try { ChatDraftStore(context, scopeKey, directory.name).invalidateHistory(sourceSessionId) }
                catch (error: Exception) { failed = error }
            }
            failed?.let { throw it }
        }
    } finally { ChatCacheInvalidations.notify(scopeKey, sourceSessionId) }
}
