package cn.shinian.app.data

import cn.shinian.app.FamilyDataController
import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.*
import org.junit.Test

class SharedBackendTransportTest {
    @Test fun defaultHomeClientReusesLoginConnectionWithoutSharingAuthorizationHeaders() = runBlocking {
        val requests = Collections.synchronizedList(mutableListOf<RecordedRequest>())
        val server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                requests += request
                return MockResponse().setBody(when (request.requestUrl!!.encodedPath) {
                    "/api/v1/auth/login" -> LOGIN
                    "/api/v1/auth/me" -> IDENTITY
                    else -> "[]"
                })
            }
        }
        server.start()
        try {
            val auth = AuthApi(server.url("/").toString())
            val repository = BackendRepository(auth.login("test_family", "synthetic-password"))
            try {
                val controller = FamilyDataController(this)
                controller.bind(repository)
                controller.refresh()!!.join()
                assertNull(controller.state.value.error)
                val identity = requests.single { it.requestUrl!!.encodedPath == "/api/v1/auth/me" }
                assertEquals("Home ownership verification should reuse login's established connection", 1, identity.sequenceNumber)
                auth.login("test_family", "synthetic-password")
                requests.filter { it.requestUrl!!.encodedPath == "/api/v1/auth/login" }.forEach {
                    assertNull(it.getHeader("Authorization"))
                }
                requests.filter { it.requestUrl!!.encodedPath != "/api/v1/auth/login" }.forEach {
                    assertEquals("Bearer synthetic-token", it.getHeader("Authorization"))
                }
            } finally { repository.invalidate() }
        } finally { server.shutdown() }
    }

    @Test fun invalidatingOneRepositoryDoesNotCancelAnotherUsingTheSharedTransport() = runBlocking {
        val held = CountDownLatch(1)
        val release = CountDownLatch(1)
        val server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                if (request.getHeader("Authorization") == "Bearer retired-token") {
                    held.countDown()
                    check(release.await(3, TimeUnit.SECONDS))
                }
                return MockResponse().setBody(CHAT)
            }
        }
        server.start()
        val retired = BackendRepository(session(server, "retired-token"))
        val current = BackendRepository(session(server, "current-token"))
        try {
            val old = async { runCatching { retired.chatState(SESSION) } }
            withContext(Dispatchers.IO) { assertTrue(held.await(2, TimeUnit.SECONDS)) }
            val active = async { current.chatState(SESSION) }
            retired.invalidate()
            assertEquals(SESSION, active.await().sessionId)
            assertTrue(old.await().exceptionOrNull() is CancellationException)
        } finally {
            release.countDown()
            retired.invalidate()
            current.invalidate()
            server.shutdown()
        }
    }

    @Test fun injectedAuthAndRepositoryClientsRetainTheirOwnInterceptors() = runBlocking {
        val authCalls = AtomicInteger()
        val repositoryCalls = AtomicInteger()
        val server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest) = MockResponse().setBody(when (request.requestUrl!!.encodedPath) {
                "/api/v1/auth/login" -> LOGIN
                "/api/v1/auth/me" -> IDENTITY
                else -> "[]"
            })
        }
        server.start()
        try {
            val authClient = OkHttpClient.Builder().addInterceptor { chain -> authCalls.incrementAndGet(); chain.proceed(chain.request()) }.build()
            val repositoryClient = OkHttpClient.Builder().addInterceptor { chain -> repositoryCalls.incrementAndGet(); chain.proceed(chain.request()) }.build()
            val auth = AuthApi(server.url("/").toString(), authClient)
            val repository = BackendRepository(auth.login("test_family", "synthetic-password"), repositoryClient)
            try { repository.familyListing() } finally { repository.invalidate() }
            assertEquals(1, authCalls.get())
            assertEquals(3, repositoryCalls.get())
        } finally { server.shutdown() }
    }

    private fun session(server: MockWebServer, token: String) = AuthSession(server.url("/").toString().trimEnd('/'),
        ACCOUNT, FAMILY, "test_family", false, token, "2030-01-01T00:00:00Z")

    private companion object {
        const val ACCOUNT = "ea28ff04-a728-4efa-8c2c-9dbdc111cace"
        const val FAMILY = "b19a6d11-f176-4189-a532-d5ff36495451"
        const val SESSION = "a77b76ab-15c8-4ae3-89be-1c7c87844ca8"
        const val IDENTITY = """{"account_id":"$ACCOUNT","family_id":"$FAMILY","username":"test_family"}"""
        const val LOGIN = """{"account_id":"$ACCOUNT","family_id":"$FAMILY","username":"test_family","token":"synthetic-token","expires_at":"2030-01-01T00:00:00Z"}"""
        const val CHAT = """{"session":{"id":"$SESSION","version":1,"status":"active","information":{}},"messages":[]}"""
    }
}
