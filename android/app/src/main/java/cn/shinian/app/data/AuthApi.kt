package cn.shinian.app.data

import cn.shinian.app.BuildConfig
import java.io.IOException
import java.io.InterruptedIOException
import java.util.Locale
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

/** The same revocable device-session API used by the iOS application. */
class AuthApi(
    baseUrl: String = BuildConfig.API_BASE_URL,
    httpClient: OkHttpClient = BackendTransport.client,
) : AuthService {
    private val base: HttpUrl = validatedBase(baseUrl)
    override val server: String = base.toString().trimEnd('/')
    private val json = Json { ignoreUnknownKeys = true }
    private val client = httpClient.newBuilder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    override suspend fun register(username: String, password: String): AuthSession =
        authenticate("register", username, password)

    override suspend fun login(username: String, password: String): AuthSession =
        authenticate("login", username, password)

    override suspend fun me(session: AuthSession): AccountIdentity {
        val value = decode<AccountIdentity>(request("me", "GET", session = session))
        if (!validIdentity(value.accountId, value.familyId, value.username)) invalidResponse()
        return value
    }

    override suspend fun logout(session: AuthSession) {
        request("logout", "POST", session = session)
    }

    private suspend fun authenticate(operation: String, username: String, password: String): AuthSession {
        val name = username.trim().lowercase(Locale.ROOT)
        if (name.isEmpty() || password.isEmpty()) {
            throw AuthException(AuthErrorKind.Rejected, "请输入账号和密码。")
        }
        val body = json.encodeToString(AccountCredentials(name, password))
        val value = decode<LoginResponse>(request(operation, "POST", body = body))
        if (!validIdentity(value.accountId, value.familyId, value.username) ||
            value.token.isBlank() || value.token.length > 128 || value.expiresAt.isBlank()
        ) invalidResponse()
        return AuthSession(server, value.accountId, value.familyId, value.username,
            value.legacy, value.token, value.expiresAt)
    }

    private suspend fun request(
        operation: String,
        method: String,
        body: String? = null,
        session: AuthSession? = null,
    ): String {
        if (session != null && session.server != server) {
            throw AuthException(AuthErrorKind.Authentication, "服务器已变更，请重新登录。")
        }
        val url = base.newBuilder().addPathSegments("api/v1/auth/$operation").build()
        val request = Request.Builder().url(url).header("Accept", "application/json")
            .header("Cache-Control", "no-store")
        if (session != null) request.header("Authorization", "Bearer ${session.token}")
        when (method) {
            "GET" -> request.get()
            "POST" -> request.post((body ?: "").toRequestBody(JSON_MEDIA_TYPE))
        }
        try {
            return withContext(Dispatchers.IO) {
                client.newCall(request.build()).awaitResponse().use { response ->
                    val text = response.body?.string().orEmpty()
                    if (!response.isSuccessful) throw responseError(operation, response.code, text)
                    text
                }
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: AuthException) {
            throw error
        } catch (error: InterruptedIOException) {
            throw AuthException(AuthErrorKind.Timeout, "请求超时，请稍后重试。")
        } catch (error: IOException) {
            throw AuthException(AuthErrorKind.Network, "无法连接服务器，请检查网络后重试。")
        } catch (error: IllegalArgumentException) {
            throw AuthException(AuthErrorKind.InvalidResponse, "服务器响应无效。")
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

    private inline fun <reified T> decode(body: String): T = try {
        json.decodeFromString<T>(body)
    } catch (error: SerializationException) {
        invalidResponse()
    } catch (error: IllegalArgumentException) {
        invalidResponse()
    }

    private fun responseError(operation: String, status: Int, body: String): AuthException {
        val detail = runCatching {
            val value = json.parseToJsonElement(body).jsonObject["detail"] as? JsonPrimitive
            value?.takeIf { it.isString }?.content?.trim()?.takeIf { it.isNotEmpty() }
        }.getOrNull()
        if (status == 401) {
            val message = if (operation == "login" || operation == "register")
                "账号或密码不正确，请重新输入。" else "登录已失效，请重新登录。"
            return AuthException(AuthErrorKind.Authentication, message, status)
        }
        val fallback = when (status) {
            409 -> "这个账号已被使用，请换一个账号。"
            422 -> "账号格式或密码不符合要求，请检查后重试。"
            429 -> "尝试过于频繁，请稍后再试。"
            in 500..599 -> "服务器暂时无法处理请求，请稍后重试。"
            else -> "请求失败（HTTP $status）。"
        }
        return AuthException(AuthErrorKind.Rejected, detail ?: fallback, status)
    }

    private fun validIdentity(accountId: String, familyId: String, username: String): Boolean =
        validUuid(accountId) && validUuid(familyId) && username.isNotBlank()

    private fun validUuid(value: String): Boolean = runCatching {
        UUID.fromString(value).toString().equals(value, ignoreCase = true)
    }.getOrDefault(false)

    private fun invalidResponse(): Nothing =
        throw AuthException(AuthErrorKind.InvalidResponse, "服务器返回的数据格式不匹配。")

    private companion object {
        val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

        fun validatedBase(value: String): HttpUrl {
            val url = value.trim().trimEnd('/').plus('/').toHttpUrlOrNull()
                ?: throw AuthException(AuthErrorKind.InvalidResponse, "服务器地址无效，请检查应用配置。")
            val debugLocal = BuildConfig.DEBUG && url.host in setOf("localhost", "127.0.0.1", "10.0.2.2", "::1")
            if ((!url.isHttps && !debugLocal) || url.username.isNotEmpty() || url.password.isNotEmpty() ||
                url.query != null || url.fragment != null
            ) throw AuthException(AuthErrorKind.InvalidResponse, "请配置 HTTPS 服务器；本机调试仅允许本地服务器。")
            return url
        }
    }

    @Serializable
    private data class AccountCredentials(val username: String, val password: String)

    @Serializable
    private data class LoginResponse(
        @SerialName("account_id") val accountId: String,
        @SerialName("family_id") val familyId: String,
        val username: String,
        val legacy: Boolean = false,
        val token: String,
        @SerialName("expires_at") val expiresAt: String,
    )
}
