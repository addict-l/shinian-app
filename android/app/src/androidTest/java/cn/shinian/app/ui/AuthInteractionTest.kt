package cn.shinian.app.ui

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import cn.shinian.app.ui.auth.*
import cn.shinian.app.ui.theme.ShinianTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AuthInteractionTest {
    @get:Rule val compose=createComposeRule()

    @Test fun registrationValidatesFormatAndMatchingPasswordsBeforeSubmitting() {
        var result:Pair<String,String>?=null
        compose.setContent { ShinianTheme { AuthScreen(AuthUiState(),{_,_->},{name,password->result=name to password},initialMode=AuthMode.Register) } }
        compose.onNodeWithTag("register.submit").performScrollTo().performClick()
        compose.onNodeWithText("请填写家庭账号。").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("register.username").performScrollTo().performTextInput("family_2026")
        compose.onNodeWithTag("register.password").performScrollTo().performTextInput("correctpassword42")
        compose.onNodeWithTag("register.confirmation").performScrollTo().performTextInput("differentpassword")
        compose.onNodeWithTag("register.submit").performScrollTo().performClick()
        compose.onNodeWithText("两次输入的密码不一致。").performScrollTo().assertIsDisplayed()
        compose.runOnIdle{assertNull(result)}
        compose.onNodeWithTag("register.confirmation").performScrollTo().performTextReplacement("correctpassword42")
        compose.onNodeWithTag("register.submit").performScrollTo().performClick()
        compose.runOnIdle{assertEquals("family_2026" to "correctpassword42",result)}
    }

    @Test fun loginKeepsCredentialsEditableAndExplainsAccountRecovery() {
        var attempts=0
        compose.setContent { ShinianTheme { AuthScreen(AuthUiState(),{_,_->attempts++},{_,_->}) } }
        compose.onNodeWithTag("login.submit").performScrollTo().performClick()
        compose.runOnIdle{assertEquals(0,attempts)}
        compose.onNodeWithTag("login.help").performScrollTo().performClick()
        compose.onNodeWithText("找回家庭账号").assertIsDisplayed()
        compose.onNodeWithText("知道了").performClick()
        compose.onNodeWithTag("login.username").performScrollTo().performTextInput("family")
        compose.onNodeWithTag("login.password").performScrollTo().performTextInput("paste_is_allowed")
        compose.onNodeWithTag("login.password.visibility").performClick()
        compose.onNodeWithContentDescription("隐藏密码").assertIsDisplayed()
        compose.onNodeWithTag("login.submit").performScrollTo().performClick()
        compose.runOnIdle{assertEquals(1,attempts)}
    }
}
