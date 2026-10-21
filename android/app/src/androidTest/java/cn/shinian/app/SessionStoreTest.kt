package cn.shinian.app

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import cn.shinian.app.data.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SessionStoreTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val store = SessionStore(context)
    private val session = AuthSession("https://example.com", "account-a", "family-a", "test_family", false, "test-private-device-token", "2030-01-01T00:00:00Z")
    @After fun clearTestSession() { store.clear() }

    @Test fun keystoreRoundTripNeverStoresTokenInPlainPreferences() {
        store.save(session)
        assertEquals(session, SessionStore(context).load())
        val values = context.getSharedPreferences(SessionStore.PREFERENCES_NAME, 0).all.values.joinToString()
        assertFalse(values.contains(session.token))
        assertFalse(values.contains(session.familyId))
        val before = values
        store.save(session)
        val after = context.getSharedPreferences(SessionStore.PREFERENCES_NAME, 0).all.values.joinToString()
        assertNotEquals(before, after)
        assertEquals(session, store.load())
    }

    @Test fun damagedEncryptedSessionIsDiscardedAndNextLoginWorks() {
        store.save(session)
        context.getSharedPreferences(SessionStore.PREFERENCES_NAME, 0).edit().putString("session_ciphertext", "damaged-data").commit()
        assertNull(store.load())
        assertTrue(context.getSharedPreferences(SessionStore.PREFERENCES_NAME, 0).all.isEmpty())
        store.save(session)
        assertEquals(session, store.load())
    }
}
