package cn.shinian.app.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import cn.shinian.app.R
import cn.shinian.app.ui.theme.JournalColors
import cn.shinian.app.ui.theme.JournalTypography

@Composable
internal fun LoginForm(
    state: AuthUiState,
    username: String,
    password: String,
    onUsernameChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onHelp: () -> Unit,
    onRegister: () -> Unit,
) {
    var submitted by rememberSaveable { mutableStateOf(false) }
    val usernameFocus = remember { FocusRequester() }
    val passwordFocus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    val usernameError = if (submitted && username.isBlank()) "请输入家庭账号。" else null
    val passwordError = if (submitted && password.isEmpty()) "请输入密码。" else null

    fun submit() {
        if (state.loading) return
        submitted = true
        when {
            username.isBlank() -> usernameFocus.requestFocus()
            password.isEmpty() -> passwordFocus.requestFocus()
            else -> { focusManager.clearFocus(); onSubmit() }
        }
    }

    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            AuthField(
                title = "家庭账号", placeholder = "请输入家庭账号", icon = R.drawable.ic_journal_home,
                value = username, onValueChange = onUsernameChange, focusRequester = usernameFocus,
                errorMessage = usernameError, tag = "login.username", enabled = !state.loading,
                imeAction = ImeAction.Next, onImeAction = { passwordFocus.requestFocus() },
            )
            AuthField(
                title = "密码", placeholder = "请输入密码", icon = R.drawable.ic_journal_lock,
                value = password, onValueChange = onPasswordChange, focusRequester = passwordFocus,
                errorMessage = passwordError, tag = "login.password", enabled = !state.loading,
                secure = true, imeAction = ImeAction.Go, onImeAction = ::submit,
            )
        }
        Spacer(Modifier.height(6.dp))
        TextButton(
            onClick = onHelp,
            enabled = !state.loading,
            contentPadding = PaddingValues(horizontal = 0.dp),
            modifier = Modifier.align(Alignment.End).heightIn(min = 48.dp).testTag("login.help"),
        ) { Text("账号或密码需要帮助？", style = JournalTypography.body(13), color = JournalColors.SecondaryInk) }

        state.error?.let {
            Spacer(Modifier.height(18.dp))
            AuthNotice(it, isError = true, modifier = Modifier.testTag("login.error"))
        }
        Spacer(Modifier.height(18.dp))
        AuthButton(
            title = if (state.loading) "正在登录…" else "登录",
            loading = state.loading,
            onClick = ::submit,
            modifier = Modifier.testTag("login.submit"),
        )
        Spacer(Modifier.height(18.dp))
        TextButton(
            onClick = onRegister,
            enabled = !state.loading,
            modifier = Modifier.heightIn(min = 48.dp).testTag("login.register"),
        ) { AuthSwitchLabel("还没有账号？ ", "去注册") }
        Spacer(Modifier.height(18.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(painterResource(R.drawable.ic_journal_shield), null, tint = JournalColors.SecondaryInk, modifier = Modifier.size(15.dp))
            Text(
                "一家人的回忆，在这里好好珍藏",
                style = JournalTypography.body(12),
                color = JournalColors.SecondaryInk,
                textAlign = TextAlign.Center,
                modifier = Modifier.weight(1f, fill = false),
            )
        }
    }
}

internal fun registrationUsernameError(value: String): String? = when {
    value.trim().isEmpty() -> "请填写家庭账号。"
    !Regex("^[A-Za-z0-9_]{3,32}$").matches(value.trim()) -> "账号须为 3–32 位字母、数字或下划线。"
    else -> null
}

internal fun registrationPasswordError(value: String): String? = when {
    value.isEmpty() -> "请设置密码。"
    value.codePointCount(0, value.length) !in 8..128 -> "密码需要 8–128 位。"
    value.isBlank() -> "密码不能只包含空格。"
    else -> null
}

internal fun registrationConfirmationError(value: String, password: String): String? = when {
    value.isEmpty() -> "请再次输入密码。"
    value != password -> "两次输入的密码不一致。"
    else -> null
}

@Composable
internal fun RegistrationForm(
    state: AuthUiState,
    username: String,
    password: String,
    confirmation: String,
    onUsernameChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onConfirmationChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onLogin: () -> Unit,
) {
    var submitted by rememberSaveable { mutableStateOf(false) }
    val usernameFocus = remember { FocusRequester() }
    val passwordFocus = remember { FocusRequester() }
    val confirmationFocus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    val usernameError = if (submitted) registrationUsernameError(username) else null
    val passwordError = if (submitted) registrationPasswordError(password) else null
    val confirmationError = if (submitted) registrationConfirmationError(confirmation, password) else null

    fun submit() {
        if (state.loading) return
        submitted = true
        when {
            registrationUsernameError(username) != null -> usernameFocus.requestFocus()
            registrationPasswordError(password) != null -> passwordFocus.requestFocus()
            registrationConfirmationError(confirmation, password) != null -> confirmationFocus.requestFocus()
            else -> { focusManager.clearFocus(); onSubmit() }
        }
    }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        AuthNotice(
            "一家人共用一个账号，在各自的设备上记录和查看家庭回忆。",
            modifier = Modifier.testTag("register.notice"),
        )
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            AuthField(
                title = "家庭账号", placeholder = "为家庭取一个账号", icon = R.drawable.ic_journal_home,
                value = username, onValueChange = onUsernameChange, focusRequester = usernameFocus,
                errorMessage = usernameError, tag = "register.username", enabled = !state.loading,
                imeAction = ImeAction.Next, onImeAction = { passwordFocus.requestFocus() },
            )
            Text(
                "3–32 位字母、数字或下划线，不区分大小写。",
                style = JournalTypography.body(12), color = JournalColors.SecondaryInk,
                modifier = Modifier.fillMaxWidth(),
            )
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                AuthField(
                    title = "设置密码", placeholder = "至少 8 位密码", icon = R.drawable.ic_journal_lock,
                    value = password, onValueChange = onPasswordChange, focusRequester = passwordFocus,
                    errorMessage = passwordError, tag = "register.password", enabled = !state.loading,
                    secure = true, newPassword = true, imeAction = ImeAction.Next,
                    onImeAction = { confirmationFocus.requestFocus() },
                )
                if (passwordError == null) {
                    Text("建议组合使用字母、数字和符号。", style = JournalTypography.body(12), color = JournalColors.SecondaryInk)
                }
            }
            AuthField(
                title = "确认密码", placeholder = "请再次输入密码", icon = R.drawable.ic_journal_lock,
                value = confirmation, onValueChange = onConfirmationChange, focusRequester = confirmationFocus,
                errorMessage = confirmationError, tag = "register.confirmation", enabled = !state.loading,
                secure = true, newPassword = true, imeAction = ImeAction.Done, onImeAction = ::submit,
            )
        }
        state.error?.let { AuthNotice(it, isError = true, modifier = Modifier.testTag("register.error")) }
        AuthButton(
            title = if (state.loading) "正在创建家庭…" else "注册并进入家庭",
            loading = state.loading, onClick = ::submit, modifier = Modifier.testTag("register.submit"),
        )
        TextButton(
            onClick = onLogin,
            enabled = !state.loading,
            modifier = Modifier.heightIn(min = 48.dp).testTag("register.login"),
        ) { AuthSwitchLabel("已有账号？ ", "返回登录") }
    }
}
