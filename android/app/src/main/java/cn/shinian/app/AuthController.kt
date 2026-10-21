package cn.shinian.app

import cn.shinian.app.data.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class AuthenticationState(
    val session: AuthSession? = null,
    val restoring: Boolean = true,
    val loading: Boolean = false,
    val error: String? = null,
)

/** Owns one device session. A retired request cannot expire a newer login. */
class AuthController(
    private val service: AuthService,
    private val persistence: SessionPersistence,
    private val scope: CoroutineScope,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) {
    private val mutableState = MutableStateFlow(AuthenticationState())
    val state = mutableState.asStateFlow()
    private var restored = false
    private val persistenceLock = Mutex()

    fun restore() {
        if (restored) return
        restored = true
        scope.launch {
            try {
                val saved = withContext(io) { persistence.load() }
                if (saved != null && saved.server == service.server) {
                    val identity = service.me(saved)
                    if (identity.accountId != saved.accountId || identity.familyId != saved.familyId) {
                        withContext(io) { persistence.clear() }
                        throw AuthException(AuthErrorKind.InvalidResponse, "登录身份不匹配，请重新登录。")
                    }
                    mutableState.value = AuthenticationState(session = saved, restoring = false)
                } else mutableState.value = AuthenticationState(restoring = false)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                if (error is AuthException && error.kind == AuthErrorKind.Authentication) {
                    try { withContext(io) { persistence.clear() } }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { /* Never activate an unverified saved session. */ }
                }
                mutableState.value = AuthenticationState(restoring = false, error = "暂时无法恢复登录，请重新登录。")
            }
        }
    }

    fun login(username: String, password: String) = authenticate(username, password, false)
    fun register(username: String, password: String) = authenticate(username, password, true)

    private fun authenticate(username: String, password: String, registering: Boolean) {
        if (state.value.loading || state.value.restoring) return
        mutableState.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val session = if (registering) service.register(username, password) else service.login(username, password)
                try { persistenceLock.withLock {
                    withContext(io) { persistence.save(session) }
                    mutableState.value = AuthenticationState(session = session, restoring = false)
                } }
                catch (error: Exception) {
                    if (error is CancellationException) throw error
                    try { service.logout(session) } catch (_: Exception) { }
                    throw AuthException(AuthErrorKind.Storage, "登录信息无法保存在这台设备上，请重试。")
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                mutableState.update { it.copy(loading = false, error = error.message ?: "登录失败，请稍后重试。") }
            }
        }
    }

    fun logout() {
        val captured = state.value.session ?: return
        if (state.value.loading) return
        mutableState.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                try { service.logout(captured) }
                catch (error: AuthException) { if (error.kind != AuthErrorKind.Authentication) throw error }
                persistenceLock.withLock {
                    if (state.value.session?.token == captured.token) {
                        withContext(io) { persistence.clear() }
                        mutableState.value = AuthenticationState(restoring = false)
                    }
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                mutableState.update { it.copy(loading = false, error = "暂时无法退出登录，请检查网络后重试。") }
            }
        }
    }

    fun handleUnauthorized(captured: AuthSession) {
        scope.launch {
            persistenceLock.withLock {
                val current = state.value.session
                if (current?.token != captured.token || current.server != captured.server || state.value.loading) return@withLock
                try { withContext(io) { persistence.clear() } }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { /* A revoked token is never activated without server validation. */ }
                mutableState.value = AuthenticationState(restoring = false, error = "登录已失效，请重新登录。")
            }
        }
    }

    fun clearError() { mutableState.update { it.copy(error = null) } }
}
