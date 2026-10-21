package cn.shinian.app.ui.chat

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.ui.theme.JournalColors as C
import cn.shinian.app.ui.theme.JournalTypography as T

@Composable
internal fun DraftReviewScreen(model: ChatController, repository: BackendRepository, care: Boolean, onSaved: () -> Unit) {
    val draft = model.review ?: return
    val edit = model.edits
    var regenerateConfirmation by remember { mutableStateOf(false) }
    var restorePrevious by remember { mutableStateOf(false) }
    if (edit != null && edit.draftId == draft.id) {
        DraftEditorScreen(model, care)
        return
    }
    BackHandler { if (!model.busy) model.closeReview() }
    ChatPage {
        ChatHeader("回忆预览", care = care, onBack = model::closeReview, enabled = !model.busy, trailing = { Spacer(Modifier.size(48.dp)) })
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(topStart = 6.dp, topEnd = 26.dp, bottomEnd = 26.dp, bottomStart = 6.dp))
                .background(Color(0xFFFFFCF5)).drawBehind { drawRect(C.Soft, size = Size(6.dp.toPx(), size.height)) }
                .padding(start = 26.dp, end = 20.dp, top = 20.dp, bottom = 20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("关于${model.person.relationship} · ${model.person.name}", Modifier.weight(1f), style = T.body(if (care) 19 else 12), color = C.Muted)
                    Text("草稿", style = T.body(if (care) 18 else 12), color = C.ButterInk,
                        modifier = Modifier.clip(RoundedCornerShape(30.dp)).background(C.ButterSoft).padding(horizontal = 10.dp, vertical = 5.dp))
                }
                Text(draft.memory.title, style = if (care) T.body(28, true) else T.story(24), color = C.Ink, lineHeight = if (care) 40.sp else 34.sp)
                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    listOf(draft.memory.dateLabel, draft.memory.location, draft.memory.feeling.value).filterNotNull()
                        .filter { it.isNotBlank() && it !in listOf("未提及", "待补充") }.forEach { value ->
                            Text(value, style = T.body(if (care) 19 else 13), color = C.SecondaryInk)
                        }
                }
                draft.memory.media.firstOrNull()?.let { RemoteChatPhoto(it, repository, Modifier.fillMaxWidth().height(170.dp).clip(RoundedCornerShape(16.dp))) }
                Text(draft.memory.content, style = if (care) T.body(23) else T.story(16), color = C.StoryInk, lineHeight = if (care) 37.sp else 28.sp)
            }
            if (care) {
                ChatButton("编辑文字与时间", secondary = true, care = true, enabled = !model.busy, onClick = model::beginEdit)
                ChatButton("重新生成草稿", secondary = true, care = true, enabled = !model.busy) { regenerateConfirmation = true }
                ChatButton("返回对话", secondary = true, care = true, enabled = !model.busy, onClick = model::closeReview)
            } else Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                listOf(Triple("编辑文字与时间", "edit", model::beginEdit),
                    Triple("重新生成草稿", "history", { regenerateConfirmation = true }),
                    Triple("返回对话", "book", model::closeReview)).forEach { (title, glyph, action) ->
                    TextButton(action, Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(C.Surface), enabled = !model.busy) {
                        Column(Modifier.padding(vertical = 7.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            JournalGlyph(glyph, tint = C.Accent)
                            Text(title, style = T.body(12), color = C.SecondaryInk, textAlign = TextAlign.Center)
                        }
                    }
                }
            }
            if (draft.hasNewNarration) Text("手动修改的草稿已保留。聊天中还有新讲述，请先重新生成并核对，再确认保存。", style = T.body(if (care) 20 else 14), color = C.Danger)
            if (edit != null && edit.draftId != draft.id) {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(C.ButterSoft).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("先前草稿的本机修改仍保留", style = T.body(if (care) 22 else 17, true), color = C.Ink)
                    Text(edit.title, style = T.body(if (care) 22 else 17), color = C.Ink)
                    Text(edit.content, style = T.body(if (care) 21 else 15), color = C.SecondaryInk)
                    ChatButton("复制到当前草稿编辑框", secondary = true, care = care, enabled = !model.busy) { restorePrevious = true }
                }
            }
            model.error?.let { Text(it, style = T.body(if (care) 20 else 14), color = C.Danger) }
            model.latestDraft?.let { latest ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.ButterSoft).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("草稿已在其他设备更新", style = T.body(if (care) 22 else 17, true), color = C.Ink)
                    Text(latest.memory.title, style = T.body(if (care) 21 else 16), color = C.SecondaryInk)
                    Text("请读取最新草稿并核对后，再决定是否重新生成或保存。", style = T.body(if (care) 20 else 14), color = C.SecondaryInk)
                    TextButton(model::readLatestDraft, enabled = !model.busy) { Text("读取最新草稿", style = T.body(if (care) 21 else 16, true)) }
                }
            }
            ChatButton("保存这段回忆", enabled = !draft.hasNewNarration && model.latestDraft == null, busy = model.busy, care = care, modifier = Modifier.testTag("memory.save")) { model.save(onSaved, continueAfterSave = !care) }
            Text("只在你确认后，成为正式回忆", Modifier.fillMaxWidth(), style = T.body(if (care) 18 else 12), color = C.Muted, textAlign = TextAlign.Center)
            Spacer(Modifier.height(12.dp))
        }
    }
    if (regenerateConfirmation) AlertDialog(onDismissRequest = { regenerateConfirmation = false }, title = { Text("重新生成草稿？") },
        text = { Text("AI 将根据当前讲述重新整理，并替换草稿的标题和正文。手改标题和正文也会被替换；已确认的手改时间会保留，新文字将再次提示校对。") },
        dismissButton = { TextButton({ regenerateConfirmation = false }) { Text("保留当前草稿") } },
        confirmButton = { TextButton({ regenerateConfirmation = false; model.regenerate() }) { Text("确认重新生成") } })
    if (restorePrevious) AlertDialog(onDismissRequest = { restorePrevious = false }, title = { Text("恢复先前的本机修改？") },
        text = { Text("将使用先前修改的标题、正文和时间填入当前草稿编辑框。请重新核对，点击保留修改后才会更新草稿。") },
        dismissButton = { TextButton({ restorePrevious = false }) { Text("取消") } },
        confirmButton = { TextButton({ restorePrevious = false; model.restorePreviousEdits() }) { Text("恢复到编辑框") } })
}

@Composable
private fun DraftEditorScreen(model: ChatController, care: Boolean) {
    val draft = model.review ?: return
    val value = model.edits ?: return
    val focus = LocalFocusManager.current
    var discard by remember { mutableStateOf(false) }
    var overwrite by remember { mutableStateOf(false) }
    var timeMenu by remember { mutableStateOf(false) }
    var automaticTimeCheckOpened by remember(draft.id) { mutableStateOf(false) }
    val changed = value.title != draft.memory.title || value.content != draft.memory.content || value.time != draft.memory.time
    fun back() { if (!model.busy) { if (changed) discard = true else model.cancelEdit() } }
    BackHandler { back() }
    LaunchedEffect(draft.id, draft.timeReviewFrom, model.busy) {
        if (draft.timeReviewFrom != null && !automaticTimeCheckOpened && !model.timePreviewOpen && !model.busy) {
            automaticTimeCheckOpened = true
            model.previewTime()
        }
    }
    ChatPage {
        ChatHeader("编辑草稿", care = care, onBack = ::back, enabled = !model.busy, trailing = { Spacer(Modifier.size(48.dp)) })
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            OutlinedTextField(value.title, { model.changeEdits(value.copy(title = it)) }, Modifier.fillMaxWidth().testTag("draft.title"),
                label = { Text("标题") }, enabled = !model.busy, textStyle = T.body(if (care) 23 else 18), maxLines = 5,
                supportingText = { Text("${value.title.length} / 200") }, isError = value.title.length > 200)
            OutlinedTextField(value.content, { model.changeEdits(value.copy(content = it)) }, Modifier.fillMaxWidth().heightIn(min = 260.dp).testTag("draft.body"),
                label = { Text("正文") }, enabled = !model.busy, textStyle = T.body(if (care) 23 else 17),
                supportingText = { Text("${value.content.length} / 100000") }, isError = value.content.length > 100_000)
            Text("时间", style = T.body(if (care) 24 else 19, true), color = C.Ink)
            Box {
                TextButton({ timeMenu = true }, enabled = !model.busy) {
                    Text("记录方式：${timeOptions.firstOrNull { it.first == value.time.status }?.second ?: value.time.status} ▾", style = T.body(if (care) 22 else 16))
                }
                DropdownMenu(timeMenu, { timeMenu = false }) {
                    timeOptions.forEach { (status, title) -> DropdownMenuItem(text = { Text(title, style = T.body(if (care) 22 else 16)) }, onClick = {
                        val text = when (status) { "missing" -> null; "unknown" -> "记不清了"; "withheld" -> "暂时不想说"; else -> value.time.value.orEmpty() }
                        model.changeEdits(value.copy(time = value.time.copy(status = status, value = text, userEdited = true))); timeMenu = false
                    }) }
                }
            }
            if (value.time.status != "missing") OutlinedTextField(value.time.value.orEmpty(), { model.changeEdits(value.copy(time = value.time.copy(value = it, userEdited = true))) },
                Modifier.fillMaxWidth().testTag("draft.time"), label = { Text("例如：2008年夏天，或 2008-06-01") }, textStyle = T.body(if (care) 22 else 16), enabled = !model.busy)
            if (value.time.userEdited) Text("用户修改的时间", style = T.body(if (care) 19 else 13), color = C.SecondaryInk)
            ChatButton("核对标题与正文中的时间", secondary = true, care = care, enabled = value.valid && !model.busy && model.latestDraft == null, modifier = Modifier.testTag("draft.timePreview")) { focus.clearFocus(); model.previewTime() }
            Text("修改时间后，可逐项选择对应文字。原聊天会保留；重新生成也会保留已确认的手改时间。", style = T.body(if (care) 20 else 14), color = C.SecondaryInk)
            Text("你的修改会直接保留，确认保存后成为正式回忆。", style = T.body(if (care) 20 else 14), color = C.Muted)
            model.error?.let { Text(it, style = T.body(if (care) 20 else 14), color = C.Danger) }
            model.latestDraft?.let { latest ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(C.ButterSoft).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("最新草稿 · 本机修改仍保留在上方", style = T.body(if (care) 22 else 17, true), color = C.Ink)
                    Text(latest.memory.title, style = T.body(if (care) 22 else 18, true), color = C.Ink)
                    Text(latest.memory.content, style = T.body(if (care) 21 else 16), color = C.SecondaryInk)
                    Text("时间：${latest.memory.dateLabel}", style = T.body(if (care) 21 else 16), color = C.SecondaryInk)
                    ChatButton("核对后保存本机修改", secondary = true, care = care, enabled = !model.busy) { overwrite = true }
                }
            }
            ChatButton("保留修改", enabled = value.valid && model.latestDraft == null, busy = model.busy, care = care, modifier = Modifier.testTag("draft.keepEdits")) { focus.clearFocus(); model.saveEdits() }
            TextButton(::back, Modifier.fillMaxWidth(), enabled = !model.busy) { Text("取消", style = T.body(if (care) 22 else 16)) }
        }
    }
    if (discard) AlertDialog(onDismissRequest = { discard = false }, title = { Text("放弃本次修改？") }, text = { Text("草稿原有内容会保留。") },
        dismissButton = { TextButton({ discard = false }) { Text("继续编辑") } }, confirmButton = { TextButton({ discard = false; model.cancelEdit() }) { Text("放弃修改") } })
    if (overwrite) AlertDialog(onDismissRequest = { overwrite = false }, title = { Text("保存本机修改到最新草稿？") },
        text = { Text("将用上方编辑的标题、正文和时间替换最新草稿。其他设备的新修改请先核对。") },
        dismissButton = { TextButton({ overwrite = false }) { Text("继续核对") } }, confirmButton = { TextButton({ overwrite = false; model.saveEdits(overwriteLatest = true) }) { Text("保存我的修改") } })
    if (model.timePreviewOpen) DraftTimePreview(model, care)
}

private val timeOptions = listOf("known" to "确定", "approximate" to "大概记得", "unknown" to "记不清", "withheld" to "暂时不想说", "missing" to "待补充")

@Composable
private fun DraftTimePreview(model: ChatController, care: Boolean) {
    val preview = model.timePreview
    var selected by remember(preview) { mutableStateOf(emptySet<String>()) }
    ChatFullDialog("核对时间文字", model::closeTimePreview) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text("原时间：${model.edits?.anchor?.label.orEmpty()}", style = T.body(if (care) 22 else 16), color = C.SecondaryInk)
            Text("修改为：${model.edits?.time?.label.orEmpty()}", style = T.body(if (care) 22 else 16), color = C.Ink)
            if (model.busy) {
                CircularProgressIndicator(Modifier.size(24.dp), color = C.AccentDeep)
                Text(model.progress, style = T.body(if (care) 20 else 16), color = C.SecondaryInk)
            }
            model.error?.let { ChatError(it, "重试核对", care, !model.busy, model::previewTime) }
            preview?.let { value ->
                Text(value.text("message").orEmpty(), style = T.body(if (care) 20 else 15), color = C.SecondaryInk)
                for (field in listOf("title", "summary")) {
                    Text(if (field == "title") "标题" else "正文", style = T.body(if (care) 24 else 19, true), color = C.Ink)
                    val suggestions = value.objects("suggestions").filter { it.text("field") == field }
                    if (suggestions.isEmpty()) Text("未找到对应时间，保留原文。", style = T.body(if (care) 21 else 16), color = C.SecondaryInk)
                    suggestions.forEach { item ->
                        val id = item.text("id").orEmpty()
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(15.dp)).background(C.Surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(item.text("context").orEmpty(), style = T.body(if (care) 22 else 16), color = C.Ink)
                            item.text("after")?.let { after ->
                                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(id in selected, { checked -> selected = if (checked) selected + id else selected - id }, enabled = !model.busy,
                                        modifier = Modifier.testTag("time.suggestion.$id").semantics { contentDescription = "将${item.text("before").orEmpty()}改为$after" })
                                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                        Text("原文：${item.text("before").orEmpty()}", style = T.body(if (care) 21 else 16), color = C.SecondaryInk)
                                        Text("改为：$after", style = T.body(if (care) 21 else 16, true), color = C.Ink)
                                    }
                                }
                            }
                            Text((if (item.flag("ambiguous")) "需您核对 · " else "") + item.text("reason").orEmpty(), style = T.body(if (care) 19 else 14), color = C.SecondaryInk)
                        }
                    }
                    HorizontalDivider(color = C.Line)
                }
                Text("这里只更新编辑框中的文字，点击保存后才会写入回忆。未选中的内容请继续手动核对。", style = T.body(if (care) 20 else 14), color = C.SecondaryInk)
            }
        }
        ChatButton("应用所选", enabled = preview != null && selected.isNotEmpty() && !model.busy, care = care,
            modifier = Modifier.padding(horizontal = 22.dp, vertical = 12.dp).testTag("time.apply")) { model.applyTime(selected) }
    }
}
