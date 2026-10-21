package cn.shinian.app.data

import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class BackendRepositoryTest {
    private lateinit var server: MockWebServer
    private lateinit var repository: BackendRepository
    private val unauthorized = AtomicInteger()

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val session = AuthSession(server.url("/").toString().trimEnd('/'), ACCOUNT, FAMILY, "family_2",
            false, "device-token", "2030-01-01T00:00:00Z")
        repository = BackendRepository(session, onUnauthorized = { unauthorized.incrementAndGet() })
    }

    @After
    fun tearDown() {
        repository.invalidate()
        server.shutdown()
    }

    @Test
    fun familyListingVerifiesOwnershipAndCountsMemoriesWithoutPublicPhotoFetches() = runBlocking {
        enqueueIdentity()
        server.enqueue(MockResponse().setBody("""[{"id":"$PERSON","name":"外婆","relationship":"外婆","birth_date":"1948-06-01","has_chat_history":true}]"""))
        server.enqueue(MockResponse().setBody("[$MEMORY_JSON]"))

        val people = repository.members()

        assertEquals(1, people.single().memoryCount)
        assertEquals("外婆", people.single().name)
        assertTrue(people.single().hasChatHistory == true)
        assertEquals("/api/v1/auth/me", take().path)
        assertEquals("/api/v1/family-members/?family_id=$FAMILY", take().path)
        assertEquals("/api/v1/memories/?family_id=$FAMILY", take().path)
        assertEquals(3, server.requestCount)
    }

    @Test
    fun addingPersonSendsStableRequestIdentityAndRequiredBirthday() = runBlocking {
        enqueueIdentity()
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"id":"$PERSON","name":"外婆","relationship":"外婆","birth_date":"1948-06-01"}"""))

        repository.addMember(" 外婆 ", " 外婆 ", "1948-06-01", REQUEST)

        take()
        val request = take()
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals(REQUEST, body["client_request_id"]!!.jsonPrimitive.content)
        assertEquals(FAMILY, body["family_id"]!!.jsonPrimitive.content)
        assertEquals("外婆", body["name"]!!.jsonPrimitive.content)
        assertEquals("1948-06-01", body["birth_date"]!!.jsonPrimitive.content)
    }

    @Test
    fun conversationMessagesUsePersonConversationEndpointAndPreserveUnknownState() = runBlocking {
        server.enqueue(MockResponse().setBody(CHAT_JSON))

        val snapshot = repository.sendMessage(SESSION, "第一次坐火车", listOf(PHOTO), REQUEST)

        val request = take()
        assertEquals("/api/v1/chat/sessions/$SESSION/conversation/messages", request.path)
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals(REQUEST, body["client_request_id"]!!.jsonPrimitive.content)
        assertEquals(PHOTO, body["attachment_ids"]!!.jsonArray.single().jsonPrimitive.content)
        assertEquals("Bearer device-token", request.getHeader("Authorization"))
        assertEquals(7, snapshot.version)
        assertEquals("exploring", snapshot.information["guided_interview"]!!.jsonObject["phase"]!!.jsonPrimitive.content)
        assertEquals("preserved", snapshot.raw["future_state"]!!.jsonPrimitive.content)
        assertEquals("旧时光", snapshot.messages.single().content)
    }

    @Test
    fun overviewActionsCarryExpectedVersionAndRetryIdentity() = runBlocking {
        server.enqueue(MockResponse().setBody(CHAT_JSON))

        repository.lifeAction(SESSION, "answer", 6, REQUEST, "1948年", "home")

        val request = take()
        assertEquals("/api/v1/chat/sessions/$SESSION/life-overview/actions", request.path)
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals("6", body["expected_version"]!!.jsonPrimitive.content)
        assertEquals(REQUEST, body["client_request_id"]!!.jsonPrimitive.content)
        assertEquals("1948年", body["text"]!!.jsonPrimitive.content)
    }

    @Test
    fun editedDraftIsConfirmedWithItsReturnedRevision() = runBlocking {
        server.enqueue(MockResponse().setBody(DRAFT_JSON))
        val original = repository.getDraft(DRAFT)
        server.enqueue(MockResponse().setBody(DRAFT_JSON.replace(REVISION, NEXT_REVISION)))
        val edited = repository.editDraft(original, "新的标题", "新的正文", InformationDimension("approximate", "1960年代"))
        server.enqueue(MockResponse().setBody(MEMORY_JSON))

        val saved = repository.saveDraft(edited)

        take()
        val edit = take()
        assertEquals("PATCH", edit.method)
        assertEquals(REVISION, Json.parseToJsonElement(edit.body.readUtf8()).jsonObject["revision"]!!.jsonPrimitive.content)
        val confirm = take()
        assertEquals("/api/v1/memory-drafts/$DRAFT/confirm", confirm.path)
        assertEquals(NEXT_REVISION, Json.parseToJsonElement(confirm.body.readUtf8()).jsonObject["revision"]!!.jsonPrimitive.content)
        assertEquals(MEMORY, saved.id)
    }

    @Test
    fun memoryEditingKeepsApproximateTimeAndVersionInsteadOfInventingExactDate() = runBlocking {
        server.enqueue(MockResponse().setBody(MEMORY_JSON))
        val memory = repository.getMemory(MEMORY)
        enqueueIdentity()
        server.enqueue(MockResponse().setBody(MEMORY_JSON))

        repository.updateMemory(memory, MemoryEdit(memory).copy(time = InformationDimension("approximate", "青年时")))

        take(); take()
        val request = take()
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals("PATCH", request.method)
        assertEquals("3", body["version"]!!.jsonPrimitive.content)
        assertEquals(JsonNull, body["memory_date"])
        assertEquals("approximate", body["time"]!!.jsonObject["status"]!!.jsonPrimitive.content)
        assertEquals("青年时", body["time"]!!.jsonObject["value"]!!.jsonPrimitive.content)
        assertEquals(PHOTO, body["media_ids"]!!.jsonArray.single().jsonPrimitive.content)
    }

    @Test
    fun mediaUploadUsesMultipartStableIdentityAndAuthenticatedDownload() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"id":"$PHOTO","url":"/api/v1/media/$PHOTO","position":0}"""))
        val media = repository.uploadChatPhoto(SESSION, byteArrayOf(1, 2, 3), PHOTO)
        server.enqueue(MockResponse().setBody("image bytes"))

        val bytes = repository.loadMedia(media)

        val upload = take()
        assertEquals("/api/v1/chat/sessions/$SESSION/media?client_request_id=$PHOTO", upload.path)
        assertTrue(upload.getHeader("Content-Type")!!.startsWith("multipart/form-data; boundary="))
        assertTrue(upload.body.readUtf8().contains("name=\"file\"; filename=\"memory.jpg\""))
        val download = take()
        assertEquals("/api/v1/media/$PHOTO", download.path)
        assertEquals("Bearer device-token", download.getHeader("Authorization"))
        assertEquals("image bytes", bytes.toString(Charsets.UTF_8))
    }

    @Test
    fun externalMediaUrlNeverReceivesFamilyToken() = runBlocking {
        val error = expectFailure { repository.loadMedia(Media(PHOTO, "https://other.example/api/v1/media/$PHOTO")) }

        assertEquals(AuthErrorKind.InvalidResponse, error.kind)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun memoirSaveCarriesOptimisticVersionAndCamelCaseRequestId() = runBlocking {
        enqueueIdentity()
        server.enqueue(MockResponse().setBody(MEMOIR_JSON))
        val snapshot = repository.getMemoir(PERSON)
        server.enqueue(MockResponse().setBody(MEMOIR_JSON))

        repository.saveMemoir(PERSON, snapshot.version, snapshot.settings.copy(subtitle = "岁月留声"), REQUEST)

        take(); take()
        val request = take()
        assertEquals("PUT", request.method)
        assertEquals("/api/v1/families/$FAMILY/members/$PERSON/memoir", request.path)
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals(REQUEST, body["requestId"]!!.jsonPrimitive.content)
        assertEquals("2", body["version"]!!.jsonPrimitive.content)
        assertEquals("岁月留声", body["settings"]!!.jsonObject["subtitle"]!!.jsonPrimitive.content)
        assertEquals("revision-value", snapshot.contentRevision)
        assertEquals("first-day", snapshot.raw["future_field"]!!.jsonPrimitive.content)
    }

    @Test
    fun timePreviewRetainsSnapshotAndUtf16OffsetsWithoutReinterpretingThem() = runBlocking {
        server.enqueue(MockResponse().setBody(DRAFT_JSON))
        val draft = repository.getDraft(DRAFT)
        server.enqueue(MockResponse().setBody("""{"snapshot":"source-hash","message":"请核对","suggestions":[{"id":"a","field":"summary","start":2,"length":4,"before":"1959","after":"1960","context":"旧日时光","ambiguous":false,"reason":"日期更正"}]}"""))

        val preview = repository.previewDraftTime(draft, TimePreviewInput("旧时光", "🙂1959年的事",
            InformationDimension("known", "1959-01-01", listOf(REQUEST), true), InformationDimension("known", "1960-01-01")))

        take()
        val request = take()
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals(REVISION, body["revision"]!!.jsonPrimitive.content)
        assertEquals("🙂1959年的事", body["summary"]!!.jsonPrimitive.content)
        assertEquals(REQUEST, body["old_time"]!!.jsonObject["source_message_ids"]!!.jsonArray.single().jsonPrimitive.content)
        assertEquals("true", body["old_time"]!!.jsonObject["user_edited"]!!.jsonPrimitive.content)
        assertEquals(2, preview.suggestions.single().start)
    }

    @Test
    fun ownership401NotifiesButInvalidatedRepositoryCannotLogOutNewSession() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"expired"}"""))
        assertEquals(401, expectFailure { repository.chatState(SESSION) }.statusCode)
        assertEquals(1, unauthorized.get())
        take()
        server.enqueue(MockResponse().setResponseCode(401).setBody("expired").setBodyDelay(3, TimeUnit.SECONDS))
        val pending = async(Dispatchers.Default) { runCatching { repository.chatState(SESSION) } }
        take()

        repository.invalidate()

        assertTrue(pending.await().exceptionOrNull() is CancellationException)
        assertEquals(1, unauthorized.get())
    }

    @Test
    fun anotherFamilyIdentityCannotLoadAnyPeople() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"account_id":"$ACCOUNT","family_id":"$PERSON","username":"family_2"}"""))

        val error = expectFailure { repository.members() }

        assertEquals(AuthErrorKind.Authentication, error.kind)
        assertEquals(1, server.requestCount)
        assertEquals("/api/v1/auth/me", take().path)
    }

    @Test
    fun retryingInterviewUsesTheSameUserMessageIdentity() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(503).setBody("""{"detail":"回复暂时未完成，请重试。"}"""))
        expectFailure { repository.sendMessage(SESSION, "旧时光", emptyList(), REQUEST) }
        server.enqueue(MockResponse().setBody(CHAT_JSON))

        val recovered = repository.sendMessage(SESSION, "旧时光", emptyList(), REQUEST)

        val first = Json.parseToJsonElement(take().body.readUtf8()).jsonObject
        val retry = Json.parseToJsonElement(take().body.readUtf8()).jsonObject
        assertEquals(REQUEST, first["client_request_id"]!!.jsonPrimitive.content)
        assertEquals(REQUEST, retry["client_request_id"]!!.jsonPrimitive.content)
        assertEquals(REQUEST, recovered.messages.single().id)
        assertEquals(2, server.requestCount)
    }

    @Test
    fun optimisticVersionConflictDoesNotPretendSaveSucceededOrExpireAccount() = runBlocking {
        server.enqueue(MockResponse().setBody(MEMORY_JSON))
        val original = repository.getMemory(MEMORY)
        enqueueIdentity()
        server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"内容已更新，请重新读取。"}"""))

        val error = expectFailure { repository.updateMemory(original, MemoryEdit(original).copy(title = "我的修改")) }

        assertEquals(409, error.statusCode)
        assertEquals(AuthErrorKind.Rejected, error.kind)
        assertEquals("旧时光", original.title)
        assertEquals(3, original.version)
        assertEquals(0, unauthorized.get())
    }

    @Test
    fun uploadedPhotoWithDifferentServerIdentityCannotAttachToMessage() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"id":"$REQUEST","url":"/api/v1/media/$REQUEST"}"""))

        val error = expectFailure { repository.uploadChatPhoto(SESSION, byteArrayOf(1, 2, 3), PHOTO) }

        assertEquals(AuthErrorKind.InvalidResponse, error.kind)
        assertEquals(1, server.requestCount)
    }

    private fun enqueueIdentity() {
        server.enqueue(MockResponse().setBody("""{"account_id":"$ACCOUNT","family_id":"$FAMILY","username":"family_2","legacy":false}"""))
    }

    private fun take() = server.takeRequest(2, TimeUnit.SECONDS) ?: throw AssertionError("Missing HTTP request")

    private suspend fun expectFailure(block: suspend () -> Any?): AuthException {
        try { block() } catch (error: AuthException) { return error }
        throw AssertionError("Expected AuthException")
    }

    private companion object {
        const val ACCOUNT = "ea28ff04-a728-4efa-8c2c-9dbdc111cace"
        const val FAMILY = "b19a6d11-f176-4189-a532-d5ff36495451"
        const val PERSON = "fc15d63d-6a8c-4572-8743-d08cf1f6c5c1"
        const val SESSION = "a77b76ab-15c8-4ae3-89be-1c7c87844ca8"
        const val REQUEST = "ae7ea9d6-ea87-4fea-98e7-642f60d3af8d"
        const val MEMORY = "50847b40-175f-4a9e-89aa-576c72f3a1dd"
        const val PHOTO = "21af900a-d99c-4c2a-a8bd-dda079fc9e4a"
        const val DRAFT = "5e0675cc-56cc-4376-8302-d1c7fa65d327"
        const val REVISION = "b7c6d8b6-7928-4817-b092-35dc55fe2474"
        const val NEXT_REVISION = "d524b6b0-c463-46ce-8bda-f28ac3025819"
        const val MEMORY_JSON = """{"id":"$MEMORY","person_ids":["$PERSON"],"title":"旧时光","raw_content":"原话","summary":"旧日的故事","memory_date":null,"created_at":"2026-10-21T00:00:00","version":3,"information":{"time":{"status":"approximate","value":"1960年代"}},"media_assets":[{"id":"$PHOTO","url":"/api/v1/media/$PHOTO"}]}"""
        const val CHAT_JSON = """{"session":{"id":"$SESSION","version":7,"status":"active","information":{"guided_interview":{"phase":"exploring","module":"childhood"}}},"messages":[{"id":"$REQUEST","role":"assistant","content":"旧时光"}],"can_generate":true,"future_state":"preserved"}"""
        const val DRAFT_JSON = """{"id":"$DRAFT","revision":"$REVISION","memory":{"person_ids":["$PERSON"],"title":"旧时光","raw_content":"原话","summary":"旧日的故事","memory_date":null},"manually_edited":true,"has_new_narration":false}"""
        const val MEMOIR_JSON = """{"personId":"$PERSON","personName":"外婆","version":2,"settings":{"title":"外婆的回忆录","coverTemplate":"text"},"stories":[$MEMORY_JSON],"contentRevision":"revision-value","future_field":"first-day"}"""
    }
}
