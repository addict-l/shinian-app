package cn.shinian.app.data

import cn.shinian.app.BuildConfig
import java.io.IOException
import java.io.InterruptedIOException
import java.time.LocalDate
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

/** One repository belongs to one immutable account session, including every image request. */
class BackendRepository(
    val session: AuthSession,
    httpClient: OkHttpClient = OkHttpClient(),
    private val onUnauthorized: () -> Unit = {},
) {
    private val base: HttpUrl = validateBase(session.server)
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val client = httpClient.newBuilder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .callTimeout(120, TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build()
    private val interviewClient = client.newBuilder()
        .readTimeout(450, TimeUnit.SECONDS).callTimeout(450, TimeUnit.SECONDS).build()
    private val calls = ConcurrentHashMap.newKeySet<Call>()
    @Volatile private var active = true
    @Volatile private var verifiedFamily: String? = null
    @Volatile private var knownMembers: List<Person> = emptyList()

    fun invalidate() {
        active = false
        calls.forEach { it.cancel() }
        calls.clear()
    }

    private suspend fun family(): String {
        verifiedFamily?.let { return it }
        val identity = objectResponse("api/v1/auth/me")
        val family = identity.requiredText("family_id")
        if (!family.equals(session.familyId, ignoreCase = true) ||
            !identity.requiredText("account_id").equals(session.accountId, ignoreCase = true)
        ) throw AuthException(AuthErrorKind.Authentication, "登录身份不匹配，请重新登录。")
        return id(family).also { verifiedFamily = it }
    }

    suspend fun members(): List<Person> {
        val familyId = family()
        val people = arrayResponse("api/v1/family-members/", query = mapOf("family_id" to familyId))
            .map { person(it.jsonObject) }
        val memories = arrayResponse("api/v1/memories/", query = mapOf("family_id" to familyId))
        knownMembers = people.map { person ->
            person.copy(memoryCount = memories.count { person.id in it.jsonObject.strings("person_ids") })
        }
        return knownMembers
    }

    suspend fun addMember(name: String, relationship: String, birthDate: String, requestId: String): Person {
        val birthday = runCatching { LocalDate.parse(birthDate) }.getOrNull()
        if (name.isBlank() || relationship.isBlank() || birthday == null || birthday.isAfter(LocalDate.now())) {
            throw AuthException(AuthErrorKind.Rejected, "请完整填写人物信息，生日不能晚于今天。")
        }
        val result = person(objectResponse("api/v1/family-members/", "POST", buildJsonObject {
            put("family_id", family()); put("client_request_id", id(requestId))
            put("name", name.trim()); put("relationship", relationship.trim()); put("birth_date", birthDate)
        }))
        knownMembers = knownMembers.filterNot { it.id == result.id } + result
        return result
    }

    suspend fun deleteMember(id: String) {
        request("api/v1/family-members/${id(id)}", "DELETE")
        knownMembers = knownMembers.filterNot { it.id == id }
    }

    suspend fun memories(): List<Memory> {
        if (knownMembers.isEmpty()) members()
        return arrayResponse("api/v1/memories/", query = mapOf("family_id" to family()))
            .map { memory(it.jsonObject) }
    }

    suspend fun getMemory(id: String): Memory = memory(objectResponse("api/v1/memories/${id(id)}"))

    suspend fun updateMemory(memory: Memory, edit: MemoryEdit): Memory {
        if (!edit.isValid) throw AuthException(AuthErrorKind.Rejected, "请检查标题、正文和信息说明。")
        val date = edit.time.value?.takeIf { edit.time.status == "known" }
            ?.takeIf { value -> runCatching { LocalDate.parse(value).toString() == value }.getOrDefault(false) }
        return memory(objectResponse("api/v1/memories/${id(memory.id)}", "PATCH", buildJsonObject {
            put("family_id", family()); put("version", memory.version)
            put("title", edit.title); put("summary", edit.content)
            put("time", dimensionJson(edit.time)); put("place", dimensionJson(edit.place))
            put("feeling", dimensionJson(edit.feeling)); put("memory_date", date?.let(::JsonPrimitive) ?: JsonNull)
            put("media_ids", stringArray(edit.mediaIds.map(::id)))
        }))
    }

    suspend fun deleteMemory(memory: Memory) {
        request("api/v1/memories/${id(memory.id)}", "DELETE",
            query = mapOf("family_id" to family(), "version" to memory.version.toString()))
    }

    suspend fun uploadMemoryPhoto(id: String, data: ByteArray, requestId: String): Media =
        upload("api/v1/memories/${id(id)}/media", data, requestId, mapOf("family_id" to family()))

    suspend fun discardMemoryPhoto(id: String, photoId: String) {
        request("api/v1/memories/${id(id)}/media/${id(photoId)}", "DELETE",
            query = mapOf("family_id" to family()))
    }

    suspend fun startConversation(personId: String, requestId: String): ChatSnapshot {
        // The backend opens this person's current segment atomically; it has no request body.
        id(requestId)
        return chat(objectResponse("api/v1/chat/members/${id(personId)}/conversation", "POST",
            query = mapOf("family_id" to family())))
    }

    suspend fun chatState(sessionId: String): ChatSnapshot =
        chat(objectResponse("api/v1/chat/sessions/${id(sessionId)}/conversation"))

    suspend fun sendMessage(sessionId: String, text: String, attachmentIds: List<String>, requestId: String): ChatSnapshot {
        if (text.length > 12_000 || attachmentIds.size > 9 || (text.isBlank() && attachmentIds.isEmpty())) {
            throw AuthException(AuthErrorKind.Rejected, "每条消息最多 12000 字和 9 张照片，请检查后重试。")
        }
        return chat(objectResponse("api/v1/chat/sessions/${id(sessionId)}/conversation/messages", "POST", buildJsonObject {
            put("content", text); put("attachment_ids", stringArray(attachmentIds.map(::id)))
            put("client_request_id", id(requestId))
        }))
    }

    suspend fun lifeAction(
        sessionId: String, action: String, version: Int, requestId: String,
        text: String = "", topicId: String? = null,
    ): ChatSnapshot = chat(objectResponse("api/v1/chat/sessions/${id(sessionId)}/life-overview/actions", "POST",
        buildJsonObject {
            put("action", action); put("expected_version", version); put("client_request_id", id(requestId))
            put("text", text); if (topicId != null) put("topic_id", topicId)
        }))

    suspend fun selectInterview(sessionId: String, module: String, version: Int): ChatSnapshot =
        chat(objectResponse("api/v1/chat/sessions/${id(sessionId)}/interview", "POST", buildJsonObject {
            put("module", module); put("expected_version", version)
        }))

    suspend fun interviewModules(): JsonElement = jsonResponse("api/v1/chat/interview-modules")

    suspend fun uploadChatPhoto(sessionId: String, data: ByteArray, requestId: String): Media =
        upload("api/v1/chat/sessions/${id(sessionId)}/media", data, requestId)

    suspend fun removeChatPhoto(sessionId: String, photoId: String) {
        request("api/v1/chat/sessions/${id(sessionId)}/media/${id(photoId)}", "DELETE")
    }

    suspend fun generateDraft(sessionId: String): Draft =
        draft(objectResponse("api/v1/chat/sessions/${id(sessionId)}/draft", "POST"))

    suspend fun getDraft(id: String): Draft = draft(objectResponse("api/v1/memory-drafts/${id(id)}"))

    suspend fun editDraft(draft: Draft, title: String, content: String, time: InformationDimension? = null): Draft =
        draft(objectResponse("api/v1/memory-drafts/${id(draft.id)}", "PATCH", buildJsonObject {
            put("revision", id(draft.revision)); put("title", title); put("summary", content)
            if (time != null) put("time", dimensionJson(time))
        }))

    suspend fun saveDraft(draft: Draft): Memory =
        memory(objectResponse("api/v1/memory-drafts/${id(draft.id)}/confirm", "POST", buildJsonObject {
            put("revision", id(draft.revision))
        }))

    suspend fun regenerateDraft(draft: Draft, replaceConfirmed: Boolean = true): Draft =
        draft(objectResponse("api/v1/memory-drafts/${id(draft.id)}/regenerate", "POST", buildJsonObject {
            put("revision", id(draft.revision)); put("replace_confirmed", replaceConfirmed)
        }))

    suspend fun previewDraftTime(draft: Draft, input: JsonObject): JsonObject =
        objectResponse("api/v1/memory-drafts/${id(draft.id)}/time-preview", "POST",
            JsonObject(input + ("revision" to JsonPrimitive(id(draft.revision)))))

    suspend fun previewDraftTime(draft: Draft, input: TimePreviewInput): TimePreview =
        contract { json.decodeFromString<TimePreview>(previewDraftTime(draft, input.fields()).toString()) }

    suspend fun previewMemoryTime(memory: Memory, input: JsonObject): JsonObject =
        objectResponse("api/v1/memories/${id(memory.id)}/time-preview", "POST", JsonObject(input + mapOf(
            "family_id" to JsonPrimitive(family()), "version" to JsonPrimitive(memory.version))))

    suspend fun previewMemoryTime(memory: Memory, input: TimePreviewInput): TimePreview =
        contract { json.decodeFromString<TimePreview>(previewMemoryTime(memory, input.fields()).toString()) }

    suspend fun getMemoir(personId: String): MemoirSnapshot = memoir(objectResponse(memoirPath(personId)))

    suspend fun saveMemoir(personId: String, version: Int, settings: MemoirSettings, requestId: String): MemoirSnapshot {
        if (!settings.isValid) throw AuthException(AuthErrorKind.Rejected, "请检查回忆录标题和副标题。")
        return memoir(objectResponse(memoirPath(personId), "PUT", buildJsonObject {
            put("version", version); put("requestId", id(requestId))
            put("settings", json.parseToJsonElement(json.encodeToString(settings)))
        }))
    }

    suspend fun uploadCover(personId: String, data: ByteArray, requestId: String): Media =
        upload(memoirPath(personId) + "/photos", data, requestId, filename = "cover.jpg")

    suspend fun loadMedia(media: Media): ByteArray {
        val path = "/api/v1/media/${id(media.id)}"
        if (!media.url.equals(path, ignoreCase = true)) {
            throw AuthException(AuthErrorKind.InvalidResponse, "服务器响应无效。")
        }
        return request(path.removePrefix("/"))
    }

    private suspend fun memoirPath(personId: String): String =
        "api/v1/families/${family()}/members/${id(personId)}/memoir"

    private suspend fun upload(
        path: String, data: ByteArray, requestId: String, query: Map<String, String> = emptyMap(),
        filename: String = "memory.jpg",
    ): Media {
        if (data.isEmpty() || data.size > 8 * 1024 * 1024) {
            throw AuthException(AuthErrorKind.Rejected, "每张照片压缩后不能超过 8 MB，请重新选择。")
        }
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", filename, data.toRequestBody("image/jpeg".toMediaType())).build()
        val result = media(parseObject(request(path, "POST", body = body,
            query = query + ("client_request_id" to id(requestId)))))
        if (!result.id.equals(requestId, ignoreCase = true)) invalidResponse()
        return result
    }

    private suspend fun objectResponse(
        path: String, method: String = "GET", fields: JsonObject? = null, query: Map<String, String> = emptyMap(),
    ): JsonObject = parseObject(request(path, method, fields?.toString()?.toRequestBody(JSON_TYPE), query))

    private suspend fun arrayResponse(path: String, query: Map<String, String> = emptyMap()): JsonArray =
        contract { json.parseToJsonElement(request(path, query = query).toString(Charsets.UTF_8)) as JsonArray }

    private suspend fun jsonResponse(path: String): JsonElement =
        contract { json.parseToJsonElement(request(path).toString(Charsets.UTF_8)) }

    private fun parseObject(data: ByteArray): JsonObject =
        contract { json.parseToJsonElement(data.toString(Charsets.UTF_8)).jsonObject }

    private suspend fun request(
        path: String, method: String = "GET", body: RequestBody? = null, query: Map<String, String> = emptyMap(),
    ): ByteArray {
        if (!active) throw CancellationException("Account session was invalidated")
        val url = base.newBuilder().addPathSegments(path).apply {
            query.forEach { (key, value) -> addQueryParameter(key, value) }
        }.build()
        val request = Request.Builder().url(url).header("Accept", "application/json")
            .header("Authorization", "Bearer ${session.token}").header("Cache-Control", "no-store")
            .method(method, when {
                body != null -> body
                method == "POST" || method == "PUT" || method == "PATCH" -> ByteArray(0).toRequestBody(null)
                else -> null
            }).build()
        val longRequest = method == "POST" && path.startsWith("api/v1/chat/sessions/") &&
            (path.endsWith("/messages") || path.endsWith("/life-overview/actions") || path.endsWith("/interview"))
        val call = (if (longRequest) interviewClient else client).newCall(request)
        calls += call
        try {
            return withContext(Dispatchers.IO) {
                call.awaitResponse().use { response ->
                    val data = response.body?.bytes() ?: ByteArray(0)
                    if (!active) throw CancellationException("Account session was invalidated")
                    if (response.code == 401) {
                        onUnauthorized()
                        throw AuthException(AuthErrorKind.Authentication, "登录已失效，请重新登录。", 401)
                    }
                    if (!response.isSuccessful) throw responseError(response.code, data)
                    data
                }
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: AuthException) {
            throw error
        } catch (error: InterruptedIOException) {
            if (!active) throw CancellationException("Account session was invalidated")
            throw AuthException(AuthErrorKind.Timeout, "请求超时，请重试；重复提交不会重复保存。")
        } catch (error: IOException) {
            if (!active) throw CancellationException("Account session was invalidated")
            throw AuthException(AuthErrorKind.Network, "无法连接服务器，请检查网络后重试。")
        } finally {
            calls -= call
        }
    }

    private suspend fun Call.awaitResponse(): Response = suspendCancellableCoroutine { continuation ->
        continuation.invokeOnCancellation { cancel() }
        enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if (continuation.isActive) continuation.resumeWithException(error)
            }
            override fun onResponse(call: Call, response: Response) {
                continuation.resume(response) { _, value, _ -> value.close() }
            }
        })
    }

    private fun responseError(status: Int, data: ByteArray): AuthException {
        val detail = runCatching {
            val value = json.parseToJsonElement(data.toString(Charsets.UTF_8)).jsonObject["detail"] as? JsonPrimitive
            value?.takeIf { it.isString }?.content?.takeIf { it.isNotBlank() }
        }.getOrNull()
        val fallback = when (status) {
            409 -> "内容已在其他设备更新，请刷新后重试。"
            422 -> "提交的内容不符合要求，请检查填写的信息和照片。"
            429 -> "尝试过于频繁，请稍后再试。"
            in 500..599 -> "服务器暂时无法处理请求，请稍后重试。"
            else -> "请求失败（HTTP $status）。"
        }
        return AuthException(AuthErrorKind.Rejected, detail ?: fallback, status)
    }

    private fun person(value: JsonObject): Person = contract {
        Person(id(value.requiredText("id")), value.requiredText("name"), value.requiredText("relationship"),
            value.text("birth_date"), openingMessage = value.obj("opening_message")?.let(::message),
            hasChatHistory = value.boolOrNull("has_chat_history"))
    }

    private fun memory(value: JsonObject, draftId: String? = null): Memory = contract {
        val personIds = value.strings("person_ids")
        val information = value.obj("information") ?: JsonObject(emptyMap())
        val date = value.text("memory_date")
        val time = dimension(information.obj("time"))
        var place = dimension(information.obj("place"))
        if (place.status == "missing" && value.text("location") != null) {
            place = InformationDimension("known", value.text("location"))
        }
        val assets = value.array("media_assets")?.map { media(it.jsonObject) }
            ?: value.strings("media_urls").mapNotNull { url ->
                val mediaId = url.removePrefix("/api/v1/media/")
                if (url == "/api/v1/media/$mediaId" && runCatching { id(mediaId) }.isSuccess) Media(mediaId, url) else null
            }
        Memory(id(value.text("id") ?: draftId ?: error("Missing memory ID")), value.requiredText("title"),
            value.text("summary") ?: value.text("raw_content").orEmpty(), value.integer("version", 1),
            personIds, personIds.joinToString("、") { personId -> knownMembers.firstOrNull { it.id == personId }?.name ?: "家庭成员" },
            date, value.text("created_at").orEmpty(), value.text("primary_person_id"), value.text("source_session_id"),
            time, place, dimension(information.obj("feeling")), assets, information, value)
    }

    private fun media(value: JsonObject): Media = contract {
        Media(id(value.requiredText("id")), value.requiredText("url"), value.integer("position", 0),
            value.text("mime_type") ?: "image/jpeg")
    }

    private fun message(value: JsonObject): ChatMessage = contract {
        ChatMessage(id(value.requiredText("id")), value.requiredText("role"), value.text("content").orEmpty(),
            value.array("attachments")?.map { media(it.jsonObject) }.orEmpty())
    }

    private fun chat(value: JsonObject): ChatSnapshot = contract {
        val state = value.obj("session") ?: error("Missing chat session")
        ChatSnapshot(id(state.requiredText("id")), value.array("messages")?.map { message(it.jsonObject) }
            ?.filter { it.role == "user" || it.role == "assistant" }.orEmpty(),
            value.bool("can_generate"), state.text("status") ?: "active", state.integer("version", 1),
            state.obj("information") ?: JsonObject(emptyMap()), value.obj("life_overview"), value.obj("readiness"),
            value.obj("generation_offer")?.text("message_id"), value.obj("review_request")?.text("message_id"),
            value.array("current_message_ids")?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }, value)
    }

    private fun draft(value: JsonObject): Draft = contract {
        val draftId = id(value.requiredText("id"))
        Draft(draftId, id(value.requiredText("revision")), memory(value.obj("memory") ?: error("Missing draft memory"), draftId),
            value.bool("manually_edited"), value.obj("time_review_from")?.let(::dimension), value.bool("has_new_narration"), value)
    }

    private fun memoir(value: JsonObject): MemoirSnapshot = contract {
        MemoirSnapshot(id(value.requiredText("personId")), value.requiredText("personName"), value.integer("version", 0),
            json.decodeFromString<MemoirSettings>((value.obj("settings") ?: error("Missing memoir settings")).toString()),
            value.array("stories")?.map { memory(it.jsonObject) }.orEmpty(), value.requiredText("contentRevision"), value)
    }

    private fun dimension(value: JsonObject?): InformationDimension = InformationDimension(
        value?.text("status") ?: "missing", value?.text("value"), value?.strings("source_message_ids").orEmpty(),
        value?.bool("user_edited") ?: false)

    private fun dimensionJson(value: InformationDimension): JsonObject = buildJsonObject {
        put("status", value.status); put("value", value.value?.let(::JsonPrimitive) ?: JsonNull)
        put("source_message_ids", stringArray(value.sourceMessageIds)); put("user_edited", value.userEdited)
    }

    private fun stringArray(value: List<String>): JsonArray = JsonArray(value.map(::JsonPrimitive))
    private fun JsonObject.text(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull
    private fun JsonObject.requiredText(key: String): String = text(key)?.takeIf { it.isNotBlank() } ?: error("Missing $key")
    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
    private fun JsonObject.array(key: String): JsonArray? = this[key] as? JsonArray
    private fun JsonObject.integer(key: String, default: Int): Int = (this[key] as? JsonPrimitive)?.intOrNull ?: default
    private fun JsonObject.boolOrNull(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull
    private fun JsonObject.bool(key: String): Boolean = boolOrNull(key) ?: false
    private fun JsonObject.strings(key: String): List<String> = array(key)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()

    private inline fun <T> contract(block: () -> T): T = try {
        block()
    } catch (error: CancellationException) {
        throw error
    } catch (error: AuthException) {
        throw error
    } catch (error: Exception) {
        invalidResponse()
    }

    private fun id(value: String): String = try {
        UUID.fromString(value).toString().also { if (!it.equals(value, ignoreCase = true)) invalidResponse() }
    } catch (error: IllegalArgumentException) { invalidResponse() }

    private fun invalidResponse(): Nothing = throw AuthException(AuthErrorKind.InvalidResponse, "服务器返回的数据格式不匹配。")

    private companion object {
        val JSON_TYPE = "application/json; charset=utf-8".toMediaType()
        fun validateBase(value: String): HttpUrl {
            val url = value.trimEnd('/').plus('/').toHttpUrlOrNull()
                ?: throw AuthException(AuthErrorKind.InvalidResponse, "服务器地址无效，请检查应用配置。")
            val local = BuildConfig.DEBUG && url.host in setOf("localhost", "127.0.0.1", "10.0.2.2", "::1")
            if ((!url.isHttps && !local) || url.username.isNotEmpty() || url.password.isNotEmpty() ||
                url.query != null || url.fragment != null) {
                throw AuthException(AuthErrorKind.InvalidResponse, "请配置 HTTPS 服务器。")
            }
            return url
        }
    }
}
