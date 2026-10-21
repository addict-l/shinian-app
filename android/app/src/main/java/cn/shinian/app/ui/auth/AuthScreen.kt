package cn.shinian.app.ui.auth

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.R
import cn.shinian.app.ui.theme.JournalBackdrop
import cn.shinian.app.ui.theme.JournalColors
import cn.shinian.app.ui.theme.JournalDimensions
import cn.shinian.app.ui.theme.JournalTypography
import cn.shinian.app.ui.theme.ShinianTheme

data class AuthUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val restoring: Boolean = false,
)

enum class AuthMode { Login, Register }

/** Authentication presentation only; credentials are submitted through the callbacks. */
@Composable
fun AuthScreen(
    state: AuthUiState,
    onLogin: (String, String) -> Unit,
    onRegister: (String, String) -> Unit,
    modifier: Modifier = Modifier,
    initialMode: AuthMode = AuthMode.Login,
    onClearError: () -> Unit = {},
) {
    var mode by rememberSaveable { mutableStateOf(initialMode) }
    var showsHelp by rememberSaveable { mutableStateOf(false) }
    // Keep the login identity when returning from registration, as the iOS stack does.
    var loginUsername by rememberSaveable { mutableStateOf("") }
    var registerUsername by rememberSaveable { mutableStateOf("") }
    // Passwords stay only in composition memory, never in saved-instance state or logs.
    var loginPassword by remember { mutableStateOf("") }
    var registerPassword by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    val focus = LocalFocusManager.current

    fun changeMode(next: AuthMode) {
        focus.clearFocus()
        onClearError()
        if (next == AuthMode.Login) {
            registerPassword = ""
            confirmation = ""
        }
        mode = next
    }

    BackHandler(enabled = mode == AuthMode.Register) {
        if (!state.loading) changeMode(AuthMode.Login)
    }

    JournalBackdrop(modifier.fillMaxSize()) {
        if (state.restoring) {
            Column(
                modifier = Modifier.fillMaxSize().systemBarsPadding().padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                CircularProgressIndicator(
                    color = JournalColors.AuthAccent,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(28.dp),
                )
                Spacer(Modifier.height(16.dp))
                Text("正在恢复家庭登录…", style = JournalTypography.body(15), color = JournalColors.SecondaryInk)
            }
        } else {
            Column(Modifier.fillMaxSize().systemBarsPadding().imePadding()) {
                if (mode == AuthMode.Register) {
                    RegistrationBar(enabled = !state.loading, onBack = { changeMode(AuthMode.Login) })
                }
                AuthPage(
                    title = if (mode == AuthMode.Login) "欢迎回家" else "开启家庭回忆",
                    subtitle = if (mode == AuthMode.Login) "把平凡的日子，收藏成家的故事。"
                    else "从今天起，一起留下值得珍藏的时光。",
                    compact = mode == AuthMode.Register,
                ) {
                    if (mode == AuthMode.Login) {
                        LoginForm(
                            state = state,
                            username = loginUsername,
                            password = loginPassword,
                            onUsernameChange = { loginUsername = it; onClearError() },
                            onPasswordChange = { loginPassword = it; onClearError() },
                            onSubmit = { onLogin(loginUsername, loginPassword) },
                            onHelp = { focus.clearFocus(); showsHelp = true },
                            onRegister = { changeMode(AuthMode.Register) },
                        )
                    } else {
                        RegistrationForm(
                            state = state,
                            username = registerUsername,
                            password = registerPassword,
                            confirmation = confirmation,
                            onUsernameChange = { registerUsername = it; onClearError() },
                            onPasswordChange = { registerPassword = it; onClearError() },
                            onConfirmationChange = { confirmation = it; onClearError() },
                            onSubmit = { onRegister(registerUsername, registerPassword) },
                            onLogin = { changeMode(AuthMode.Login) },
                        )
                    }
                }
            }
        }
    }

    if (showsHelp) {
        AlertDialog(
            onDismissRequest = { showsHelp = false },
            title = { Text("找回家庭账号", style = JournalTypography.body(20, medium = true)) },
            text = {
                Text(
                    "一家人使用同一个家庭账号。账号不区分大小写；忘记账号或密码时，请联系服务维护者协助恢复，目前不支持自助找回密码。",
                    style = JournalTypography.body(15),
                    color = JournalColors.SecondaryInk,
                )
            },
            confirmButton = { TextButton(onClick = { showsHelp = false }) { Text("知道了") } },
            containerColor = JournalColors.Surface,
            titleContentColor = JournalColors.Ink,
        )
    }
}

@Composable
private fun RegistrationBar(enabled: Boolean, onBack: () -> Unit) {
    Box(Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
        IconButton(onClick = onBack, enabled = enabled, modifier = Modifier.align(Alignment.CenterStart)) {
            Icon(painterResource(R.drawable.ic_journal_back), "返回登录", tint = JournalColors.AuthAccent)
        }
        Text(
            "创建账号",
            style = JournalTypography.body(17, medium = true),
            color = JournalColors.Ink,
            modifier = Modifier.align(Alignment.Center).semantics { heading() },
        )
    }
}

@Composable
private fun AuthPage(
    title: String,
    subtitle: String,
    compact: Boolean,
    content: @Composable ColumnScope.() -> Unit,
) {
    val density = LocalDensity.current
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val artworkHeight: Dp = if (density.fontScale >= 1.5f) 72.dp else {
            (maxHeight * if (compact) 0.18f else 0.32f).coerceIn(72.dp, if (compact) 112.dp else 240.dp)
        }
        Column(
            modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).heightIn(min = maxHeight),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            WelcomeArtwork(artworkHeight)
            Column(
                modifier = Modifier.widthIn(max = 480.dp).fillMaxWidth()
                    .padding(horizontal = JournalDimensions.Gutter).padding(bottom = 28.dp).offset(y = (-8).dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(24.dp),
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        "拾年 · 留住时光",
                        style = JournalTypography.body(12, medium = true).copy(letterSpacing = 2.sp),
                        color = JournalColors.SecondaryInk,
                        textAlign = TextAlign.Center,
                    )
                    Text(
                        title,
                        style = JournalTypography.story(32),
                        color = JournalColors.Ink,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.semantics { heading() },
                    )
                    Text(subtitle, style = JournalTypography.body(14), color = JournalColors.SecondaryInk, textAlign = TextAlign.Center)
                }
                content()
            }
        }
    }
}

@Composable
private fun WelcomeArtwork(height: Dp) {
    Image(
        painter = painterResource(R.drawable.journal_welcome),
        contentDescription = null,
        contentScale = ContentScale.Crop,
        modifier = Modifier.widthIn(max = 600.dp).fillMaxWidth().height(height)
            .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
            .drawWithContent {
                drawContent()
                drawRect(
                    brush = Brush.verticalGradient(
                        0f to Color.Transparent,
                        0.12f to Color.Black,
                        0.58f to Color.Black,
                        1f to Color.Transparent,
                    ),
                    blendMode = BlendMode.DstIn,
                )
            },
    )
}

@Composable
internal fun AuthSwitchLabel(lead: String, action: String) {
    Text(
        buildAnnotatedString {
            withStyle(SpanStyle(color = JournalColors.SecondaryInk)) { append(lead) }
            withStyle(SpanStyle(color = JournalColors.AuthAccent, fontWeight = FontWeight.Bold)) { append(action) }
        },
        style = JournalTypography.body(15),
        textAlign = TextAlign.Center,
    )
}

@Preview(name = "登录", widthDp = 393, heightDp = 852, showSystemUi = true)
@Composable
private fun LoginPreview() = ShinianTheme { AuthScreen(AuthUiState(), { _, _ -> }, { _, _ -> }) }

@Preview(name = "注册", widthDp = 393, heightDp = 852, showSystemUi = true)
@Composable
private fun RegistrationPreview() = ShinianTheme {
    AuthScreen(AuthUiState(), { _, _ -> }, { _, _ -> }, initialMode = AuthMode.Register)
}
