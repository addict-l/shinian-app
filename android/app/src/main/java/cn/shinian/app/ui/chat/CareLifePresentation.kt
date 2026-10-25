package cn.shinian.app.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import cn.shinian.app.data.ChatMessage
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.care.CareTypography as T
import cn.shinian.app.ui.theme.ShinianImmersiveWindow
import cn.shinian.app.ui.theme.shinianContentInsets
import kotlinx.serialization.json.JsonObject

internal data class CareSummaryLine(val text: String, val subdued: Boolean)
internal data class CareSummaryGroup(val title: String, val icon: String, val tone: CareTone, val lines: List<CareSummaryLine>)

/** Presentation grouping only. Never infer answers, fill fields or determine interview progress. */
internal fun careLifeSummaryGroups(fields: List<JsonObject>): List<CareSummaryGroup> {
    val groups = if (fields.any { it.text("topic_id")?.startsWith("SK") == true }) listOf(
        Triple("出生与家乡", listOf("SK01", "SK01b", "SK01c", "SK02"), "home"),
        Triple("小时候的家", listOf("SK03", "SK03b", "SK03c", "SK03d", "SK04"), "users"),
        Triple("性格与一生", listOf("SK05", "SK06"), "sun"),
    ) else listOf(
        Triple("小时候", listOf("home"), "home"),
        Triple("读书工作", listOf("learning", "early_work", "later_work"), "book"),
        Triple("家人近况", listOf("family", "changes", "present"), "users"),
    )
    fun lines(values: List<JsonObject>) = values.filter { it.text("status") != "pending" }.map { field ->
        val quotes = field.objects("evidence").mapNotNull { it.text("quote")?.takeIf(String::isNotBlank) }
        if (quotes.isNotEmpty()) CareSummaryLine(quotes.joinToString("\n"), false)
        else CareSummaryLine((field.text("title") ?: fieldTitles[field.text("topic_id")] ?: field.text("topic_id").orEmpty()) + "：" +
            (mapOf("skipped" to "暂时跳过", "unknown" to "记不清", "declined" to "暂时不想讲")[field.text("status")] ?: "待补充"), true)
    }
    val result = groups.mapIndexed { index, (title, ids, icon) ->
        CareSummaryGroup(title, icon, listOf(CareTone.Butter, CareTone.Sage, CareTone.Rose)[index], lines(fields.filter { it.text("topic_id") in ids }))
    }.toMutableList()
    val known = groups.flatMap { it.second }.toSet()
    val remaining = fields.filter { it.text("topic_id") !in known }
    if (remaining.isNotEmpty()) result += CareSummaryGroup("其他", "book", CareTone.Apricot, lines(remaining))
    return result
}

private data class CareTopic(val id: String, val title: String, val hint: String, val icon: String, val tone: CareTone)
private val careTopics = listOf(
    CareTopic("childhood", "成长的地方", "家乡 · 童年", "home", CareTone.Butter),
    CareTopic("growth", "读书或学艺", "学校 · 手艺", "book", CareTone.Sage),
    CareTopic("work", "工作与生活", "工作 · 日常", "briefcase", CareTone.Apricot),
    CareTopic("family", "重要家人", "亲情 · 陪伴", "users", CareTone.Rose),
    CareTopic("later_life", "如今的生活", "现在 · 爱好", "cup", CareTone.Sage),
    CareTopic("reflection", "人生回望", "往事 · 感悟", "sun", CareTone.Butter),
)

@Composable
internal fun CareLifeOverview(overview: JsonObject?, confirmed: Boolean, enabled: Boolean, busy: Boolean,
    onDetails: () -> Unit, onHistory: () -> Unit, onConfirm: () -> Unit, onSelect: (String) -> Unit,
    modifier: Modifier = Modifier, feedback: @Composable () -> Unit = {}) {
    Column(modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(top = 16.dp, bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
            CareHeading(if (confirmed) "想聊些什么？" else "这些经历记对了吗？", if (confirmed) "选一个话题，慢慢讲。" else "记不清的，可以以后再补。")
            if (confirmed) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { careTopics.chunked(2).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        row.forEach { topic ->
                            Column(Modifier.weight(1f).clip(RoundedCornerShape(26.dp)).background(topic.tone.fill)
                                .clickable(enabled = enabled && !busy, role = Role.Button) { onSelect(topic.id) }
                                .testTag("life.module.${topic.id}").padding(18.dp).heightIn(min = 122.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Box(Modifier.size(56.dp).background(CareColors.Surface, CircleShape), contentAlignment = Alignment.Center) {
                                    CareSymbol(topic.icon, 28.dp, tint = topic.tone.ink)
                                }
                                Text(topic.title, style = T.body(23, true), color = CareColors.Ink)
                                Text(topic.hint, style = T.body(17), color = topic.tone.ink)
                            }
                        }
                    }
                } }
                CarePill("帮我挑一个", icon = "shuffle", enabled = enabled && !busy,
                    modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 2.dp).testTag("care.life.randomTopic")) { onSelect(careTopics.random().id) }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    careLifeSummaryGroups(overview.objects("fields")).forEach { group -> CareLifeSummaryCard(group, enabled && !busy, onDetails) }
                }
            }
            feedback()
        }
        if (!confirmed) CareDock {
            CareButton("记对了，下一步", icon = "next", loading = busy, enabled = enabled,
                modifier = Modifier.testTag("life.confirm"), onClick = onConfirm)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CareButton("修改经历", icon = "edit", secondary = true, enabled = enabled && !busy, minimumHeight = 88.dp,
                    fontSize = 21, modifier = Modifier.weight(1f).testTag("life.details"), onClick = onDetails)
                CareButton("查看刚才\n问答", icon = "chat", secondary = true, enabled = enabled && !busy, minimumHeight = 88.dp,
                    fontSize = 21, modifier = Modifier.weight(1f).testTag("care.life.history"), onClick = onHistory)
            }
        }
    }
}

@Composable
private fun CareLifeSummaryCard(group: CareSummaryGroup, enabled: Boolean, onDetails: () -> Unit) {
    var expanded by rememberSaveable(group.title) { mutableStateOf(false) }
    var overflow by remember(group.lines) { mutableStateOf(false) }
    CareCard(Modifier.fillMaxWidth().testTag("life.summary.${group.title}")) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.Top) {
            CareIconTile(group.icon, group.tone)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(group.title, style = T.body(20, true), color = group.tone.ink, modifier = Modifier.weight(1f))
                    CarePill("改", icon = "edit", compact = true, enabled = enabled, onClick = onDetails)
                }
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val text = if (group.lines.isEmpty()) AnnotatedString("之后可以慢慢补充。") else buildAnnotatedString {
                        group.lines.forEachIndexed { index, line ->
                            if (index > 0) append("\n")
                            withStyle(SpanStyle(color = if (line.subdued) CareColors.SecondaryInk else CareColors.Ink)) { append(line.text) }
                        }
                    }
                    Text(text, style = T.body(22, lineSpacing = 7f), color = CareColors.SecondaryInk,
                        maxLines = if (expanded) Int.MAX_VALUE else 3, onTextLayout = { if (!expanded) overflow = it.hasVisualOverflow })
                    if (expanded || overflow) CarePill(if (expanded) "收起" else "展开全文", icon = if (expanded) "up" else "down", compact = true) { expanded = !expanded }
                }
            }
        }
    }
}

@Composable
internal fun CareLifeInterviewPresentation(model: ChatController, dictation: MandarinDictation, turns: List<ChatMessage>,
    onMic: () -> Unit, onBack: () -> Unit, onHistory: () -> Unit, onDetails: () -> Unit, feedback: @Composable () -> Unit) {
    val overview = model.overview
    val review = model.lifeStatus == "review" || model.lifeStatus == "confirmed"
    val question = overview.text("question") ?: turns.lastOrNull { it.role != "user" }?.content ?: "想到什么就说什么。"
    var previousQuestion by remember { mutableStateOf<String?>(question) }
    var previousID by remember { mutableStateOf(overview.text("question_id")) }
    var followUp by remember { mutableStateOf(false) }
    LaunchedEffect(question) {
        followUp = previousQuestion != null && previousQuestion != question && previousID == overview.text("question_id")
        previousQuestion = question; previousID = overview.text("question_id")
    }
    val compact = dictation.busy || model.lifeInput.isNotBlank() || model.pendingLife != null
    Box(Modifier.fillMaxSize()) {
        CarePage {
            CareToolbar(if (review) if (model.lifeStatus == "confirmed") "选择话题" else "核对经历" else "慢慢讲述",
                onBack, backTitle = if (model.collectingLife) "暂停" else "返回",
                step = if (review) if (model.lifeStatus == "confirmed") "2 / 3" else "1 / 3"
                    else overview?.let { "${it.number("question_number", 1)} / ${it.number("total_questions", 11)}" },
                enabled = !model.busy, backTag = "chat.back")
            if (review) CareLifeOverview(overview, model.lifeStatus == "confirmed", model.pendingLife == null, model.busy,
                onDetails, onHistory, { model.performLife("confirm") }, model::chooseModule, Modifier.weight(1f), feedback)
            else {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    if (!model.collectingLife) {
                        CareHeading("先聊聊您的人生经历", "一次只问一个问题，慢慢想、慢慢说。")
                        Text("记不清的可以跳过，累了可以下次继续。", style = T.body(20), color = CareColors.SecondaryInk)
                        CareButton("开始聊聊", loading = model.busy, enabled = model.pendingLife == null,
                            modifier = Modifier.testTag("life.begin")) { model.performLife("begin") }
                    } else {
                        CareProgressBar(overview.number("question_number", 1), overview.number("total_questions", 11), Modifier.testTag("life.progress"))
                        CarePersonLine(model.person, "人生经历")
                        CareQuestionCard(question, Modifier.testTag("care.life.question"), label = if (followUp) "接着问您" else "回忆助手问您", compact = compact)
                        if (!compact) Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            CarePill("前面聊过的", icon = "chat", enabled = !model.busy,
                                modifier = Modifier.testTag("care.life.history"), onClick = onHistory)
                            CarePill("跳过这题", icon = "forward", enabled = !model.busy && model.pendingLife == null && !dictation.busy,
                                modifier = Modifier.testTag("life.skip")) { dictation.cancel(); model.performLife("answer", "跳过这题") }
                        }
                    }
                }
                if (model.collectingLife) CareDock {
                    CareNarrationComposer(model.lifeInput, model::updateLifeInput, enabled = !model.busy && model.pendingLife == null,
                        sendEnabled = !model.busy && !dictation.busy && (model.pendingLife != null || model.lifeInput.isNotBlank()),
                        retrying = model.pendingLife != null, dictation = dictation, onMic = onMic,
                        onSend = { dictation.cancel(); model.performLife("answer", model.lifeInput) }, tag = "life", pendingText = model.pendingLife?.text)
                }
                Column(Modifier.padding(horizontal = 20.dp)) { feedback() }
            }
        }
        if (model.busy) CareBusyOverlay("正在记录与核对…")
    }
}

@Composable
internal fun CareLifeCorrectionDialog(model: ChatController, editingTopic: String?, correction: String,
    onText: (String) -> Unit, onEdit: (String) -> Unit, onSave: () -> Unit, onBack: () -> Unit) {
    val editingField = model.overview.objects("fields").firstOrNull { it.text("topic_id") == editingTopic }
    Dialog(onDismissRequest = { if (!model.busy) onBack() }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        ShinianImmersiveWindow()
        CareBackdrop(Modifier.fillMaxSize(), force = true) {
            Box(Modifier.fillMaxSize().shinianContentInsets()) {
                CarePage {
                    CareToolbar(editingTopic?.let { editingField.text("title") ?: fieldTitles[it] ?: it } ?: "修改经历", onBack,
                        enabled = !model.busy, backTag = "care.back")
                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                        if (editingTopic != null) {
                            Text("请写下这一项应保留的说法。更正后需要重新核对。", style = T.body(19, lineSpacing = 6f), color = CareColors.SecondaryInk)
                            BasicTextField(correction, onText, Modifier.fillMaxWidth().background(CareColors.Surface, RoundedCornerShape(22.dp))
                                .border(1.5.dp, CareColors.Border, RoundedCornerShape(22.dp)).padding(18.dp).testTag("life.correctionText")
                                .semantics { contentDescription = "应保留的说法" },
                                enabled = !model.busy && model.pendingLife == null, minLines = 5, maxLines = 12,
                                textStyle = T.body(22, lineSpacing = 7f).copy(color = CareColors.Ink), cursorBrush = SolidColor(CareColors.Accent),
                                decorationBox = { inner -> Box {
                                    if (correction.isEmpty()) Text("写下应该保留的说法", style = T.body(22), color = CareColors.SecondaryInk.copy(alpha = .5f)); inner()
                                } })
                        } else {
                            Text("点“更正”，写下应该保留的说法。原来的讲述会留着。", style = T.body(19, lineSpacing = 6f), color = CareColors.SecondaryInk)
                            Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                                model.overview.objects("fields").forEach { field ->
                                    val topic = field.text("topic_id").orEmpty()
                                    val title = field.text("title") ?: fieldTitles[topic] ?: topic
                                    val evidence = field.objects("evidence").mapNotNull { it.text("quote") }.joinToString("\n")
                                    val content = evidence.ifBlank { mapOf("skipped" to "暂时跳过", "unknown" to "记不清", "declined" to "暂时不想讲")[field.text("status")] ?: "待补充" }
                                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
                                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                                Text(title, style = T.body(20, true), color = CareColors.Ink)
                                                Text(content, style = T.body(18, lineSpacing = 6f), color = CareColors.SecondaryInk)
                                            }
                                            CarePill("更正", icon = "edit", compact = true, enabled = !model.busy && model.pendingLife == null,
                                                modifier = Modifier.testTag("life.correct.${field.text("id") ?: topic}").semantics { contentDescription = "更正$title" }) { onEdit(topic) }
                                        }
                                        HorizontalDivider(color = CareColors.Line)
                                    }
                                }
                            }
                        }
                        model.error?.let { CareError(it) {
                            if (model.pendingLife != null) model.performLife(model.pendingLife!!.action) else model.retryOpen()
                        } }
                        model.storageError?.let { CareError(it, model::retryStorage) }
                    }
                    if (editingTopic != null) CareDock {
                        CareButton("记录更正", icon = "check", loading = model.busy, enabled = correction.isNotBlank() && model.pendingLife == null,
                            modifier = Modifier.testTag("life.saveCorrection"), onClick = onSave)
                    }
                }
                if (model.busy) CareBusyOverlay("正在记录更正…")
            }
        }
    }
}
