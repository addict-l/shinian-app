package cn.shinian.app.ui.auth

import androidx.annotation.DrawableRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.autofill.ContentType
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.contentType
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import cn.shinian.app.R
import cn.shinian.app.ui.theme.JournalColors
import cn.shinian.app.ui.theme.JournalTypography

@Composable
internal fun AuthField(
    title: String,
    placeholder: String,
    @DrawableRes icon: Int,
    value: String,
    onValueChange: (String) -> Unit,
    focusRequester: FocusRequester,
    errorMessage: String?,
    tag: String,
    enabled: Boolean,
    imeAction: ImeAction,
    onImeAction: () -> Unit,
    secure: Boolean = false,
    newPassword: Boolean = false,
) {
    var reveal by remember { mutableStateOf(false) }
    var focused by remember { mutableStateOf(false) }
    val bringIntoView = remember { BringIntoViewRequester() }
    LaunchedEffect(focused) { if (focused) bringIntoView.bringIntoView() }
    val shape = RoundedCornerShape(16.dp)
    Column(
        modifier = Modifier.fillMaxWidth().bringIntoViewRequester(bringIntoView),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(title, style = JournalTypography.body(13, medium = true), color = JournalColors.SecondaryInk)
        Row(
            modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
                .background(JournalColors.Surface, shape)
                .border(
                    width = if (errorMessage != null || focused) 1.5.dp else 1.dp,
                    color = if (errorMessage != null) JournalColors.Danger
                    else if (focused) JournalColors.AuthAccent else JournalColors.CardBorder,
                    shape = shape,
                )
                .padding(start = 16.dp, end = if (secure) 6.dp else 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(painterResource(icon), null, tint = JournalColors.AuthAccent, modifier = Modifier.size(20.dp))
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                enabled = enabled,
                singleLine = true,
                textStyle = JournalTypography.body(16).copy(color = JournalColors.Ink),
                cursorBrush = SolidColor(JournalColors.AuthAccent),
                visualTransformation = if (secure && !reveal) PasswordVisualTransformation() else VisualTransformation.None,
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.None,
                    autoCorrectEnabled = false,
                    keyboardType = if (secure) KeyboardType.Password else KeyboardType.Ascii,
                    imeAction = imeAction,
                ),
                keyboardActions = KeyboardActions(onNext = { onImeAction() }, onGo = { onImeAction() }, onDone = { onImeAction() }),
                modifier = Modifier.weight(1f).heightIn(min = 56.dp).padding(vertical = 16.dp)
                    .focusRequester(focusRequester).onFocusChanged { focused = it.isFocused }
                    .testTag(tag)
                    .semantics {
                        contentDescription = title
                        contentType = if (!secure) ContentType.Username
                        else if (newPassword) ContentType.NewPassword else ContentType.Password
                        if (errorMessage != null) error(errorMessage)
                    },
                decorationBox = { innerTextField ->
                    Box(contentAlignment = Alignment.CenterStart) {
                        if (value.isEmpty()) Text(placeholder, style = JournalTypography.body(16), color = JournalColors.SecondaryInk)
                        innerTextField()
                    }
                },
            )
            if (secure) {
                IconButton(
                    onClick = { reveal = !reveal; focusRequester.requestFocus() },
                    enabled = enabled,
                    modifier = Modifier.size(48.dp).testTag("$tag.visibility"),
                ) {
                    Icon(
                        painterResource(if (reveal) R.drawable.ic_journal_eye_off else R.drawable.ic_journal_eye),
                        contentDescription = if (reveal) "隐藏$title" else "显示$title",
                        tint = JournalColors.SecondaryInk,
                        modifier = Modifier.size(20.dp),
                    )
                }
            }
        }
        errorMessage?.let {
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.Top,
                modifier = Modifier.testTag("$tag.error").semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }) {
                Icon(painterResource(R.drawable.ic_journal_error), null, tint = JournalColors.Ink, modifier = Modifier.size(15.dp))
                Text(it, style = JournalTypography.body(12), color = JournalColors.Ink)
            }
        }
    }
}

@Composable
internal fun AuthButton(title: String, loading: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = !loading,
        shape = CircleShape,
        modifier = modifier.fillMaxWidth().heightIn(min = 56.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = JournalColors.AuthAccent,
            contentColor = Color.White,
            disabledContainerColor = JournalColors.AuthAccent,
            disabledContentColor = Color.White,
        ),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            if (loading) CircularProgressIndicator(modifier = Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
            Text(title, style = JournalTypography.body(16, medium = true))
        }
    }
}

@Composable
internal fun AuthNotice(message: String, modifier: Modifier = Modifier, isError: Boolean = false) {
    Row(
        modifier = modifier.fillMaxWidth().background(JournalColors.Soft.copy(alpha = 0.6f), RoundedCornerShape(14.dp))
            .padding(14.dp).semantics(mergeDescendants = true) { if (isError) liveRegion = LiveRegionMode.Polite },
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Icon(
            painterResource(if (isError) R.drawable.ic_journal_error else R.drawable.ic_journal_info),
            null, tint = JournalColors.SecondaryInk, modifier = Modifier.size(17.dp),
        )
        Text(message, style = JournalTypography.body(13), color = JournalColors.SecondaryInk)
    }
}
