package cn.shinian.app.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/** Preferences contain only ciphertext and its IV; the AES key never leaves Android Keystore. */
class SessionStore(context: Context) : SessionPersistence {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }

    @Synchronized
    override fun load(): AuthSession? {
        val encrypted: String?
        val iv: String?
        try {
            encrypted = preferences.getString(CIPHERTEXT, null)
            iv = preferences.getString(IV, null)
        } catch (error: Exception) {
            discardUnreadableSession()
            return null
        }
        if (encrypted == null && iv == null) return null
        if (encrypted == null || iv == null) {
            discardUnreadableSession()
            return null
        }
        return try {
            val key = keyStore().getKey(KEY_ALIAS, null) as? SecretKey
                ?: throw IllegalStateException("Session key is unavailable")
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            val plain = cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP))
            json.decodeFromString<AuthSession>(plain.toString(Charsets.UTF_8)).also { session ->
                require(session.server.isNotBlank() && session.accountId.isNotBlank() &&
                    session.familyId.isNotBlank() && session.username.isNotBlank() &&
                    session.token.isNotBlank() && session.expiresAt.isNotBlank())
            }
        } catch (error: Exception) {
            discardUnreadableSession()
            null
        }
    }

    @Synchronized
    override fun save(session: AuthSession) {
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, encryptionKey())
            val data = cipher.doFinal(json.encodeToString(session).toByteArray(Charsets.UTF_8))
            val saved = preferences.edit().clear()
                .putString(CIPHERTEXT, Base64.encodeToString(data, Base64.NO_WRAP))
                .putString(IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .commit()
            if (!saved) throw IllegalStateException("Session preferences were not saved")
        } catch (error: Exception) {
            throw AuthException(AuthErrorKind.Storage, "登录信息无法保存在这台设备上，请重试。")
        }
    }

    @Synchronized
    override fun clear() {
        if (!preferences.edit().clear().commit()) {
            throw AuthException(AuthErrorKind.Storage, "登录信息暂时无法清除，请重试。")
        }
    }

    private fun discardUnreadableSession() {
        runCatching { preferences.edit().clear().commit() }
        // Regenerate an invalidated/missing key on the next successful login.
        runCatching { keyStore().deleteEntry(KEY_ALIAS) }
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    private fun encryptionKey(): SecretKey {
        val existing = keyStore().getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build())
        }.generateKey()
    }

    companion object {
        const val PREFERENCES_NAME = "shinian_auth"
        private const val KEY_ALIAS = "cn.shinian.app.auth-session.v1"
        private const val CIPHERTEXT = "session_ciphertext"
        private const val IV = "session_iv"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
