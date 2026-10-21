package cn.shinian.app.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.data.ChatMessage
import cn.shinian.app.ui.theme.JournalColors as C
import cn.shinian.app.ui.theme.JournalTypography as T

private data class LifeModule(val id: String, val title: String, val subtitle: String, val glyph: String)
private val lifeModules = listOf(
    LifeModule("childhood", "成长的地方", "家乡与童年", "photo"),
    LifeModule("growth", "读书或学艺", "校园与手艺", "book"),
    LifeModule("work", "工作与生活", "奋斗与日常", "edit"),
    LifeModule("family", "重要家人", "亲人与陪伴", "heart"),
    LifeModule("later_life", "如今的生活", "此刻的日常", "spark"),
    LifeModule("reflection", "人生回望", "回忆与感悟", "history"),
)

private val fieldTitles = mapOf("home" to "成长的地方", "learning" to "读书或学艺", "early_work" to "年轻时的工作与生活",
    "later_work" to "后来的工作与生活", "family" to "重要家人", "changes" to "记得的生活变化", "present" to "如今的生活",
    "SK01" to "出生时间", "SK01b" to "出生地点", "SK01c" to "记忆中的家乡", "SK02" to "名字与期许",
    "SK03" to "小时候和谁生活", "SK03b" to "家庭生活来源", "SK03c" to "兄弟姐妹", "SK03d" to "家人的相处",
    "SK04" to "家教与影响", "SK05" to "性格底色", "SK06" to "人生关键词")

/** Only presentation labels live here. Questions, evidence and progression always come from the server. */
@Composable
internal fun LifeInterviewScreen(model: ChatController, care: Boolean, dictation: MandarinDictation,
    onMic: () -> Unit, onBack: () -> Unit, onHistory: (List<ChatMessage>) -> Unit) {
    val overview = model.overview
    val status = model.lifeStatus
    val collecting = model.collectingLife
    val showingOverview = status == "review" || status == "confirmed"
    val confirmed = status == "confirmed"
    var selectedModule by rememberSaveable(model.person.id) { mutableStateOf("childhood") }
    var details by rememberSaveable { mutableStateOf(false) }
    var editingTopic by rememberSaveable { mutableStateOf<String?>(null) }
    var correction by rememberSaveable { mutableStateOf("") }
    var correctionSent by remember { mutableStateOf(false) }
    val turns = overview.objects("turns").mapIndexed { index, turn ->
        ChatMessage(turn.text("id") ?: "life-$index", turn.text("role") ?: "assistant", turn.text("content").orEmpty())
    }
    LaunchedEffect(model.busy, model.error, overview.number("version")) {
        if (correctionSent && !model.busy && model.pendingLife == null && model.error == null) {
            editingTopic = null; correctionSent = false
        }
    }
    ChatPage {
        ChatHeader(if (care) (if (showingOverview) if (confirmed) "选择话题" else "核对经历" else "慢慢讲述")
            else if (showingOverview) "人生概览" else "开始记录 · ${model.person.name}",
            if (care && showingOverview) if (confirmed) "2 / 3" else "1 / 3" else "AI 回忆助手", care,
            onBack = onBack, enabled = !model.busy) {
            Text(model.person.name.take(1), style = T.story(20), color = Color.White,
                modifier = Modifier.size(42.dp).clip(CircleShape).background(C.SageInk).padding(top = 7.dp), textAlign = TextAlign.Center)
        }
        if (showingOverview) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 16.dp), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(if (confirmed) "✓ 01 核对脉络" else "01 核对脉络 ●", style = T.body(if (care) 17 else 13, true), color = if (confirmed) C.SageInk else C.AccentDeep)
                Text("—", color = C.Muted)
                Text("02 选择板块", style = T.body(if (care) 17 else 13, confirmed), color = if (confirmed) C.AccentDeep else C.SecondaryInk)
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                Text(if (confirmed) "从哪段日子开始？" else "先核对人生脉络", style = if (care) T.body(30, true) else T.story(30), color = C.Ink,
                    modifier = Modifier.semantics { heading() })
                Text(if (confirmed) "选一段最想聊的，按您的节奏来。" else "确认后，选一段想聊的回忆。", style = T.body(if (care) 21 else 16), color = C.SecondaryInk)
                val summary = overview.objects("fields").flatMap { it.objects("evidence") }.mapNotNull { it.text("quote") }.joinToString("\n")
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(17.dp)).background(C.Surface)
                    .border(1.dp, C.CardBorder, RoundedCornerShape(17.dp)).padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        JournalGlyph("book")
                        Text(if (confirmed) "人生脉络" else "回忆线索", Modifier.weight(1f).padding(start = 10.dp), style = T.body(if (care) 22 else 18, true), color = C.Ink)
                        Text(if (confirmed) "已核对" else "待核对", style = T.body(if (care) 18 else 13), color = if (confirmed) C.SageInk else C.AccentDeep)
                    }
                    if (summary.isBlank() && !confirmed) {
                        Column(Modifier.fillMaxWidth().padding(vertical = 20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            JournalGlyph("book", size = 92.dp, tint = C.Muted)
                            Text("还没有具体生活线索", Modifier.padding(top = 22.dp, bottom = 8.dp), style = T.body(if (care) 24 else 20, true), color = C.Ink)
                            Text("之后可以随时补充，\n也可以先从熟悉的回忆开始。", style = T.body(if (care) 20 else 16), color = C.SecondaryInk, textAlign = TextAlign.Center)
                        }
                    } else Text(summary.ifBlank { "暂未提供具体线索，之后可以随时补充。" }, style = T.body(if (care) 21 else 15), color = C.SecondaryInk,
                        lineHeight = if (care) 32.sp else 25.sp, maxLines = if (confirmed) 3 else Int.MAX_VALUE)
                    HorizontalDivider(color = C.Line)
                    TextButton({ details = true }, Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                        Text("查看全部与更正", Modifier.weight(1f), style = T.body(if (care) 22 else 16), textAlign = TextAlign.Start)
                        Text("›", style = T.body(24))
                    }
                }
                if (confirmed) {
                    val columns = if (care || LocalDensity.current.fontScale > 1.3f) 1 else 2
                    lifeModules.chunked(columns).forEach { row ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            row.forEach { module ->
                                val selected = selectedModule == module.id
                                Column(Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(if (selected) C.Soft else C.Surface)
                                    .border(if (selected) 1.5.dp else 1.dp, if (selected) C.AccentDeep else C.CardBorder, RoundedCornerShape(16.dp))
                                    .clickable(enabled = !model.busy && model.pendingLife == null) { selectedModule = module.id }
                                    .semantics { this.selected = selected }.testTag("life.module.${module.id}").padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                    Row(Modifier.fillMaxWidth()) {
                                        JournalGlyph(module.glyph, tint = if (selected) C.AccentDeep else C.Ink)
                                        Spacer(Modifier.weight(1f)); if (selected) JournalGlyph("check", size = 20.dp, tint = C.AccentDeep)
                                    }
                                    Text(module.title, style = T.body(if (care) 24 else 18, true), color = C.Ink)
                                    Text(module.subtitle, style = T.body(if (care) 19 else 14), color = C.SecondaryInk)
                                }
                            }
                        }
                    }
                } else Text("不必一次想全，回忆可以慢慢补充。", Modifier.fillMaxWidth().padding(vertical = 12.dp), style = T.body(if (care) 20 else 14), color = C.SecondaryInk, textAlign = TextAlign.Center)
                LifeFeedback(model, care)
                Spacer(Modifier.height(12.dp))
            }
            ChatButton(if (confirmed) "进入「${lifeModules.first { it.id == selectedModule }.title}」" else "确认这些脉络",
                enabled = model.pendingLife == null, busy = model.busy, care = care, modifier = Modifier.padding(horizontal = 22.dp, vertical = 12.dp).testTag(if (confirmed) "life.enter" else "life.confirm")) {
                if (confirmed) model.chooseModule(selectedModule) else model.performLife("confirm")
            }
        } else {
            LazyColumn(Modifier.weight(1f).padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                item {
                    Spacer(Modifier.height(16.dp))
                    Text(if (collecting) "01 / 了解人生骨架" else "先了解您大致经历过哪些日子", style = if (care) T.body(24, true) else T.story(24), color = C.Ink)
                }
                if (!collecting) item {
                    Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
                        Text("一次聊一个问题，记不清或暂时不想讲的可以跳过。已有聊天与草稿会保留。", style = T.body(if (care) 22 else 16), color = C.SecondaryInk, lineHeight = if (care) 34.sp else 26.sp)
                        ChatButton(if (care) "开始聊聊" else "开始了解人生骨架", busy = model.busy, enabled = model.pendingLife == null, care = care,
                            modifier = Modifier.testTag("life.begin")) { model.performLife("begin") }
                    }
                }
                if (collecting && care) item {
                    Text("第 ${overview.number("question_number", 1)} 个问题，共 ${overview.number("total_questions", 11)} 个", style = T.body(18), color = C.SecondaryInk)
                    Text(overview.text("question") ?: turns.lastOrNull { it.role != "user" }?.content.orEmpty(), Modifier.padding(vertical = 20.dp), style = T.body(26, true), color = C.Ink, lineHeight = 39.sp)
                    TextButton({ onHistory(turns) }) { Text("前面聊过的", style = T.body(20)) }
                }
                if (collecting && !care) items(turns, key = { it.id }) { turn ->
                    Column(Modifier.fillMaxWidth().padding(start = if (turn.role == "user") 35.dp else 0.dp)
                        .then(if (turn.role == "user") Modifier.clip(RoundedCornerShape(22.dp)).background(C.Soft).padding(16.dp) else Modifier)) {
                        if (turn.role != "user") Text("AI 回忆助手", style = T.body(12), color = C.SecondaryInk)
                        Text(turn.content, style = T.story(17), color = C.Ink, lineHeight = 28.sp, modifier = Modifier.padding(top = 8.dp))
                    }
                }
                item { LifeFeedback(model, care); Spacer(Modifier.height(12.dp)) }
            }
            if (collecting) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("人生骨架 ${overview.number("question_number", 1)} / ${overview.number("total_questions", 11)}", Modifier.weight(1f), style = T.body(if (care) 18 else 12), color = C.SecondaryInk)
                    TextButton({ dictation.cancel(); model.performLife("answer", "跳过这题") }, Modifier.testTag("life.skip"), enabled = !model.busy && model.pendingLife == null && !dictation.busy) { Text(if (care) "记不清了，跳过" else "跳过", style = T.body(if (care) 20 else 14)) }
                }
                NarrationComposer(value = model.lifeInput, onValue = model::updateLifeInput, care = care,
                    enabled = !model.busy && model.pendingLife == null, sendEnabled = !model.busy && !dictation.busy && (model.pendingLife != null || model.lifeInput.isNotBlank()),
                    retrying = model.pendingLife != null, dictation = dictation, onMic = onMic,
                    onSend = { dictation.cancel(); model.performLife("answer", model.lifeInput) }, tag = "life")
            }
        }
    }
    if (details) ChatFullDialog(editingTopic?.let { fieldTitles[it] ?: it } ?: "核对人生脉络", onClose = {
        if (!model.busy) { if (editingTopic != null) editingTopic = null else details = false }
    }) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            if (editingTopic != null) {
                Text("请写下这一项应保留的说法。原始讲述会保留，更正后需要重新核对概览。", style = T.body(if (care) 22 else 16), color = C.SecondaryInk)
                OutlinedTextField(correction, { correction = it }, Modifier.fillMaxWidth().heightIn(min = 180.dp).testTag("life.correctionText"), enabled = !model.busy,
                    label = { Text("应保留的说法") }, textStyle = T.body(if (care) 23 else 17))
                ChatButton("记录更正", enabled = correction.isNotBlank() && model.pendingLife == null, busy = model.busy, care = care) {
                    correctionSent = true; model.performLife("correct", correction, editingTopic)
                }
            } else overview.objects("fields").forEach { field ->
                val topic = field.text("topic_id").orEmpty()
                Column(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(fieldTitles[topic] ?: topic, Modifier.weight(1f), style = T.body(if (care) 22 else 18, true), color = C.Ink)
                        TextButton({ editingTopic = topic; correction = "" }, enabled = !model.busy && model.pendingLife == null) { Text("更正", style = T.body(if (care) 21 else 16)) }
                    }
                    val evidence = field.objects("evidence").mapNotNull { it.text("quote") }.joinToString("\n")
                    Text(evidence.ifBlank { mapOf("skipped" to "暂时跳过", "unknown" to "记不清", "declined" to "暂时不想讲")[field.text("status")] ?: "待补充" },
                        style = T.body(if (care) 22 else 16), color = C.SecondaryInk, lineHeight = if (care) 34.sp else 26.sp)
                    HorizontalDivider(color = C.Line)
                }
            }
            LifeFeedback(model, care)
        }
    }
}

@Composable
private fun LifeFeedback(model: ChatController, care: Boolean) {
    model.error?.let { ChatError(it, if (model.pendingLife == null) "重新读取" else "重试这次操作", care, !model.busy) {
        if (model.pendingLife != null) model.performLife(model.pendingLife!!.action) else model.retryOpen()
    } }
    model.storageError?.let { ChatError(it, "重试本机保存", care, !model.busy, model::retryStorage) }
    if (model.busy) Row(Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.size(20.dp), color = C.AccentDeep, strokeWidth = 2.dp)
        Text(model.progress, style = T.body(if (care) 20 else 14), color = C.SecondaryInk)
    }
}
