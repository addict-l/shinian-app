package cn.shinian.app.ui.browse

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.data.Memory
import cn.shinian.app.data.Person
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.theme.JournalColors
import java.time.LocalDate

// These iOS destinations keep JournalTheme's compact layout even in care mode.
internal fun careNativeBody(size: Float, medium: Boolean = false, spacing: Float = 0f) =
    CareTypography.body(size.toInt(), medium, lineSpacing = spacing).copy(fontSize = size.sp, lineHeight = (size * 1.4f + spacing).sp)
internal fun careNativeStory(size: Float, spacing: Float = 0f) =
    CareTypography.story(size, lineSpacing = spacing).copy(lineHeight = (size * 1.437f + spacing).sp)

@Composable
internal fun CareNativeBackBar(title: String = "", onBack: () -> Unit) {
    Box(Modifier.fillMaxWidth().height(48.dp).padding(horizontal = 14.dp), contentAlignment = Alignment.Center) {
        Text(title, style = careNativeBody(16f, true), color = CareColors.Ink, maxLines = 1)
        Box(Modifier.align(Alignment.CenterStart).size(44.dp).clickable(role = Role.Button, onClick = onBack)
            .testTag("browse.back").semantics { contentDescription = "返回" }, contentAlignment = Alignment.Center) {
            Box(Modifier.size(40.dp).shadow(7.dp, CircleShape).background(CareColors.Surface, CircleShape), contentAlignment = Alignment.Center) {
                JournalIcon("back", modifier = Modifier.size(22.dp), tint = CareColors.Ink)
            }
        }
    }
}

@Composable
internal fun CareNativeCard(modifier: Modifier = Modifier, padding: androidx.compose.ui.unit.Dp = 16.dp,
    content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Column(modifier.shadow(7.dp, shape, ambientColor = JournalColors.Shadow.copy(alpha = .08f),
        spotColor = JournalColors.Shadow.copy(alpha = .08f)).background(CareColors.Surface, shape)
        .border(1.dp, JournalColors.CardBorder, shape).clip(shape).padding(padding), content = content)
}

@Composable
internal fun CareNativeIconTile(icon: String, fill: Color = CareColors.Soft, ink: Color = JournalColors.AccentDeep,
    size: androidx.compose.ui.unit.Dp = 38.dp, radius: androidx.compose.ui.unit.Dp = 12.dp) {
    Box(Modifier.size(size).background(fill, RoundedCornerShape(radius)), contentAlignment = Alignment.Center) {
        JournalIcon(icon, modifier = Modifier.size(22.dp), tint = ink)
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
internal fun CareFamilyFilmContent(people: List<Person>, memories: List<Memory>, loading: Boolean, error: String?,
    allPeople: Boolean, search: String, onSearch: (String) -> Unit, storageScope: String, portraitRevision: Int,
    onRefresh: () -> Unit, onPerson: (Person) -> Unit, onMemory: (Memory) -> Unit,
    onAdd: (Person?) -> Unit, onAllPeople: () -> Unit, onPersonMenu: (Person) -> Unit) {
    val filtered = people.filter { search.isBlank() || "${it.name} ${it.relationship}".contains(search, true) }.let { if (allPeople) it else it.take(3) }
    CarePage {
        if (allPeople) CareNativeBackBar(onBack = onAllPeople)
        PullToRefreshBox(loading, onRefresh, Modifier.weight(1f)) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(top = 6.dp, bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Column(Modifier.padding(horizontal = 22.dp)) {
                    Text("家庭胶片", style = careNativeBody(12f, true).copy(letterSpacing = 2.2.sp), color = JournalColors.Accent)
                    Text(if (allPeople) "家人的胶卷" else "我们的家庭", Modifier.padding(top = 8.dp),
                        style = careNativeStory(30f).copy(letterSpacing = .6.sp), color = CareColors.Ink)
                    Text(if (allPeople) "一人一卷，慢慢翻阅。" else "把日子连起来，就成了我们的故事。", Modifier.padding(top = 2.dp),
                        style = careNativeBody(14f, spacing = 4f), color = CareColors.SecondaryInk)
                    if (people.isNotEmpty()) Row(Modifier.padding(top = 14.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("${people.size} 位家人 · ${memories.distinctBy { it.id }.size} 段回忆", style = careNativeBody(13f), color = CareColors.SecondaryInk)
                        if (!allPeople) {
                            Spacer(Modifier.weight(1f))
                            TextButton(onAllPeople, contentPadding = PaddingValues(0.dp), modifier = Modifier.heightIn(min = 44.dp)) {
                                Text("查看全部家人", style = careNativeBody(13f), color = CareColors.SecondaryInk)
                                JournalIcon("chev", modifier = Modifier.size(14.dp), tint = CareColors.SecondaryInk)
                            }
                        }
                    }
                }
                if (allPeople) Row(Modifier.padding(horizontal = 22.dp).fillMaxWidth().height(46.dp)
                    .background(CareColors.Surface, CircleShape).border(1.dp, JournalColors.Line, CircleShape).padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    JournalIcon("search", tint = JournalColors.Muted)
                    BasicTextField(search, onSearch, Modifier.weight(1f).testTag("browse.search"), singleLine = true,
                        textStyle = careNativeBody(14f).copy(color = CareColors.Ink), cursorBrush = SolidColor(JournalColors.Accent),
                        decorationBox = { inner -> Box { if (search.isEmpty()) Text("搜索家人的姓名或身份", style = careNativeBody(14f), color = JournalColors.Muted); inner() } })
                    if (search.isNotEmpty()) IconButton({ onSearch("") }, Modifier.size(28.dp)) { JournalIcon("x", "清除搜索", tint = JournalColors.Muted) }
                } else if (people.isNotEmpty()) Row(Modifier.padding(horizontal = 24.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("家人的胶卷", style = careNativeStory(19f), color = CareColors.Ink)
                    Spacer(Modifier.weight(1f))
                    Text("一人一卷，慢慢翻阅。", style = careNativeBody(12f), color = JournalColors.Muted)
                }
                filtered.forEach { person ->
                    val events = memories.filter { person.id in it.personIds }.sortedWith(compareByDescending<Memory> { storyYear(it) ?: Int.MIN_VALUE }.thenByDescending { it.createdAt })
                    Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.padding(horizontal = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Row(Modifier.weight(1f).heightIn(min = 44.dp).combinedClickable(onClick = { onPerson(person) }, onLongClick = { onPersonMenu(person) })
                                .testTag("film.person.${person.name}"), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                LocalPortrait(person.id, person, storageScope, 38.dp, portraitRevision, care = true)
                                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                                    Text(person.relationship.ifBlank { person.name }, style = careNativeBody(15f, true), color = CareColors.Ink)
                                    if (person.relationship.isNotBlank()) Text(person.name, style = careNativeBody(12f), color = CareColors.SecondaryInk)
                                }
                                Spacer(Modifier.weight(1f))
                                Text("${events.size} 段回忆", style = careNativeBody(12f), color = CareColors.SecondaryInk, modifier = Modifier.testTag("film.count.${person.name}"))
                            }
                            Box(Modifier.size(44.dp).clickable(role = Role.Button) { onAdd(person) }.testTag("film.add.${person.name}")
                                .semantics { contentDescription = "记录关于${person.name}的回忆" }, contentAlignment = Alignment.Center) {
                                Box(Modifier.size(34.dp).background(CareColors.Soft, CircleShape), contentAlignment = Alignment.Center) { JournalIcon("plus", modifier = Modifier.size(18.dp), tint = JournalColors.AccentDeep) }
                            }
                        }
                        Column(Modifier.fillMaxWidth().shadow(9.dp, RoundedCornerShape(12.dp)).background(JournalColors.Film, RoundedCornerShape(12.dp)).padding(vertical = 6.dp)) {
                            CareNativePerforations()
                            LazyRow(Modifier.testTag("film.roll.${person.name}"), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                items(events, key = { it.id }) { CareNativeFilmFrame(it) { onMemory(it) } }
                                if (events.isEmpty()) item {
                                    if (loading) Box(Modifier.size(101.dp, 82.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(22.dp), color = CareColors.Soft) }
                                    else Column(Modifier.widthIn(min = 240.dp).heightIn(min = 82.dp).clickable(role = Role.Button) { onAdd(person) }.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text("这一卷，等一个故事", style = careNativeStory(14f), color = CareColors.Paper)
                                        Text("记下你们的第一段回忆", style = careNativeBody(12f), color = CareColors.Paper)
                                    }
                                }
                            }
                            CareNativePerforations()
                        }
                    }
                }
                if (filtered.isEmpty() && !loading) Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(if (people.isEmpty()) "第一卷，留给谁？" else "没有找到这位家人", style = careNativeStory(24f), color = CareColors.Ink)
                    Text(if (people.isEmpty()) "先记下家人的名字，\n再慢慢收集你们的故事。" else "试试姓名，或是你对家人的称呼。", style = careNativeBody(14f), color = CareColors.SecondaryInk)
                    if (people.isEmpty()) JournalAction("添加一位家人", icon = "plus") { onAdd(null) }
                }
                error?.let { Box(Modifier.padding(horizontal = 22.dp)) { CareError(it, onRefresh) } }
            }
        }
    }
}

@Composable
private fun CareNativePerforations() {
    Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        repeat(16) { Box(Modifier.size(7.dp, 5.dp).background(CareColors.Paper.copy(alpha = .85f), RoundedCornerShape(1.5.dp))) }
    }
}

@Composable
private fun CareNativeFilmFrame(memory: Memory, onClick: () -> Unit) {
    val photo = memory.media.firstOrNull()
    Box(Modifier.size(101.dp, 82.dp).clip(RoundedCornerShape(7.dp)).background(CareColors.PaperSecondary).clickable(role = Role.Button, onClick = onClick)) {
        if (photo != null) {
            MemoryPhoto(photo, Modifier.fillMaxSize(), radius = 7.dp)
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0f to Color.Transparent, .36f to JournalColors.Film.copy(alpha = .08f), .65f to JournalColors.Film.copy(alpha = .88f), 1f to JournalColors.Film)))
        }
        storyYear(memory)?.let { year -> Text(year.toString(), style = careNativeBody(10f, true), color = if (photo != null) Color.White else CareColors.SecondaryInk,
            modifier = Modifier.align(Alignment.TopStart).padding(6.dp).background(if (photo != null) JournalColors.Film.copy(alpha = .72f) else CareColors.Surface.copy(alpha = .9f), CircleShape).padding(horizontal = 6.dp, vertical = 3.dp)) }
        Text(memory.title, style = careNativeBody(11f, true, 1f), color = if (photo != null) Color.White else CareColors.Ink, maxLines = 2, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth().padding(7.dp))
    }
}

@Composable
internal fun CarePersonDetailContent(person: Person, memories: List<Memory>, storageScope: String,
    onBack: () -> Unit, onMemory: (Memory) -> Unit, onCompose: () -> Unit, onMemoir: () -> Unit) {
    val events = memories.filter { person.id in it.personIds }.sortedByDescending { it.createdAt }
    val ownStories = events.any { it.primaryPersonId == person.id }
    val role = person.relationship.ifBlank { person.name }
    CarePage {
        CareNativeBackBar("人物资料", onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp).padding(top = 6.dp, bottom = 16.dp)) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Brush.linearGradient(listOf(Color(0xFFFCEBDD), Color(0xFFF7E1CF))))
                .drawBehind { drawCircle(Color.White.copy(alpha = .35f), 80.dp.toPx(), Offset(size.width - 60.dp.toPx(), size.height - 40.dp.toPx())) }
                .padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    LocalPortrait(person.id, person, storageScope, 88.dp, care = true)
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(role, style = careNativeBody(12f), color = JournalColors.AccentDeep,
                            modifier = Modifier.background(Color.White, CircleShape).padding(horizontal = 10.dp).height(24.dp).wrapContentHeight(Alignment.CenterVertically))
                        Text(person.name, style = careNativeStory(25f), color = CareColors.Ink)
                        val birthday = person.birthDate?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
                        Text("生日 · ${birthday?.let { "${it.year} 年 ${it.monthValue} 月 ${it.dayOfMonth} 日" } ?: "待补充"}", style = careNativeBody(12f), color = JournalColors.Muted)
                    }
                }
                Text("还有很多故事，等你慢慢说。", style = careNativeStory(14f), color = Color(0xFF9A7B62))
            }
            CareNativeCard(Modifier.fillMaxWidth().padding(top = 14.dp).clickable(enabled = ownStories, role = Role.Button, onClick = onMemoir).testTag("person-memoir")) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    CareNativeIconTile("book", CareColors.ButterSoft, JournalColors.ButterInk, 44.dp, 14.dp)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("制作／继续制作回忆录", style = careNativeBody(15.5f, true), color = CareColors.Ink)
                        Text("封面、目录、故事和照片排成一本 PDF", style = careNativeBody(12f), color = JournalColors.Muted)
                    }
                    JournalIcon("chev", tint = JournalColors.Muted)
                }
            }
            if (!ownStories) Text("先保存一段以这位家人为主人物的回忆，再制作回忆录。", Modifier.padding(top = 8.dp), style = careNativeBody(12f), color = JournalColors.Muted)
            Row(Modifier.fillMaxWidth().padding(horizontal = 2.dp).padding(top = 22.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("关于$role", style = careNativeStory(19f), color = CareColors.Ink)
                Spacer(Modifier.weight(1f)); Text("${events.size} 段", style = careNativeBody(12f), color = JournalColors.Muted)
            }
            Column(Modifier.drawBehind {
                if (size.height > 72.dp.toPx()) drawLine(JournalColors.Line, Offset(3.5.dp.toPx(), 36.dp.toPx()), Offset(3.5.dp.toPx(), size.height - 36.dp.toPx()), 1.dp.toPx())
            }, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                events.forEachIndexed { index, memory ->
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        val color = listOf(JournalColors.Accent, JournalColors.Sage, JournalColors.Butter)[index % 3]
                        val ring = listOf(CareColors.Soft, CareColors.SageSoft, CareColors.ButterSoft)[index % 3]
                        Box(Modifier.size(8.dp).drawBehind { drawCircle(ring, 7.dp.toPx()) }.background(color, CircleShape))
                        CareNativeCard(Modifier.weight(1f).clickable(role = Role.Button) { onMemory(memory) }, 10.dp) {
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                memory.media.firstOrNull()?.let { MemoryPhoto(it, Modifier.size(58.dp), radius = 12.dp) }
                                    ?: CareNativeIconTile("quote", CareColors.SageSoft, JournalColors.SageInk, 58.dp)
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Text(memory.title, style = careNativeStory(15.5f), color = CareColors.Ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(listOfNotNull(memory.dateLabel, careMeaningful(memory.place.value)).joinToString(" · "), style = careNativeBody(12f), color = JournalColors.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                            }
                        }
                    }
                }
            }
        }
        JournalAction("记录与${role}的故事", modifier = Modifier.padding(horizontal = 22.dp).padding(top = 8.dp, bottom = 16.dp), icon = "plus", onClick = onCompose)
    }
}
