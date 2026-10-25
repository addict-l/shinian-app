package cn.shinian.app.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.care.CareTypography as T

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun CareDraftReview(model: ChatController, repository: BackendRepository, onRegenerate: () -> Unit,
    onRestorePrevious: () -> Unit, onSaved: () -> Unit) {
    val draft = model.review ?: return
    Box(Modifier.fillMaxSize()) {
        CarePage {
            CareToolbar("回忆草稿", model::closeReview, backTitle = "讲述", enabled = !model.busy, backTag = "chat.back")
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(top = 4.dp, bottom = 16.dp).testTag("care.draft.scroll"),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(Modifier.fillMaxWidth().background(CareColors.SageSoft, RoundedCornerShape(22.dp)).padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                    CareSymbol("eye", 20.dp, tint = CareColors.SageInk)
                    Text("看看有没有记错，满意了再保存。", style = T.body(20, true), color = CareColors.SageInk)
                }
                model.error?.let { CareError(it) }
                CareCard(Modifier.fillMaxWidth(), padding = 20.dp) {
                    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                            Text("关于${model.person.relationship.ifBlank { model.person.name }}${if (model.person.relationship.isBlank()) "" else " · ${model.person.name}"}",
                                Modifier.weight(1f), style = T.body(18), color = CareColors.SecondaryInk)
                            Text("草稿", style = T.body(17, true), color = CareColors.ButterInk,
                                modifier = Modifier.background(CareColors.ButterSoft, CircleShape).padding(horizontal = 13.dp, vertical = 7.dp))
                        }
                        Text(draft.memory.title, style = T.story(28), color = CareColors.Ink)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            CareDraftMetaChip(draft.memory.dateLabel, "cal")
                            careMeaningful(draft.memory.location)?.let { CareDraftMetaChip(it, "pin") }
                        }
                        draft.memory.media.firstOrNull()?.let {
                            RemoteChatPhoto(it, repository, Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(20.dp)))
                        }
                        SelectionContainer {
                            Text(draft.memory.content, style = T.story(22, lineSpacing = 10f), color = CareColors.Ink, modifier = Modifier.fillMaxWidth())
                        }
                    }
                }
                if (draft.hasNewNarration) CareError("手动修改的草稿已保留。聊天中还有新讲述，请先重新整理并核对，再确认保存。")
                model.edits?.takeIf { it.draftId != draft.id }?.let { edit ->
                    CareCard(Modifier.fillMaxWidth()) {
                        Text("先前草稿的本机修改仍保留", style = T.body(22, true), color = CareColors.Ink)
                        Text(edit.title, style = T.body(22), color = CareColors.Ink)
                        Text(edit.content, style = T.body(21), color = CareColors.SecondaryInk)
                        CareButton("复制到当前草稿编辑框", secondary = true, enabled = !model.busy, onClick = onRestorePrevious)
                    }
                }
                model.latestDraft?.let { latest ->
                    CareCard(Modifier.fillMaxWidth()) {
                        Text("草稿已在其他设备更新", style = T.body(22, true), color = CareColors.Ink)
                        Text(latest.memory.title, style = T.body(21), color = CareColors.SecondaryInk)
                        Text("请读取最新草稿并核对后，再决定是否重新整理或保存。", style = T.body(20), color = CareColors.SecondaryInk)
                        CareButton("读取最新草稿", secondary = true, enabled = !model.busy, onClick = model::readLatestDraft)
                    }
                }
            }
            CareDock {
                CareButton("保存这段回忆", icon = "heart", enabled = !draft.hasNewNarration && model.latestDraft == null,
                    loading = model.busy, modifier = Modifier.testTag("memory.save")) { model.save(onSaved, continueAfterSave = false) }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    CareButton("修改草稿", icon = "edit", secondary = true, enabled = !model.busy, fontSize = 21,
                        modifier = Modifier.weight(1f).testTag("care.draft.edit"), onClick = model::beginEdit)
                    CareButton("重新整理", icon = "refresh", secondary = true, enabled = !model.busy, fontSize = 21,
                        modifier = Modifier.weight(1f).testTag("care.draft.regenerate"), onClick = onRegenerate)
                }
            }
        }
        if (model.busy) CareBusyOverlay("正在处理草稿…")
    }
}

@Composable
private fun CareDraftMetaChip(text: String, icon: String) {
    Row(Modifier.background(CareColors.PaperSecondary, RoundedCornerShape(18.dp)).padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        CareSymbol(icon, 17.dp, tint = CareColors.Accent)
        Text(text, style = T.body(17, true), color = CareColors.SecondaryInk)
    }
}
