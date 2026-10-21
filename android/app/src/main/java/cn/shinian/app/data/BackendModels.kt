package cn.shinian.app.data

import java.time.LocalDate
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

@Serializable
data class Person(
    val id: String,
    val name: String,
    val relationship: String,
    val birthDate: String? = null,
    val memoryCount: Int = 0,
    val openingMessage: ChatMessage? = null,
    val hasChatHistory: Boolean? = null,
)

@Serializable
data class Media(
    val id: String,
    val url: String,
    val position: Int = 0,
    val mimeType: String = "image/jpeg",
)

/** Keep the API's five distinct information states, including unknown and withheld. */
@Serializable
data class InformationDimension(
    val status: String = "missing",
    val value: String? = null,
    @SerialName("source_message_ids") val sourceMessageIds: List<String> = emptyList(),
    @SerialName("user_edited") val userEdited: Boolean = false,
) {
    val label: String
        get() = when (status) {
            "unknown" -> "记不清"
            "withheld" -> "暂不透露"
            "missing" -> "待补充"
            else -> value.orEmpty().ifBlank { "待补充" }
        }
}

@Serializable
data class Memory(
    val id: String,
    val title: String,
    val content: String,
    val version: Int = 1,
    val personIds: List<String> = emptyList(),
    val personName: String = "家庭成员",
    val memoryDate: String? = null,
    val createdAt: String = "",
    val primaryPersonId: String? = null,
    val sourceSessionId: String? = null,
    val time: InformationDimension = InformationDimension(),
    val place: InformationDimension = InformationDimension(),
    val feeling: InformationDimension = InformationDimension(),
    val media: List<Media> = emptyList(),
    val information: JsonObject = JsonObject(emptyMap()),
    val raw: JsonObject = JsonObject(emptyMap()),
) {
    val dateLabel: String
        get() = time.value?.takeIf { it.isNotBlank() } ?: memoryDate?.let { value ->
            runCatching { LocalDate.parse(value).let { "${it.year}年${it.monthValue}月${it.dayOfMonth}日" } }.getOrDefault(value)
        } ?: when (time.status) {
            "unknown" -> "时间记不清"
            "withheld" -> "时间暂不透露"
            else -> "时间待补充"
        }
    val location: String? get() = place.value
}

@Serializable
data class MemoryEdit(
    val title: String,
    val content: String,
    val time: InformationDimension,
    val place: InformationDimension,
    val feeling: InformationDimension,
    val mediaIds: List<String>,
) {
    constructor(memory: Memory) : this(memory.title, memory.content,
        if (memory.time.status == "missing" && memory.memoryDate != null) InformationDimension("known", memory.memoryDate) else memory.time, memory.place,
        memory.feeling, memory.media.map { it.id })
    val isValid: Boolean
        get() = title.isNotBlank() && title.length <= 200 && content.isNotBlank() &&
            content.length <= 100_000 && listOf(time, place, feeling).all {
                it.status == "missing" || !it.value.isNullOrBlank()
            }
}

@Serializable
data class ChatMessage(
    val id: String,
    val role: String,
    val content: String,
    val attachments: List<Media> = emptyList(),
)

/** raw and information preserve server interview state that this client need not reinterpret. */
@Serializable
data class ChatSnapshot(
    val sessionId: String,
    val messages: List<ChatMessage> = emptyList(),
    val canGenerate: Boolean = false,
    val status: String = "active",
    val version: Int = 1,
    val information: JsonObject = JsonObject(emptyMap()),
    val lifeOverview: JsonObject? = null,
    val readiness: JsonObject? = null,
    val generationOfferMessageId: String? = null,
    val reviewRequestMessageId: String? = null,
    val currentMessageIds: List<String>? = null,
    val raw: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class Draft(
    val id: String,
    val revision: String,
    val memory: Memory,
    val manuallyEdited: Boolean = false,
    val timeReviewFrom: InformationDimension? = null,
    val hasNewNarration: Boolean = false,
    val raw: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class MemoirCoverPhoto(
    val id: String,
    val sourceMemoryId: String? = null,
    val x: Double = 0.0,
    val y: Double = 0.0,
    val zoom: Double = 1.0,
)

@Serializable
data class MemoirSettings(
    val title: String,
    val subtitle: String = "",
    val coverTemplate: String = "text",
    val coverPhotos: List<MemoirCoverPhoto> = emptyList(),
    val ordering: String = "time",
    val storyOrder: List<String> = emptyList(),
    val photoOrders: Map<String, List<String>> = emptyMap(),
    val excludedPhotoIds: List<String> = emptyList(),
    val textSize: Int = 16,
) {
    val isValid: Boolean get() = title.isNotBlank() && title.length <= 200 && subtitle.length <= 300

    /** Undated stories stay at the end; equal dates retain the original save order. */
    fun ordered(stories: List<Memory>): List<Memory> {
        val saved = stories.sortedWith(compareBy<Memory> { it.createdAt }.thenBy { it.id })
        if (ordering == "manual") {
            val byId = saved.associateBy { it.id }
            return storyOrder.mapNotNull { byId[it] } + saved.filter { it.id !in storyOrder }
        }
        return saved.sortedWith(compareBy(nullsLast()) { timeKey(it) })
    }

    fun photos(memory: Memory): List<Media> {
        val order = photoOrders[memory.id.lowercase()].orEmpty()
        val byId = memory.media.associateBy { it.id }
        return order.mapNotNull { byId[it] } + memory.media.filter { it.id !in order }
    }

    fun selectedPhotos(memory: Memory): List<Media> = photos(memory).filter { it.id !in excludedPhotoIds }

    companion object {
        fun timeKey(memory: Memory): String? {
            memory.memoryDate?.let { return it }
            if (memory.time.status == "unknown" || memory.time.status == "withheld") return null
            val value = memory.time.value ?: return null
            val match = Regex("^(\\d{4})(?:年(?:(\\d{1,2})月(?:(\\d{1,2})[日号])?|春天|夏天|秋天|冬天|春季|夏季|秋季|冬季)?|-(\\d{2})(?:-(\\d{2}))?)?$")
                .matchEntire(value) ?: return null
            val year = match.groupValues[1].toIntOrNull() ?: return null
            val month = match.groupValues[2].toIntOrNull() ?: match.groupValues[4].toIntOrNull() ?: 1
            val day = match.groupValues[3].toIntOrNull() ?: match.groupValues[5].toIntOrNull() ?: 1
            return runCatching { LocalDate.of(year, month, day).takeIf { year > 0 }?.toString() }.getOrNull()
        }
    }
}

@Serializable
data class MemoirSnapshot(
    val personId: String,
    val personName: String,
    val version: Int,
    val settings: MemoirSettings,
    val stories: List<Memory>,
    val contentRevision: String,
    val raw: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class TimePreviewInput(
    val title: String,
    @SerialName("summary") val content: String,
    @SerialName("old_time") val oldTime: InformationDimension,
    @SerialName("new_time") val newTime: InformationDimension,
) {
    fun fields(): JsonObject = Json.parseToJsonElement(Json.encodeToString(this)).jsonObject
}

@Serializable
data class TimeSuggestion(
    val id: String,
    val field: String,
    val start: Int,
    val length: Int,
    val before: String,
    val after: String? = null,
    val context: String,
    val ambiguous: Boolean,
    val reason: String,
)

@Serializable
data class TimePreview(
    val snapshot: String,
    val suggestions: List<TimeSuggestion>,
    val message: String,
) {
    /** Kotlin String offsets are UTF-16, matching the server contract and NSString. */
    fun applying(selected: Set<String>, input: TimePreviewInput): Pair<String, String> {
        fun apply(field: String, source: String): String {
            var result = source
            var boundary = source.length
            for (item in suggestions.filter { it.field == field && it.id in selected }.sortedByDescending { it.start }) {
                val end = item.start.toLong() + item.length
                if (item.after == null || item.start < 0 || item.length <= 0 || end > boundary ||
                    !source.isUtf16Boundary(item.start) || !source.isUtf16Boundary(end.toInt()) ||
                    source.substring(item.start, end.toInt()) != item.before
                ) throw AuthException(AuthErrorKind.Rejected, "文字已变化，请重新核对时间。")
                result = result.replaceRange(item.start, end.toInt(), item.after)
                boundary = item.start
            }
            return result
        }
        val title = apply("title", input.title)
        val content = apply("summary", input.content)
        if (title.length > 200 || content.length > 100_000) {
            throw AuthException(AuthErrorKind.Rejected, "修改后文字过长，请减少内容再应用。")
        }
        return title to content
    }

    private fun String.isUtf16Boundary(index: Int): Boolean =
        index in 0..length && !(index > 0 && index < length && this[index].isLowSurrogate() && this[index - 1].isHighSurrogate())
}
