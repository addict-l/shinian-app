package cn.shinian.app.data

import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class AuthApiTest {
    private lateinit var server: MockWebServer
    private lateinit var api: AuthApi

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        api = AuthApi(server.url("/").toString())
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun loginNormalizesUsernameAndUsesReturnedDeviceSession() = runBlocking {
        server.enqueue(MockResponse().setBody(LOGIN_RESPONSE))

        val session = api.login("  FAMILY_2  ", "keep My Spaces ")

        assertEquals(ACCOUNT_ID, session.accountId)
        assertEquals(FAMILY_ID, session.familyId)
        assertEquals("family_2", session.username)
        assertEquals("opaque-device-session", session.token)
        assertEquals(api.server, session.server)
        assertFalse(session.server.endsWith('/'))
        val request = server.takeRequest(1, TimeUnit.SECONDS)!!
        assertEquals("POST", request.method)
        assertEquals("/api/v1/auth/login", request.path)
        assertNull(request.getHeader("Authorization"))
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals("family_2", body["username"]!!.jsonPrimitive.content)
        assertEquals("keep My Spaces ", body["password"]!!.jsonPrimitive.content)
    }

    @Test
    fun registrationUsesRegisterAndAcceptsCreatedResponse() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(201).setBody(LOGIN_RESPONSE))

        val session = api.register("new_family", "password123")

        assertEquals(FAMILY_ID, session.familyId)
        assertEquals("/api/v1/auth/register", server.takeRequest(1, TimeUnit.SECONDS)!!.path)
    }

    @Test
    fun restoringSessionSendsBearerAndReadsActualIdentityShape() = runBlocking {
        server.enqueue(MockResponse().setBody(IDENTITY_RESPONSE))

        val identity = api.me(session())

        assertEquals(AccountIdentity(ACCOUNT_ID, FAMILY_ID, "family_2", false), identity)
        val request = server.takeRequest(1, TimeUnit.SECONDS)!!
        assertEquals("GET", request.method)
        assertEquals("/api/v1/auth/me", request.path)
        assertEquals("Bearer opaque-device-session", request.getHeader("Authorization"))
    }

    @Test
    fun logoutAcceptsEmpty204Response() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(204))

        api.logout(session())

        val request = server.takeRequest(1, TimeUnit.SECONDS)!!
        assertEquals("POST", request.method)
        assertEquals("/api/v1/auth/logout", request.path)
        assertEquals("Bearer opaque-device-session", request.getHeader("Authorization"))
    }

    @Test
    fun wrongPasswordAndExpiredSessionHaveAppropriateMessages() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Unauthorized"}"""))
        val login = expectAuthFailure { api.login("family_2", "incorrect") }
        assertEquals(AuthErrorKind.Authentication, login.kind)
        assertEquals("账号或密码不正确，请重新输入。", login.message)
        assertEquals(401, login.statusCode)

        server.enqueue(MockResponse().setResponseCode(401))
        val restore = expectAuthFailure { api.me(session()) }
        assertEquals("登录已失效，请重新登录。", restore.message)
    }

    @Test
    fun duplicateAccountAndStructuredValidationAreReadable() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(409)
            .setBody("""{"detail":"这个账号已被使用，请换一个账号。"}"""))
        val duplicate = expectAuthFailure { api.register("family_2", "password123") }
        assertEquals(AuthErrorKind.Rejected, duplicate.kind)
        assertEquals("这个账号已被使用，请换一个账号。", duplicate.message)

        server.enqueue(MockResponse().setResponseCode(422)
            .setBody("""{"detail":[{"loc":["body","username"],"msg":"validation failed"}]}"""))
        val invalid = expectAuthFailure { api.register("x", "123") }
        assertEquals("账号格式或密码不符合要求，请检查后重试。", invalid.message)
    }

    @Test
    fun malformedOrIncompleteResponseNeverBecomesSession() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"account_id":"invalid","family_id":"$FAMILY_ID","username":"family_2","token":"token","expires_at":"2030-01-01T00:00:00Z"}"""))
        assertEquals(AuthErrorKind.InvalidResponse,
            expectAuthFailure { api.login("family_2", "password123") }.kind)

        server.enqueue(MockResponse().setBody(IDENTITY_RESPONSE))
        assertEquals(AuthErrorKind.InvalidResponse,
            expectAuthFailure { api.login("family_2", "password123") }.kind)
    }

    @Test
    fun changingServerNeverSendsExistingToken() = runBlocking {
        val error = expectAuthFailure { api.me(session().copy(server = "https://other.example")) }

        assertEquals(AuthErrorKind.Authentication, error.kind)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun emptyFieldsDoNotMakeNetworkRequests() = runBlocking {
        val error = expectAuthFailure { api.login("   ", "") }

        assertEquals(AuthErrorKind.Rejected, error.kind)
        assertEquals("请输入账号和密码。", error.message)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun redirectsDoNotForwardCredentials() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", "https://other.example/"))

        val error = expectAuthFailure { api.login("family_2", "password123") }

        assertEquals(307, error.statusCode)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun tokenIsRedactedAndCacheScopeSurvivesReauthentication() {
        val session = session()

        assertFalse(session.toString().contains(session.token))
        assertEquals(session.scopeKey, session.copy(token = "another-device-session").scopeKey)
        assertTrue(session.scopeKey.matches(Regex("[0-9a-f]{64}")))
        assertFalse(session.scopeKey == session.copy(familyId = ACCOUNT_ID).scopeKey)
        assertFalse(session.scopeKey == session.copy(server = "https://other.example").scopeKey)
    }

    private fun session() = AuthSession(api.server, ACCOUNT_ID, FAMILY_ID, "family_2", false,
        "opaque-device-session", "2030-01-01T00:00:00Z")

    private suspend fun expectAuthFailure(block: suspend () -> Any?): AuthException {
        try {
            block()
        } catch (error: AuthException) {
            return error
        }
        throw AssertionError("Expected AuthException")
    }

    private companion object {
        const val ACCOUNT_ID = "ea28ff04-a728-4efa-8c2c-9dbdc111cace"
        const val FAMILY_ID = "b19a6d11-f176-4189-a532-d5ff36495451"
        const val IDENTITY_RESPONSE = """{"account_id":"$ACCOUNT_ID","family_id":"$FAMILY_ID","username":"family_2","legacy":false}"""
        const val LOGIN_RESPONSE = """{"account_id":"$ACCOUNT_ID","family_id":"$FAMILY_ID","username":"family_2","legacy":false,"token":"opaque-device-session","token_type":"Bearer","expires_at":"2030-01-01T00:00:00Z"}"""
    }
}
