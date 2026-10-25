package cn.shinian.app

import cn.shinian.app.data.AuthException
import cn.shinian.app.data.AuthSession
import cn.shinian.app.data.BackendRepository
import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class FamilyDataControllerTest {
    private lateinit var server: MockWebServer
    private lateinit var repository: BackendRepository
    private val requests = Collections.synchronizedList(mutableListOf<String>())
    @Volatile private var empty = false
    @Volatile private var memoryStatus = 200
    @Volatile private var deleteStatus = 204
    @Volatile private var identityFamily = FAMILY
    @Volatile private var holdDelete = false
    @Volatile private var holdLists = false
    @Volatile private var disconnectDeletes = false
    @Volatile private var multipleMemories = false
    private val deleteStarted = CountDownLatch(1)
    private val deleteAllowed = CountDownLatch(1)
    private val listStarted = CountDownLatch(1)
    private val listAllowed = CountDownLatch(1)

    @Before fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.requestUrl!!.encodedPath
                requests += "${request.method} $path"
                if (request.method == "DELETE") {
                    deleteStarted.countDown()
                    if (holdDelete) check(deleteAllowed.await(3, TimeUnit.SECONDS))
                    if (disconnectDeletes) return MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST)
                    return MockResponse().setResponseCode(deleteStatus).apply {
                        if (deleteStatus != 204) setBody("""{"detail":"请重试"}""")
                    }
                }
                if (path != "/api/v1/auth/me" && holdLists) {
                    listStarted.countDown()
                    check(listAllowed.await(3, TimeUnit.SECONDS))
                }
                return when (path) {
                    "/api/v1/auth/me" -> MockResponse().setBody("""{"account_id":"$ACCOUNT","family_id":"$identityFamily","username":"test_family"}""")
                    "/api/v1/family-members/" -> MockResponse().setBody(if (empty) "[]" else PEOPLE)
                    "/api/v1/memories/" -> MockResponse().setResponseCode(memoryStatus).setBody(
                        if (memoryStatus != 200) """{"detail":"回忆暂时无法读取"}""" else if (empty) "[]"
                        else if (multipleMemories) MEMORIES.dropLast(1) + "," + MEMORIES.drop(1).replace(MEMORY, SECOND_MEMORY) else MEMORIES)
                    else -> MockResponse().setResponseCode(404)
                }
            }
        }
        server.start()
        repository = BackendRepository(AuthSession(server.url("/").toString().trimEnd('/'), ACCOUNT, FAMILY,
            "test_family", false, "test-token", "2030-01-01T00:00:00Z"))
    }

    @After fun tearDown() {
        deleteAllowed.countDown()
        listAllowed.countDown()
        repository.invalidate()
        server.shutdown()
    }

    @Test fun emptyFamilyRefreshReadsEachListOnceAndCanRefreshAgain() = runBlocking {
        empty = true
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        repeat(2) { controller.refresh()!!.join() }
        assertFalse(controller.state.value.loading)
        assertNull(controller.state.value.error)
        assertEquals(1, requests.count { it == "GET /api/v1/auth/me" })
        assertEquals(2, requests.count { it == "GET /api/v1/family-members/" })
        assertEquals(2, requests.count { it == "GET /api/v1/memories/" })
    }

    @Test fun emptyMemberListIsAValidLoadedStateForRepositoryConsumers() = runBlocking {
        empty = true
        repository.members()
        repository.memories()
        assertEquals(1, requests.count { it == "GET /api/v1/family-members/" })
        assertEquals(2, requests.count { it == "GET /api/v1/memories/" })
    }

    @Test fun failedMemoryReadKeepsPeopleAndRetryUsesOneReadPerList() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        memoryStatus = 503
        controller.refresh()!!.join()
        assertEquals(PERSON, controller.state.value.people.single().id)
        assertTrue(controller.state.value.memories.isEmpty())
        assertNotNull(controller.state.value.error)
        memoryStatus = 200
        controller.refresh()!!.join()
        assertNull(controller.state.value.error)
        assertEquals(1, controller.state.value.people.single().memoryCount)
        assertEquals("外婆", controller.state.value.memories.single().personName)
        assertEquals(2, requests.count { it == "GET /api/v1/family-members/" })
        assertEquals(2, requests.count { it == "GET /api/v1/memories/" })
    }

    @Test fun mismatchedIdentityNeverReadsFamilyLists() = runBlocking {
        identityFamily = PERSON
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        assertNotNull(controller.state.value.error)
        assertEquals(listOf("GET /api/v1/auth/me"), requests.toList())
    }

    @Test fun memoryIsRemovedOnlyAfterServerAcknowledgesWithoutAnotherListRoundTrip() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        val memory = controller.state.value.memories.single()
        val initialRequests = requests.size
        holdDelete = true
        val deletion = async { controller.deleteMemory(memory) }
        await(deleteStarted)
        assertFalse(deletion.isCompleted)
        assertEquals(memory.id, controller.state.value.memories.single().id)
        deleteAllowed.countDown()
        deletion.await()
        assertTrue(controller.state.value.memories.isEmpty())
        assertEquals(0, controller.state.value.people.single().memoryCount)
        assertFalse(controller.state.value.loading)
        assertEquals(listOf("DELETE /api/v1/memories/$MEMORY"), requests.drop(initialRequests))
    }

    @Test fun memberDeletionRetainsSavedStoriesAndUnlinksOnlyThatPerson() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        val initialRequests = requests.size
        controller.deleteMember(PERSON)
        assertTrue(controller.state.value.people.isEmpty())
        val memory = controller.state.value.memories.single()
        assertEquals(MEMORY, memory.id)
        assertTrue(memory.personIds.isEmpty())
        assertNull(memory.primaryPersonId)
        assertEquals(listOf("DELETE /api/v1/family-members/$PERSON"), requests.drop(initialRequests))
    }

    @Test fun rejectedMemoryDeletionKeepsStateAndAllowsSameVersionRetry() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        val memory = controller.state.value.memories.single()
        for (status in listOf(409, 503)) {
            deleteStatus = status
            val error = runCatching { controller.deleteMemory(memory) }.exceptionOrNull()
            assertEquals(status, (error as AuthException).statusCode)
            assertEquals(memory, controller.state.value.memories.single())
            assertEquals(1, controller.state.value.people.single().memoryCount)
        }
        deleteStatus = 204
        controller.deleteMemory(memory)
        assertTrue(controller.state.value.memories.isEmpty())
    }

    @Test fun completedDeleteCancelsOlderSlowRefreshSoItCannotRestoreDeletedMemory() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        val memory = controller.state.value.memories.single()
        holdLists = true
        val staleRefresh = controller.refresh()!!
        await(listStarted)
        controller.deleteMemory(memory)
        assertFalse(controller.state.value.loading)
        assertTrue(controller.state.value.memories.isEmpty())
        listAllowed.countDown()
        staleRefresh.join()
        assertTrue(staleRefresh.isCancelled)
        assertTrue(controller.state.value.memories.isEmpty())
        assertEquals(0, controller.state.value.people.single().memoryCount)
    }

    @Test fun failedMemberDeletionKeepsPeopleAndStoriesUntilRetrySucceeds() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        deleteStatus = 503
        assertNotNull(runCatching { controller.deleteMember(PERSON) }.exceptionOrNull())
        assertEquals(PERSON, controller.state.value.people.single().id)
        assertEquals(listOf(PERSON), controller.state.value.memories.single().personIds)
        deleteStatus = 204
        controller.deleteMember(PERSON)
        assertTrue(controller.state.value.people.isEmpty())
        assertTrue(controller.state.value.memories.single().personIds.isEmpty())
    }

    @Test fun failedMemoryRefreshAfterConfirmedDeleteDoesNotRestoreOldMemberCount() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        controller.deleteMemory(controller.state.value.memories.single())
        memoryStatus = 503
        controller.refresh()!!.join()
        assertNotNull(controller.state.value.error)
        assertTrue(controller.state.value.memories.isEmpty())
        assertEquals(0, controller.state.value.people.single().memoryCount)
    }

    @Test fun interruptedDeleteResponseKeepsLocalStateAndCanBeRetried() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        val memory = controller.state.value.memories.single()
        disconnectDeletes = true
        assertNotNull(runCatching { controller.deleteMemory(memory) }.exceptionOrNull())
        assertEquals(memory, controller.state.value.memories.single())
        disconnectDeletes = false
        controller.deleteMemory(memory)
        assertTrue(controller.state.value.memories.isEmpty())
    }

    @Test fun idempotentDeleteRetryThenFailedRefreshKeepsRemainingStoryCount() = runBlocking {
        multipleMemories = true
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        assertEquals(2, controller.state.value.people.single().memoryCount)
        val memory = controller.state.value.memories.single { it.id == MEMORY }
        controller.deleteMemory(memory)
        deleteStatus = 200
        controller.deleteMemory(memory) // The server returns its successful deletion receipt on retry.
        memoryStatus = 503
        controller.refresh()!!.join()
        assertEquals(SECOND_MEMORY, controller.state.value.memories.single().id)
        assertEquals(1, controller.state.value.people.single().memoryCount)
    }

    @Test fun completedMemberDeleteAlsoCancelsOlderRefreshAndKeepsStoriesUnlinked() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        holdLists = true
        val staleRefresh = controller.refresh()!!
        await(listStarted)
        controller.deleteMember(PERSON)
        listAllowed.countDown()
        staleRefresh.join()
        assertTrue(staleRefresh.isCancelled)
        assertTrue(controller.state.value.people.isEmpty())
        assertTrue(controller.state.value.memories.single().personIds.isEmpty())
    }

    @Test fun retiredAccountDeleteCannotChangeNewAccountState() = runBlocking {
        val controller = FamilyDataController(this).apply { bind(this@FamilyDataControllerTest.repository) }
        controller.refresh()!!.join()
        val memory = controller.state.value.memories.single()
        holdDelete = true
        val deletion = async { runCatching { controller.deleteMemory(memory) } }
        await(deleteStarted)
        controller.bind(null)
        deleteAllowed.countDown()
        deletion.await()
        assertEquals(FamilyState(), controller.state.value)
    }

    private suspend fun await(latch: CountDownLatch) = withContext(Dispatchers.IO) {
        assertTrue("Expected request reached server", latch.await(2, TimeUnit.SECONDS))
    }

    private companion object {
        const val ACCOUNT = "ea28ff04-a728-4efa-8c2c-9dbdc111cace"
        const val FAMILY = "b19a6d11-f176-4189-a532-d5ff36495451"
        const val PERSON = "fc15d63d-6a8c-4572-8743-d08cf1f6c5c1"
        const val MEMORY = "50847b40-175f-4a9e-89aa-576c72f3a1dd"
        const val SECOND_MEMORY = "2f899c06-64df-497d-8e07-35f11ac923a2"
        const val PEOPLE = """[{"id":"$PERSON","name":"外婆","relationship":"外婆","birth_date":"1948-06-01"}]"""
        const val MEMORIES = """[{"id":"$MEMORY","person_ids":["$PERSON"],"primary_person_id":"$PERSON","title":"旧时光","raw_content":"故事","summary":"故事","version":1}]"""
    }
}
