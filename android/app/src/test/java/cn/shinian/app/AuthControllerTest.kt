package cn.shinian.app

import cn.shinian.app.data.*
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthControllerTest {
    private val saved = AuthSession("https://example.com", "account", "family", "family", false, "device-token", "2030-01-01T00:00:00Z")
    private class Store(var value: AuthSession? = null) : SessionPersistence {
        var failSave = false
        var failClear = false
        override fun load() = value
        override fun save(session: AuthSession) { if (failSave) error("disk full"); value = session }
        override fun clear() { if (failClear) error("storage unavailable"); value = null }
    }
    private class Service(private val result: AuthSession) : AuthService {
        override val server = result.server
        var meCalls = 0
        var logoutCalls = 0
        var meError: AuthException? = null
        var logoutError: AuthException? = null
        var identity = AccountIdentity(result.accountId, result.familyId, result.username)
        override suspend fun login(username: String, password: String) = result
        override suspend fun register(username: String, password: String) = result
        override suspend fun me(session: AuthSession): AccountIdentity { meCalls++; meError?.let { throw it }; return identity }
        override suspend fun logout(session: AuthSession) { logoutCalls++; logoutError?.let { throw it } }
    }

    @Test fun restoreRequiresMatchingServerIdentity() = runTest {
        val store = Store(saved); val api = Service(saved)
        api.identity = api.identity.copy(familyId = "another-family")
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        assertNull(controller.state.value.session); assertNull(store.value)
        assertFalse(controller.state.value.restoring)
    }

    @Test fun restorationDoesNotSendTokenToAnotherServer() = runTest {
        val store = Store(saved.copy(server = "https://old.example.com")); val api = Service(saved)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        assertEquals(0, api.meCalls); assertNull(controller.state.value.session)
    }

    @Test fun restoreNetworkFailureKeepsRecoverableSessionOnDisk() = runTest {
        val store = Store(saved); val api = Service(saved)
        api.meError = AuthException(AuthErrorKind.Network, "offline")
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        assertEquals(saved, store.value); assertNull(controller.state.value.session)
        assertNotNull(controller.state.value.error)
    }

    @Test fun expiredRestorationClearsRevokedToken() = runTest {
        val store = Store(saved); val api = Service(saved)
        api.meError = AuthException(AuthErrorKind.Authentication, "expired", 401)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        assertNull(store.value); assertNull(controller.state.value.session)
    }

    @Test fun failedSecurePersistenceRevokesNewRemoteSession() = runTest {
        val store = Store().apply { failSave = true }; val api = Service(saved)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        controller.login("family", "password"); advanceUntilIdle()
        assertEquals(1, api.logoutCalls); assertNull(controller.state.value.session)
        assertTrue(controller.state.value.error.orEmpty().contains("无法保存"))
    }

    @Test fun failedRemoteLogoutRetainsDeviceSessionForRetry() = runTest {
        val store = Store(saved); val api = Service(saved)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        api.logoutError = AuthException(AuthErrorKind.Network, "offline")
        controller.logout(); advanceUntilIdle()
        assertEquals(saved, controller.state.value.session); assertEquals(saved, store.value)
        assertFalse(controller.state.value.loading)
    }

    @Test fun logoutOfAlreadyRevokedSessionStillSignsOutLocally() = runTest {
        val store = Store(saved); val api = Service(saved)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        api.logoutError = AuthException(AuthErrorKind.Authentication, "expired", 401)
        controller.logout(); advanceUntilIdle()
        assertNull(store.value); assertNull(controller.state.value.session)
    }

    @Test fun oldUnauthorizedRequestCannotSignOutCurrentAccount() = runTest {
        val store = Store(saved); val api = Service(saved)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        controller.handleUnauthorized(saved.copy(token = "retired-token")); advanceUntilIdle()
        assertEquals(saved, controller.state.value.session); assertEquals(saved, store.value)
    }

    @Test fun revokedSessionWithUnavailableStorageStillLeavesRestoreScreen() = runTest {
        val store = Store(saved).apply { failClear = true }; val api = Service(saved)
        api.meError = AuthException(AuthErrorKind.Authentication, "expired", 401)
        val controller = AuthController(api, store, this, StandardTestDispatcher(testScheduler))
        controller.restore(); advanceUntilIdle()
        assertNull(controller.state.value.session)
        assertFalse(controller.state.value.restoring)
        assertNotNull(controller.state.value.error)
    }
}
