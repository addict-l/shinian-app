package cn.shinian.app.ui.browse

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.theme.JournalColors

/** iOS keeps these account pages in the compact JournalTheme structure. */
@Composable
internal fun CareSettingsContent(displayName: String, loading: Boolean, error: String?, onDisplayNameChange: (String) -> Unit,
    onCareChange: (Boolean) -> Unit, onLogout: () -> Unit, onBack: () -> Unit) {
    val requester = remember { FocusRequester() }
    val focus = LocalFocusManager.current
    CarePage {
        CareNativeBackBar("设置", onBack)
        Column(Modifier.weight(1f).imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 22.dp).padding(top = 8.dp, bottom = 24.dp)) {
            CareNativeCard(Modifier.fillMaxWidth().padding(bottom = 20.dp)) {
                Row(Modifier.heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("关怀模式", style = careNativeBody(22f, true), color = CareColors.Ink)
                        Text("大字号、大按钮，更简单的讲述与回看。", style = careNativeBody(18f), color = CareColors.SecondaryInk)
                    }
                    Switch(true, onCareChange, modifier = Modifier.testTag("settings.careMode"),
                        colors = SwitchDefaults.colors(checkedTrackColor = CareColors.Accent))
                }
            }
            CareSettingsLabel("个人展示", top = 0)
            CareNativeCard(Modifier.fillMaxWidth(), padding = 0.dp) {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("显示名称", style = careNativeBody(12f), color = JournalColors.Muted)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        BasicTextField(displayName, onDisplayNameChange, Modifier.weight(1f).focusRequester(requester).testTag("settings.displayName"), singleLine = true,
                            textStyle = careNativeBody(16f).copy(color = CareColors.Ink), cursorBrush = SolidColor(JournalColors.Accent),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done), keyboardActions = KeyboardActions(onDone = { focus.clearFocus() }))
                        IconButton({ requester.requestFocus() }, Modifier.size(44.dp, 28.dp)) { JournalIcon("edit", "修改显示名称", Modifier.size(18.dp), tint = JournalColors.Accent) }
                    }
                }
            }
            CareSettingsLabel("家庭胶片")
            CareNativeCard(Modifier.fillMaxWidth()) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
                    CareNativeIconTile("film")
                    Text("每位家人拥有自己的胶卷，左右滑动翻阅回忆。点击“查看全部家人”可搜索和浏览所有胶卷，长按人物头像可以更换照片。",
                        style = careNativeBody(13.5f, spacing = 7f), color = CareColors.SecondaryInk, modifier = Modifier.weight(1f))
                }
            }
            CareSettingsLabel("关于")
            CareNativeCard(Modifier.fillMaxWidth()) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(54.dp).background(Brush.linearGradient(listOf(JournalColors.AccentGlow, JournalColors.AccentDark)), RoundedCornerShape(16.dp)), contentAlignment = Alignment.Center) {
                        Text("拾", style = careNativeStory(22f), color = Color.White)
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("拾年 · 留住时光", style = careNativeStory(16f), color = CareColors.Ink)
                        Text("界面版本 V1", style = careNativeBody(12f), color = JournalColors.Muted)
                    }
                }
            }
            Row(Modifier.padding(top = 34.dp).fillMaxWidth().height(52.dp).background(CareColors.Surface, CircleShape)
                .border(1.dp, Color(0xFFF0D3CC), CircleShape).clickable(enabled = !loading, role = Role.Button, onClick = onLogout).testTag("settings.logout"),
                horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically) {
                JournalIcon("logout", modifier = Modifier.size(19.dp), tint = JournalColors.Danger)
                Text(if (loading) "正在退出…" else "退出家庭登录", style = careNativeBody(15.5f), color = JournalColors.Danger)
            }
            Text("仅退出当前设备，家庭和回忆会保留。", Modifier.padding(top = 10.dp), style = careNativeBody(12f), color = CareColors.SecondaryInk)
            error?.let { Text(it, Modifier.padding(top = 12.dp), style = careNativeBody(13f), color = JournalColors.Danger) }
        }
    }
}

@Composable
private fun CareSettingsLabel(title: String, top: Int = 22) {
    Text(title, Modifier.padding(horizontal = 6.dp).padding(top = top.dp, bottom = 8.dp),
        style = careNativeBody(12f).copy(letterSpacing = 1.2.sp), color = JournalColors.Muted)
}

@Composable
internal fun CarePrivacyContent(onBack: () -> Unit) {
    CarePage {
        CareNativeBackBar("隐私与数据", onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp).padding(top = 6.dp, bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth().background(CareColors.SageSoft, RoundedCornerShape(24.dp)).padding(18.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(46.dp).background(Color.White, CircleShape), contentAlignment = Alignment.Center) { JournalIcon("shield", tint = JournalColors.SageInk) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("你的回忆，只属于你的家。", style = careNativeStory(16f), color = Color(0xFF4D5E41))
                    Text("只有点击“保存这段回忆”后，草稿才会成为正式回忆。", style = careNativeBody(12.5f, spacing = 5f), color = Color(0xFF6E8160))
                }
            }
            CarePrivacyNativeCard("照片与 AI 对话", "image", listOf(
                "照片选择只显示你授权访问的照片。你可以在系统中管理照片访问范围，也可以使用系统选图入口。只有确认选择的照片才会加入讲述或编辑内容。",
                "对话文字由服务器调用 AI 整理。照片上传到家庭服务器，用于聊天展示、回忆和回忆录，不发送给 AI 分析。"), 14)
            CarePrivacyNativeCard("回忆数据", "heart", listOf(
                "人物和已保存回忆通过家庭账号同步到服务器。草稿需经你确认保存，才会出现在回忆列表中。",
                "尚未发送的对话、制作缓存、显示名称和人物头像保存在本机；头像不会自动上传或同步。"))
            CarePrivacyNativeCard("数据管理", "gear", listOf(
                "可在人物列表和回忆详情中删除相应记录；回忆录支持 PDF 预览与导出。批量导出和账号权限管理暂无服务端接口。"))
        }
    }
}

@Composable
private fun CarePrivacyNativeCard(title: String, icon: String, paragraphs: List<String>, top: Int = 12) {
    CareNativeCard(Modifier.fillMaxWidth().padding(top = top.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            JournalIcon(icon, modifier = Modifier.size(19.dp), tint = JournalColors.Accent)
            Text(title, style = careNativeBody(15.5f, true), color = CareColors.Ink)
        }
        paragraphs.forEachIndexed { index, paragraph -> Text(paragraph, Modifier.padding(top = if (index == 0) 8.dp else 6.dp),
            style = careNativeBody(13f, spacing = 7f), color = CareColors.SecondaryInk) }
    }
}
