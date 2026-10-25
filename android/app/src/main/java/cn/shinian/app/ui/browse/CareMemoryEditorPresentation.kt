package cn.shinian.app.ui.browse

import androidx.compose.foundation.background
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.data.InformationDimension
import cn.shinian.app.data.Memory
import cn.shinian.app.data.MemoryEdit
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.theme.JournalColors

/** The iOS destination is a grouped system Form, including in care mode. */
@Composable
internal fun CareMemoryEditorContent(edit: MemoryEdit, latest: Memory?, busy: Boolean, error: String?,
    onEdit: (MemoryEdit) -> Unit, onBack: () -> Unit, onSave: () -> Unit, onTimePreview: () -> Unit,
    onReadLatest: () -> Unit, onResolve: () -> Unit, onAddPhotos: () -> Unit,
    photos: @Composable ColumnScope.() -> Unit) {
    val enabled = !busy
    CareBackdrop {
        Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding()) {
            Box(Modifier.padding(top = 16.dp).fillMaxWidth().height(44.dp).padding(horizontal = 16.dp), contentAlignment = Alignment.Center) {
                Text("编辑回忆", style = careNativeBody(17f, true), color = CareColors.Ink)
                CareNativeFormBarButton("取消", Modifier.align(Alignment.CenterStart), enabled, onBack)
                CareNativeFormBarButton("保存修改", Modifier.align(Alignment.CenterEnd).testTag("memory.saveEdits"), enabled && edit.isValid && latest == null, onSave)
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(top = 24.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(32.dp)) {
                CareFormSection("标题") { CareFormTextField(edit.title, { onEdit(edit.copy(title = it)) }, "回忆标题", "memory.editTitle", enabled) }
                CareFormSection("正文") { CareFormTextField(edit.content, { onEdit(edit.copy(content = it)) }, "", "memory.editBody", enabled, multiline = true, minimumHeight = 250) }
                CareFormSection("时间") {
                    CareFormDimension("时间", edit.time, "memory.edit.time", enabled) { onEdit(edit.copy(time = it)) }
                    CareFormDivider()
                    Row(Modifier.fillMaxWidth().heightIn(min = 62.dp).clickable(enabled = enabled && edit.isValid && latest == null, role = Role.Button, onClick = onTimePreview)
                        .testTag("memory.timePreview").padding(horizontal = 16.dp, vertical = 15.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        CareSymbol("textCheck", 22.dp, tint = CareColors.Ink)
                        Text("核对标题与正文中的时间", style = careNativeBody(22f), color = CareColors.Ink, modifier = Modifier.weight(1f))
                    }
                    CareFormDivider()
                    Text("逐项核对后选择要更新的文字，保存修改后才会写入回忆。", style = careNativeBody(13f), color = CareColors.SecondaryInk, modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp))
                }
                CareFormSection("地点") { CareFormDimension("地点", edit.place, "memory.edit.place", enabled) { onEdit(edit.copy(place = it)) } }
                CareFormSection("感受") { CareFormDimension("感受", edit.feeling, "memory.edit.feeling", enabled) { onEdit(edit.copy(feeling = it)) } }
                CareFormSection("照片") {
                    photos()
                    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).clickable(enabled = enabled, role = Role.Button, onClick = onAddPhotos)
                        .testTag("memory.addPhotos").padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        JournalIcon("plus", modifier = Modifier.size(22.dp), tint = JournalColors.Accent)
                        Text("添加照片", style = careNativeBody(22f), color = JournalColors.Accent)
                    }
                    CareFormDivider()
                    Text("照片和文字会在保存修改后一起更新。原始聊天中的照片会保留，整段删除时一并清除。", style = careNativeBody(13f), color = CareColors.SecondaryInk, modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp))
                }
                error?.let { message -> CareFormSection {
                    Text(message, style = careNativeBody(22f), color = CareColors.DangerInk, modifier = Modifier.padding(16.dp))
                    CareFormDivider()
                    TextButton(onReadLatest, enabled = enabled, modifier = Modifier.fillMaxWidth()) { Text("读取最新版本（保留本机修改）", style = careNativeBody(22f), color = JournalColors.Accent) }
                } }
                latest?.let { cloud -> CareFormSection("最新版本 · 本机修改仍保留在上方", wrapTitle = true) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(cloud.title, style = careNativeBody(17f, true), color = CareColors.Ink)
                        Text(cloud.content, style = careNativeBody(22f), color = CareColors.Ink)
                        Text("时间：${cloud.dateLabel}\n地点：${cloud.place.label}\n感受：${cloud.feeling.label}\n照片：${cloud.media.size} 张", style = careNativeBody(22f), color = CareColors.Ink)
                        Text("核对后保存会使用本机文字、信息和照片选择，替换此最新版本。", style = careNativeBody(22f), color = CareColors.Ink)
                        TextButton(onResolve, enabled = enabled, modifier = Modifier.testTag("memory.resolveConflict")) { Text("核对后保存本机修改", style = careNativeBody(22f), color = JournalColors.Accent) }
                    }
                } }
            }
        }
        if (busy) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(Modifier.background(CareColors.Surface.copy(alpha = .94f), RoundedCornerShape(12.dp)).padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(Modifier.size(22.dp), color = JournalColors.Accent)
                Text("正在处理…", style = careNativeBody(22f), color = CareColors.Ink)
            }
        }
    }
}

@Composable
internal fun CareFormSection(title: String? = null, wrapTitle: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        // The native Form header has a tighter line box than a 22pt body paragraph.
        title?.let {
            val lineBox = with(LocalDensity.current) { 28.5.sp.toDp() }
            Text(it, style = careNativeBody(22f).copy(lineHeight = 28.5.sp), color = CareColors.Ink,
                modifier = Modifier.padding(horizontal = 16.dp).then(if (wrapTitle) Modifier else Modifier.height(lineBox)))
        }
        Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(26.dp)), content = content)
    }
}

@Composable
internal fun CareFormDivider() { HorizontalDivider(Modifier.padding(horizontal = 16.dp), thickness = .5.dp, color = Color(0xFFE5E5E5)) }

@Composable
private fun CareNativeFormBarButton(title: String, modifier: Modifier, enabled: Boolean, onClick: () -> Unit) {
    Box(modifier.height(44.dp).careShadow(CircleShape, 14.dp, 8.dp, .08f).background(Color(0xFFFFFCF1), CircleShape)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(horizontal = 12.dp), contentAlignment = Alignment.Center) {
        Text(title, style = careNativeBody(22f), color = if (enabled) CareColors.Ink else JournalColors.Muted)
    }
}

@Composable
internal fun CareFormTextField(value: String, onChange: (String) -> Unit, placeholder: String, tag: String,
    enabled: Boolean, multiline: Boolean = false, minimumHeight: Int = 62) {
    BasicTextField(value, onChange, Modifier.fillMaxWidth().heightIn(min = minimumHeight.dp).padding(horizontal = if (multiline) 22.dp else 16.dp, vertical = if (multiline) 20.dp else 15.dp).testTag(tag)
        .semantics { contentDescription = placeholder.ifEmpty { "正文" } }, enabled = enabled,
        textStyle = careNativeBody(22f).copy(color = CareColors.Ink), singleLine = !multiline,
        cursorBrush = SolidColor(JournalColors.Accent), decorationBox = { inner -> Box {
            if (value.isEmpty() && placeholder.isNotEmpty()) Text(placeholder, style = careNativeBody(22f), color = JournalColors.Placeholder)
            inner()
        } })
}

@Composable
private fun CareFormDimension(title: String, value: InformationDimension, tag: String, enabled: Boolean, onChange: (InformationDimension) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val statuses = listOf("known" to "确定", "approximate" to "大概记得", "unknown" to "记不清", "withheld" to "暂时不想说", "missing" to "待补充")
    Box {
        Row(Modifier.fillMaxWidth().heightIn(min = 62.dp).clickable(enabled = enabled, role = Role.Button) { expanded = true }.testTag("$tag.status").padding(horizontal = 16.dp, vertical = 15.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("记录方式", style = careNativeBody(22f), color = CareColors.Ink)
            Spacer(Modifier.weight(1f))
            Text(statuses.firstOrNull { it.first == value.status }?.second ?: "待补充", style = careNativeBody(17f), color = JournalColors.Accent)
            Canvas(Modifier.size(12.dp, 18.dp)) {
                val color = JournalColors.Accent
                val stroke = 1.5.dp.toPx()
                drawLine(color, Offset(2.dp.toPx(), 6.dp.toPx()), Offset(6.dp.toPx(), 2.dp.toPx()), stroke)
                drawLine(color, Offset(6.dp.toPx(), 2.dp.toPx()), Offset(10.dp.toPx(), 6.dp.toPx()), stroke)
                drawLine(color, Offset(2.dp.toPx(), 12.dp.toPx()), Offset(6.dp.toPx(), 16.dp.toPx()), stroke)
                drawLine(color, Offset(6.dp.toPx(), 16.dp.toPx()), Offset(10.dp.toPx(), 12.dp.toPx()), stroke)
            }
        }
        DropdownMenu(expanded, { expanded = false }) {
            statuses.forEach { (status, label) -> DropdownMenuItem(text = { Text(label) }, onClick = {
                expanded = false
                val next = when (status) { "missing" -> null; "unknown" -> "记不清了"; "withheld" -> "暂时不想说"; else -> value.value.orEmpty() }
                onChange(value.copy(status = status, value = next, sourceMessageIds = emptyList(), userEdited = true))
            }) }
        }
    }
    if (value.status != "missing") {
        CareFormDivider()
        CareFormTextField(value.value.orEmpty(), { onChange(value.copy(value = it, sourceMessageIds = emptyList(), userEdited = true)) },
            if (title == "时间") "例如：2008年夏天，或 2008-06-01" else "写下你的说明", tag, enabled)
    }
}
