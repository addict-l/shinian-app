package cn.shinian.app.ui

import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.Person
import cn.shinian.app.ui.auth.*
import cn.shinian.app.ui.browse.PersonSelectionScreen
import cn.shinian.app.ui.theme.ShinianTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ResponsiveScreensTest {
    @get:Rule val compose = createComposeRule()
    private fun screenshot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val configuration = instrumentation.targetContext.resources.configuration
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "responsive-screenshots").apply { mkdirs() }
        val image = compose.onRoot().captureToImage().asAndroidBitmap()
        File(folder, "$name-${configuration.orientation}-${configuration.fontScale}.png").outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }

    @Test fun loginAndRegistrationActionsRemainReachable() {
        compose.setContent { ShinianTheme { AuthScreen(AuthUiState(), onLogin = { _, _ -> }, onRegister = { _, _ -> }) } }
        compose.onNodeWithTag("login.submit").performScrollTo().assertIsDisplayed()
        screenshot("login")
        compose.onNodeWithTag("login.register").performScrollTo().performClick()
        compose.onNodeWithTag("register.submit").performScrollTo().assertIsDisplayed()
        screenshot("register")
    }

    @Test fun carePersonActionsRemainReachableWithLongNames() {
        val person = Person("person", "一位名字比较长的家人", "我的亲人", "1950-01-01")
        compose.setContent { ShinianTheme { PersonSelectionScreen(listOf(person), care = true) } }
        compose.onNodeWithTag("member.person").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("members.addAnother").performScrollTo().assertIsDisplayed()
        screenshot("care-person")
    }
}
