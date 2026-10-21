package cn.shinian.app.data

import java.security.MessageDigest
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AuthSession(
    val server: String,
    @SerialName("account_id") val accountId: String,
    @SerialName("family_id") val familyId: String,
    val username: String,
    val legacy: Boolean = false,
    val token: String,
    @SerialName("expires_at") val expiresAt: String,
) {
    val scopeKey: String
        get() = MessageDigest.getInstance("SHA-256")
            .digest("$server\n$accountId\n$familyId".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }

    override fun toString(): String =
        "AuthSession(server=$server, accountId=$accountId, familyId=$familyId, " +
            "username=$username, legacy=$legacy, token=[REDACTED], expiresAt=$expiresAt)"
}

@Serializable
data class AccountIdentity(
    @SerialName("account_id") val accountId: String,
    @SerialName("family_id") val familyId: String,
    val username: String,
    val legacy: Boolean = false,
)

enum class AuthErrorKind { Authentication, Timeout, Network, Rejected, InvalidResponse, Storage }

class AuthException(
    val kind: AuthErrorKind,
    message: String,
    val statusCode: Int? = null,
) : Exception(message)

interface AuthService {
    val server: String
    suspend fun register(username: String, password: String): AuthSession
    suspend fun login(username: String, password: String): AuthSession
    suspend fun me(session: AuthSession): AccountIdentity
    suspend fun logout(session: AuthSession)
}

interface SessionPersistence {
    fun load(): AuthSession?
    fun save(session: AuthSession)
    fun clear()
}
