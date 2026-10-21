package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import android.graphics.Color
import android.os.SystemClock
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.AuthSession
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.Person
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises durable partial uploads without a network connection or a real family. */
@RunWith(AndroidJUnit4::class)
class ChatPhotoUploadRecoveryTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val backend = PhotoRecoveryTransport()
    private val repository = BackendRepository(backend.session, OkHttpClient.Builder().addInterceptor(backend).build())
    private val person = Person(backend.personId, "照片恢复测试家人", "奶奶", hasChatHistory = true)
    private val viewModels = ViewModelStore()
    private lateinit var controller: ChatController

    @After fun cleanup() {
        main { viewModels.clear() }
        repository.invalidate()
        File(File(context.noBackupFilesDir, "PendingStories"), backend.session.scopeKey).deleteRecursively()
    }

    @Test fun secondPhotoFailureRetainsBothPhotosAcrossRecreationAndRetriesOnlyMissingUpload() {
        openController()
        val selected = listOf(jpeg(Color.rgb(170, 80, 45)), jpeg(Color.rgb(45, 110, 165)))
        main {
            controller.appendPhotos(selected)
            controller.updateInput("照片里是我们一起生活的老屋。")
        }
        val photoIds = main { controller.photos.map { it.id } }
        assertEquals(2, photoIds.distinct().size)

        main { controller.send() }
        await("第二张上传失败后应保留待重试讲述") {
            main { !controller.busy && controller.pending != null && controller.error != null }
        }
        val messageId = main { requireNotNull(controller.pending).id }
        main {
            assertEquals(photoIds, controller.photos.map { it.id })
            assertEquals(listOf("uploaded", "failed"), controller.photos.map { it.status })
            assertEquals(photoIds[0], controller.photos[0].attachment?.id)
            assertNull(controller.photos[1].attachment)
            selected.indices.forEach { assertArrayEquals(selected[it], controller.photos[it].data) }
            assertEquals(messageId, controller.messages.last().id)
        }
        assertEquals(photoIds, backend.uploadIds.toList())
        assertTrue("照片未传齐前不能发送半条消息", backend.messages.isEmpty())

        val persisted = requireNotNull(ChatDraftStore(context, backend.session.scopeKey, person.id).load())
        assertEquals(messageId, persisted.first.pending?.id)
        assertEquals(photoIds, persisted.second.map { it.id })
        assertNotNull(persisted.second[0].attachment)
        assertNull(persisted.second[1].attachment)
        selected.indices.forEach { assertArrayEquals(selected[it], persisted.second[it].data) }

        // A new controller must recover the same durable upload/message identities.
        main { viewModels.clear() }
        openController()
        main {
            assertEquals(messageId, controller.pending?.id)
            assertEquals(photoIds, controller.photos.map { it.id })
            assertEquals(photoIds[0], controller.photos[0].attachment?.id)
            assertNull(controller.photos[1].attachment)
        }
        main { controller.send() }
        await("补传第二张后应一次性完成双图消息") {
            main { !controller.busy && controller.pending == null && controller.photos.isEmpty() && controller.snapshot?.messages?.any { it.id == messageId } == true }
        }

        assertEquals("首张成功的照片不能重传", listOf(photoIds[0], photoIds[1], photoIds[1]), backend.uploadIds.toList())
        assertEquals(1, backend.messages.size)
        val sent = backend.messages.single()
        assertEquals(messageId, sent.getString("client_request_id"))
        assertEquals("照片里是我们一起生活的老屋。", sent.getString("content"))
        assertEquals(photoIds, sent.getJSONArray("attachment_ids").strings())
        main {
            assertNull(controller.error)
            val saved = controller.messages.single { it.id == messageId }
            assertEquals(photoIds, saved.attachments.map { it.id })
        }
        val finalDraft = requireNotNull(ChatDraftStore(context, backend.session.scopeKey, person.id).load())
        assertNull(finalDraft.first.pending)
        assertTrue(finalDraft.second.isEmpty())
    }

    private fun openController() {
        main {
            controller = ViewModelProvider(viewModels, object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T = ChatController(context, person, repository) as T
            })[ChatController::class.java]
        }
        await("应打开本地模拟会话") { main { !controller.busy && controller.snapshot != null } }
    }

    private fun jpeg(color: Int): ByteArray {
        val bitmap = Bitmap.createBitmap(80, 60, Bitmap.Config.ARGB_8888)
        return try {
            bitmap.eraseColor(color)
            ByteArrayOutputStream().use { output ->
                assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG, 85, output))
                output.toByteArray()
            }
        } finally { bitmap.recycle() }
    }

    private fun await(message: String, condition: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + 10_000
        while (!condition()) {
            assertTrue(message, SystemClock.uptimeMillis() < deadline)
            SystemClock.sleep(20)
        }
    }

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return requireNotNull(result).getOrThrow()
    }
}

/** All requests terminate here. UUIDs and data directories are private to this test run. */
private class PhotoRecoveryTransport : Interceptor {
    val personId = UUID.randomUUID().toString()
    val session = AuthSession("https://photo-recovery-validation.example", UUID.randomUUID().toString(),
        UUID.randomUUID().toString(), "local-photo-instrumentation", false, "synthetic-photo-token", "2099-01-01T00:00:00Z")
    private val sessionId = UUID.randomUUID().toString()
    private val openingId = UUID.randomUUID().toString()
    private val replyId = UUID.randomUUID().toString()
    val uploadIds = CopyOnWriteArrayList<String>()
    val messages = CopyOnWriteArrayList<JSONObject>()

    @Synchronized override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        assertEquals("Bearer ${session.token}", request.header("Authorization"))
        val path = request.url.encodedPath
        val response = when {
            path.endsWith("/auth/me") -> JSONObject().put("account_id", session.accountId)
                .put("family_id", session.familyId).put("username", session.username)
            path.endsWith("/media") && request.method == "POST" -> {
                val photoId = requireNotNull(request.url.queryParameter("client_request_id"))
                assertTrue(request.body is MultipartBody)
                val part = (request.body as MultipartBody).parts.single()
                assertEquals("image/jpeg", part.body.contentType().toString())
                assertTrue(part.body.contentLength() > 0)
                uploadIds += photoId
                if (uploadIds.size == 2) throw IOException("Simulated interruption uploading second photo")
                attachment(photoId)
            }
            path.endsWith("/conversation/messages") -> {
                val body = Buffer().also { requireNotNull(request.body).writeTo(it) }.readUtf8()
                val value = JSONObject(body)
                assertEquals(2, value.getJSONArray("attachment_ids").length())
                messages += value
                snapshot()
            }
            path.endsWith("/conversation") -> snapshot()
            else -> throw AssertionError("Unexpected photo recovery request: $path")
        }
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
            .body(response.toString().toResponseBody("application/json".toMediaType())).build()
    }

    private fun attachment(id: String) = JSONObject().put("id", id).put("url", "/api/v1/media/$id")
    private fun message(id: String, role: String, text: String, attachments: JSONArray = JSONArray()) =
        JSONObject().put("id", id).put("role", role).put("content", text).put("attachments", attachments)

    private fun snapshot(): JSONObject {
        val list = JSONArray().put(message(openingId, "assistant", "这些照片里，有什么难忘的故事？"))
        messages.lastOrNull()?.let { sent ->
            val attachments = JSONArray(sent.getJSONArray("attachment_ids").strings().map(::attachment))
            list.put(message(sent.getString("client_request_id"), "user", sent.getString("content"), attachments))
            list.put(message(replyId, "assistant", "照片和讲述都已收到，我们继续慢慢聊。"))
        }
        return JSONObject().put("session", JSONObject().put("id", sessionId).put("status", "active")
            .put("version", 1).put("information", JSONObject()))
            .put("messages", list).put("can_generate", false).put("life_overview", JSONObject.NULL)
            .put("current_message_ids", JSONArray((0 until list.length()).map { list.getJSONObject(it).getString("id") }))
    }
}

private fun JSONArray.strings(): List<String> = (0 until length()).map(::getString)
