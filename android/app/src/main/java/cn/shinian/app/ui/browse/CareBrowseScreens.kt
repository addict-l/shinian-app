package cn.shinian.app.ui.browse

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.R
import cn.shinian.app.data.Memory
import cn.shinian.app.data.Person
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.chat.ChatDraftStore
import cn.shinian.app.ui.care.CareTypography as T
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
internal fun CareHomeScreen(people: List<Person>, memories: List<Memory>, loading: Boolean, error: String?,
    onRefresh: () -> Unit, onNewMemory: () -> Unit, onAllMemories: () -> Unit, onMemory: (Memory) -> Unit,
    onContinue: (Person) -> Unit) {
    val context = LocalContext.current
    val account = LocalBrowseStorageScope.current
    var continuation by remember(account) { mutableStateOf<Pair<Person, String>?>(null) }
    LaunchedEffect(account, people) {
        continuation = if (account == "signed-out") null else withContext(Dispatchers.IO) {
            people.firstNotNullOfOrNull { person ->
                val draft = runCatching { ChatDraftStore(context, account, person.id).load()?.first }.getOrNull()
                draft?.takeIf { it.pending != null || it.pendingLife != null || it.input.isNotBlank() || it.lifeInput.isNotBlank() || it.photos.isNotEmpty() }
                    ?.let { person to if (it.pending != null || it.pendingLife != null) "有一段待重试" else "有没发出的话" }
            }
        }
    }
    BrowseScroll(loading, onRefresh, care = true, topPadding = 12.dp) {
        CareHomeBrand()
        Text("慢慢讲，\n都是好时光。", style = T.story(34, lineSpacing = 4f), color = CareColors.Ink,
            modifier = Modifier.semantics { heading() })
        CareCard(Modifier.fillMaxWidth()) {
            CareHomeIllustration()
            Text("今天想起了谁？说给我听听。", style = T.body(19), color = CareColors.SecondaryInk)
            CareButton("开始讲述", icon = "mic", modifier = Modifier.testTag("home.newMemory"), onClick = onNewMemory)
        }
        continuation?.let { (person, hint) ->
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(CareColors.SageSoft)
                .clickable(role = Role.Button) { onContinue(person) }.testTag("care.home.continue").heightIn(min = 92.dp).padding(16.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                LocalPortrait(person.id, person, size = 56.dp, care = true)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("接着上次讲", style = T.body(22, true), color = CareColors.SageInk)
                    Text("${person.relationship.ifBlank { person.name }} · $hint", style = T.body(18), color = CareColors.SageInk)
                }
                Box(Modifier.size(48.dp).background(CareColors.Surface, CircleShape), contentAlignment = Alignment.Center) {
                    CareSymbol("next", 23.dp, tint = CareColors.SageInk)
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("最近的回忆", style = T.body(24, true), color = CareColors.Ink, modifier = Modifier.weight(1f))
            CarePill("全部", icon = "chev", compact = true, modifier = Modifier.testTag("home.allMemories"), onClick = onAllMemories)
        }
        val latest = memories.maxByOrNull { it.createdAt }
        if (latest != null) CareMemoryCard(latest, people, compact = true) { onMemory(latest) }
        else if (!loading && error == null) CareCard(Modifier.fillMaxWidth(), padding = 20.dp) {
            Text("还没有回忆。点“开始讲述”，留下第一段故事。", style = T.body(22), color = CareColors.SecondaryInk)
        }
        if (loading && memories.isEmpty()) CareBrowseLoading("正在打开回忆…", Modifier.padding(24.dp))
        BrowseError(error, true, onRefresh)
    }
}

@Composable
private fun CareHomeBrand() {
    val date = LocalDate.now().format(DateTimeFormatter.ofPattern("M月d日 EEEE", Locale.SIMPLIFIED_CHINESE))
    val brandStyle = T.body(18, true).copy(letterSpacing = 1.sp)
    val dateStyle = T.body(18)
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val width = with(density) { (measurer.measure(AnnotatedString("拾年 · 关怀模式"), brandStyle).size.width +
        measurer.measure(AnnotatedString(date), dateStyle).size.width).toDp() } + 8.dp
    val brand: @Composable () -> Unit = { Text("拾年 · 关怀模式", style = brandStyle, color = CareColors.Accent) }
    val day: @Composable () -> Unit = { Text(date, style = dateStyle, color = CareColors.SecondaryInk) }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (width <= maxWidth) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) { brand(); day() }
        else Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { brand(); day() }
    }
}

@Composable
private fun CareHomeIllustration() {
    val painter = painterResource(R.drawable.journal_welcome)
    Canvas(Modifier.fillMaxWidth().height(128.dp)
        .clip(RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp))
        .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }) {
        val photoHeight = size.width * 4f / 3f
        translate(top = -(photoHeight - size.height) * .62f) {
            with(painter) { draw(Size(size.width, photoHeight)) }
        }
        drawRect(Brush.verticalGradient(0f to Color.Black, .65f to Color.Black, 1f to Color.Transparent), blendMode = BlendMode.DstIn)
    }
}

@Composable
internal fun CareMemoryCard(memory: Memory, people: List<Person>, compact: Boolean = false, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val person = people.firstOrNull { it.id == (memory.primaryPersonId ?: memory.personIds.firstOrNull()) }
    CareCard(modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).testTag("memory.card.${memory.id}"), padding = 0.dp) {
        if (compact) Row(Modifier.padding(14.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
            if (memory.media.isNotEmpty()) MemoryPhoto(memory.media.first(), Modifier.size(96.dp), radius = 18.dp)
            else Box(Modifier.size(96.dp), contentAlignment = Alignment.Center) { CareIconTile("book", CareTone.Butter, 76.dp) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(careMemorySubtitle(memory, people), style = T.body(18), color = CareColors.SecondaryInk)
                Text(memory.title, style = T.story(23), color = CareColors.Ink)
            }
        } else {
            memory.media.firstOrNull()?.let { MemoryPhoto(it, Modifier.fillMaxWidth().height(158.dp), radius = 0.dp) }
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically) {
                    person?.let { LocalPortrait(it.id, it, size = 32.dp, care = true) }
                    Text(careMemorySubtitle(memory, people), style = T.body(18), color = CareColors.SecondaryInk)
                }
                Text(memory.title, style = T.story(25), color = CareColors.Ink)
                CareMemoryDetails(listOfNotNull(careMeaningful(memory.place.value), careMeaningful(memory.feeling.value)).joinToString(" · "))
            }
        }
    }
}

private fun careMemorySubtitle(memory: Memory, people: List<Person>): String {
    val ids = memory.primaryPersonId?.let { listOf(it) } ?: memory.personIds
    val roles = ids.mapNotNull { id -> people.firstOrNull { it.id == id } }.joinToString("、") { it.relationship.ifBlank { it.name } }
    return "${roles.ifBlank { memory.personName }} · ${memory.dateLabel}"
}

@Composable
private fun CareMemoryDetails(details: String) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val detailsWidth = with(density) { measurer.measure(AnnotatedString(details), T.body(18)).size.width.toDp() }
    val openWidth = with(density) { measurer.measure(AnnotatedString("打开看看"), T.body(20, true)).size.width.toDp() } + careSymbolWidth("next", 20.dp) + 8.dp
    val openLabel: @Composable () -> Unit = {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            CareSymbol("next", 20.dp, tint = CareColors.Accent)
            Text("打开看看", style = T.body(20, true), color = CareColors.Accent)
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (detailsWidth + openWidth + 12.dp <= maxWidth) Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (details.isNotEmpty()) Text(details, style = T.body(18), color = CareColors.SecondaryInk)
            Spacer(Modifier.weight(1f)); openLabel()
        } else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (details.isNotEmpty()) Text(details, style = T.body(18), color = CareColors.SecondaryInk)
            openLabel()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CareMemoriesScreen(people: List<Person>, memories: List<Memory>, loading: Boolean, error: String?, isRoot: Boolean,
    onBack: () -> Unit, onMemory: (Memory) -> Unit, onCompose: () -> Unit, onRefresh: () -> Unit) {
    var search by rememberSaveable { mutableStateOf("") }
    var selectedPerson by rememberSaveable { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val focus = LocalFocusManager.current
    val dictation = remember { cn.shinian.app.ui.chat.MandarinDictation(context.applicationContext) { search = it } }
    val mic = rememberCareMicrophone(dictation, "")
    DisposableEffect(dictation) { onDispose { dictation.cancel() } }
    val events = memories.filter { (selectedPerson == null || (it.primaryPersonId?.let { id -> id == selectedPerson } ?: (selectedPerson in it.personIds))) &&
        (search.isBlank() || "${it.title} ${it.personName} ${it.content}".contains(search, true)) }.sortedByDescending { it.createdAt }
    Column(Modifier.fillMaxSize()) {
        if (!isRoot) CareToolbar("珍藏的回忆", onBack)
        PullToRefreshBox(loading, onRefresh, Modifier.weight(1f)) {
        LazyColumn(Modifier.fillMaxSize().testTag("memories.list"), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    if (isRoot) CareCollectionHeading(memories.distinctBy { it.id }.size)
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(CareColors.Surface)
                        .border(1.5.dp, CareColors.Border, RoundedCornerShape(22.dp))
                        .padding(start = 18.dp, end = 8.dp, top = 8.dp, bottom = 8.dp).heightIn(min = 48.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        JournalIcon("search", modifier = Modifier.size(26.dp), tint = CareColors.Accent)
                        BasicTextField(search, { search = it }, Modifier.weight(1f).testTag("care.memories.search")
                            .semantics { contentDescription = "搜索回忆" }, textStyle = T.body(22).copy(color = CareColors.Ink), singleLine = true,
                            cursorBrush = SolidColor(CareColors.Accent), keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { focus.clearFocus() }), decorationBox = { inner ->
                                Box(contentAlignment = Alignment.CenterStart) {
                                    if (search.isEmpty()) Text("找一段回忆", style = T.body(22), color = Color(0xFFC7C7CC))
                                    inner()
                                }
                            })
                        IconButton({ focus.clearFocus(); mic() }, enabled = dictation.phase != cn.shinian.app.ui.chat.MandarinDictation.Phase.Finishing,
                            modifier = Modifier.size(48.dp).testTag("care.memories.dictation")) {
                            CareSymbol(if (dictation.busy) "stopCircle" else "mic", 25.dp, if (dictation.busy) "停止语音搜索" else "语音搜索", tint = CareColors.Accent)
                        }
                    }
                    Row(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 2.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CarePersonFilter(null, selectedPerson == null, "care.filter.all") { selectedPerson = null }
                        people.forEach { person -> CarePersonFilter(person, selectedPerson == person.id, "care.filter.${person.id}") { selectedPerson = person.id } }
                    }
                    if (dictation.busy) Text(dictation.status, style = T.body(18), color = CareColors.Accent)
                    if (loading) CareBrowseLoading("正在打开回忆…", Modifier.padding(12.dp))
                    BrowseError(error, true, onRefresh)
                }
            }
            val groups = events.groupBy { storyYear(it) }.toSortedMap(compareByDescending<Int?> { it ?: Int.MIN_VALUE })
            groups.forEach { (year, values) ->
                item("year-$year") {
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp).semantics { heading() }, horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(year?.let { "$it 年" } ?: "时间待补充", style = T.body(20, true), color = CareColors.SecondaryInk)
                        HorizontalDivider(Modifier.weight(1f), color = CareColors.Line)
                    }
                }
                items(values, key = { it.id }) { memory -> CareMemoryCard(memory, people) { onMemory(memory) } }
            }
            if (events.isEmpty() && !loading && error == null) item {
                Text(if (memories.isEmpty()) "还没有回忆，先讲一段故事吧。" else "没有找到，换一句话或另一位家人试试。",
                    style = T.body(22), color = CareColors.SecondaryInk, modifier = Modifier.padding(vertical = 20.dp))
            }
            if (memories.isEmpty() && !loading && error == null) item { CareButton("开始讲述", icon = "mic", onClick = onCompose) }
        }
        }
    }
    dictation.error?.let { message -> AlertDialog(onDismissRequest = { dictation.error = null }, title = { Text("语音输入") }, text = { Text(message) },
        confirmButton = { TextButton({ dictation.error = null }) { Text("确定") } }) }
}

@Composable
private fun CareCollectionHeading(count: Int) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val titleStyle = T.body(32, true)
    val countStyle = T.body(18, true)
    val countText = "共 $count 段"
    val desiredWidth = with(density) { (measurer.measure(AnnotatedString("珍藏的回忆"), titleStyle).size.width +
        measurer.measure(AnnotatedString(countText), countStyle).size.width).toDp() } + 40.dp
    val title: @Composable () -> Unit = { Text("珍藏的回忆", style = titleStyle, color = CareColors.Ink, modifier = Modifier.semantics { heading() }) }
    val badge: @Composable () -> Unit = { Text(countText, style = countStyle, color = CareColors.Accent,
        modifier = Modifier.background(CareColors.Soft, CircleShape).padding(horizontal = 14.dp, vertical = 8.dp)) }
    BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 8.dp)) {
        if (desiredWidth <= maxWidth) Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) { title(); badge() }
        else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { title(); badge() }
    }
}

@Composable
private fun CarePersonFilter(person: Person?, selected: Boolean, tag: String, onClick: () -> Unit) {
    val fill = if (selected) CareColors.Accent else CareColors.Surface
    Row(Modifier.clip(CircleShape).background(fill).border(1.5.dp, if (selected) CareColors.Accent else CareColors.Border, CircleShape)
        .clickable(role = Role.Button, onClick = onClick).testTag(tag).semantics { this.selected = selected }
        .heightIn(min = 56.dp).padding(start = if (person == null) 22.dp else 6.dp, end = 20.dp, top = 6.dp, bottom = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        person?.let { LocalPortrait(it.id, it, size = 42.dp, care = true) }
        Text(person?.relationship?.ifBlank { person.name } ?: person?.name ?: "全部", style = T.body(21, selected), color = if (selected) Color.White else CareColors.Ink)
    }
}

@Composable
private fun CareBrowseLoading(message: String, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.size(20.dp), color = CareColors.Accent, strokeWidth = 2.dp)
        Text(message, style = T.body(20), color = CareColors.Ink)
    }
}

@Composable
internal fun CareMoreContent(people: List<Person>, memories: List<Memory>, onFamily: () -> Unit, onSettings: () -> Unit,
    onPrivacy: () -> Unit, onStandard: () -> Unit) {
    Text("更多", style = T.body(32, true), color = CareColors.Ink, modifier = Modifier.padding(bottom = 2.dp).semantics { heading() })
    CareCard(Modifier.fillMaxWidth(), 20.dp) {
        CareFamilySummary(people, memories)
    }
    CareCard(Modifier.fillMaxWidth(), 0.dp) {
        CareMenuRow("家人管理", "添加家人、换头像", "users", CareTone.Rose, onFamily)
        HorizontalDivider(color = CareColors.Line)
        CareMenuRow("设置与账号", "名字、退出家庭账号", "gear", CareTone.Butter, onSettings)
        HorizontalDivider(color = CareColors.Line)
        CareMenuRow("隐私与数据", "回忆只属于您的家", "shield", CareTone.Sage, onPrivacy)
    }
    CareCard(Modifier.fillMaxWidth(), 0.dp) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("显示方式", style = T.body(24, true), color = CareColors.Ink, modifier = Modifier.semantics { heading() })
            Row(Modifier.fillMaxWidth().background(CareColors.PaperSecondary, RoundedCornerShape(22.dp)).padding(5.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                CareModeLabel("普通模式", false, Modifier.weight(1f).clip(RoundedCornerShape(18.dp))
                    .clickable(role = Role.Button, onClick = onStandard).testTag("care.switchStandard"))
                CareModeLabel("关怀模式", true, Modifier.weight(1f).semantics { selected = true })
            }
        }
    }
    Text("拾年 · 留住时光", style = T.body(18), color = CareColors.SecondaryInk, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
}

@Composable
private fun CareFamilySummary(people: List<Person>, memories: List<Memory>) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val count = "${people.size} 位家人 · ${memories.distinctBy { it.id }.size} 段回忆"
    val textWidth = with(density) { maxOf(measurer.measure(AnnotatedString("我们家的回忆"), T.body(23, true)).size.width,
        measurer.measure(AnnotatedString(count), T.body(18)).size.width).toDp() }
    val portraitsWidth = 54.dp * people.size.coerceIn(1, 3) - 16.dp * (people.size.coerceIn(1, 3) - 1)
    val portraits: @Composable () -> Unit = {
        Row(horizontalArrangement = Arrangement.spacedBy((-16).dp)) {
            people.take(3).forEach { LocalPortrait(it.id, it, size = 54.dp, care = true) }
            if (people.isEmpty()) CareIconTile("users", CareTone.Rose, 54.dp)
        }
    }
    val summary: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text("我们家的回忆", style = T.body(23, true), color = CareColors.Ink)
            Text(count, style = T.body(18), color = CareColors.SecondaryInk)
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (portraitsWidth + textWidth + 14.dp <= maxWidth) Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) { portraits(); summary() }
        else Column(verticalArrangement = Arrangement.spacedBy(14.dp)) { portraits(); summary() }
    }
}

@Composable
private fun CareModeLabel(title: String, selected: Boolean, modifier: Modifier) {
    Row(modifier.background(if (selected) CareColors.Surface else Color.Transparent, RoundedCornerShape(18.dp))
        .padding(horizontal = 6.dp, vertical = 6.dp).heightIn(min = 58.dp),
        horizontalArrangement = Arrangement.spacedBy(7.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically) {
        val ink = if (selected) CareColors.Accent else CareColors.SecondaryInk
        Text("Aa", style = T.body(20, selected), color = ink)
        Text(title, style = T.body(21, selected), color = ink, textAlign = TextAlign.Center)
    }
}

@Composable
private fun CareMenuRow(title: String, detail: String, icon: String, tone: CareTone, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).heightIn(min = 100.dp).padding(18.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        CareIconTile(icon, tone)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(title, style = T.body(23, true), color = CareColors.Ink)
            Text(detail, style = T.body(18), color = CareColors.SecondaryInk)
        }
        CareSymbol("chev", 20.dp, tint = CareColors.SecondaryInk)
    }
}

@Composable
internal fun CarePersonSelectionScreen(people: List<Person>, loading: Boolean, error: String?, onSelect: (Person) -> Unit,
    onAdd: () -> Unit, onRefresh: () -> Unit, onBack: () -> Unit) {
    Column(Modifier.fillMaxSize()) {
        CareToolbar("选择家人", onBack, backTitle = "首页")
        BrowseScroll(loading, onRefresh, true, Modifier.weight(1f), spacing = 14.dp) {
            Box(Modifier.padding(bottom = 8.dp)) { CareHeading("这次讲谁的故事？", "点一下家人，就可以开始。") }
            people.forEach { person ->
                CareCard(Modifier.fillMaxWidth().clickable(role = Role.Button) { onSelect(person) }.testTag("member.${person.id}")) {
                    Row(Modifier.heightIn(min = 80.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        LocalPortrait(person.id, person, size = 74.dp, care = true)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                            CarePersonName(person)
                            Text("已讲 ${person.memoryCount} 段", style = T.body(17, true), color = CareColors.Accent,
                                modifier = Modifier.background(CareColors.Soft, CircleShape).padding(horizontal = 12.dp, vertical = 5.dp))
                        }
                        Box(Modifier.width(48.dp).height(52.dp).background(CareColors.Faint, CircleShape), contentAlignment = Alignment.Center) {
                            CareSymbol("next", 23.dp, tint = CareColors.Accent)
                        }
                    }
                }
            }
            if (loading) CareBrowseLoading("正在打开家人…", Modifier.padding(12.dp))
            BrowseError(error, true, onRefresh)
            Box(Modifier.fillMaxWidth().drawDashedCareBorder().clip(RoundedCornerShape(26.dp)).clickable(role = Role.Button, onClick = onAdd)
                .heightIn(min = 76.dp).padding(horizontal = 12.dp).testTag("members.addAnother"), contentAlignment = Alignment.Center) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    CareSymbol("plus", 24.dp, tint = CareColors.Accent)
                    Text("添加一位家人", style = T.body(24, true), color = CareColors.Accent)
                }
            }
        }
    }
}

@Composable
private fun CarePersonName(person: Person) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val title = person.relationship.ifBlank { person.name }
    val titleWidth = measurer.measure(AnnotatedString(title), T.body(28, true)).size.width
    val nameWidth = if (person.relationship.isBlank()) 0 else measurer.measure(AnnotatedString(person.name), T.body(20)).size.width
    val width = with(density) { (titleWidth + nameWidth).toDp() } + if (person.relationship.isBlank()) 0.dp else 8.dp
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (width <= maxWidth) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = T.body(28, true), color = CareColors.Ink, modifier = Modifier.alignByBaseline())
            if (person.relationship.isNotBlank()) Text(person.name, style = T.body(20), color = CareColors.SecondaryInk, modifier = Modifier.alignByBaseline())
        } else Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = T.body(28, true), color = CareColors.Ink)
            if (person.relationship.isNotBlank()) Text(person.name, style = T.body(20), color = CareColors.SecondaryInk)
        }
    }
}

private fun Modifier.drawDashedCareBorder(): Modifier = this.then(Modifier.drawWithContent {
    drawContent()
    val stroke = 2.dp.toPx()
    drawRoundRect(CareColors.Border, topLeft = Offset(stroke / 2, stroke / 2), size = Size(size.width - stroke, size.height - stroke),
        cornerRadius = CornerRadius(26.dp.toPx()), style = Stroke(stroke, pathEffect = PathEffect.dashPathEffect(floatArrayOf(7.dp.toPx(), 5.dp.toPx()))))
})
