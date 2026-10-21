package cn.shinian.app.ui.browse

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import cn.shinian.app.data.*
import cn.shinian.app.ui.media.rememberPhotoPicker
import cn.shinian.app.ui.theme.*
import java.time.*
import java.util.UUID
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class,ExperimentalFoundationApi::class)
@Composable
fun PersonSelectionScreen(
    people:List<Person>,loading:Boolean=false,error:String?=null,care:Boolean=false,
    onSelect:(Person)->Unit={},onAdd:()->Unit={},onDelete:(Person)->Unit={},onRefresh:()->Unit={},onBack:()->Unit={},
) {
    var search by rememberSaveable{mutableStateOf("")};var pendingDelete by remember{mutableStateOf<Person?>(null)}
    val matches=people.filter{search.isBlank()||"${it.name} ${it.relationship}".contains(search,true)}
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column {
            if(care)BrowseBar("选择家人",true,onBack)
            BrowseScroll(loading,onRefresh,care) {
                if(!care)Text("新的回忆   ·   02 选择人物",style=JournalTypography.body(12),color=JournalColors.Muted)
                PageTitle(if(care)"这次记录谁的故事？"else"今天，想起了谁？",if(care)"点一下名字，就可以开始。"else"选择一位家人，聊聊你们的故事。",care)
                if(!care)SearchBox(search,{search=it},"搜索姓名或家庭身份")
                if(!care&&people.isNotEmpty())Text("点击人物，即可开始 AI 对话。",style=JournalTypography.body(12),color=JournalColors.Muted)
                matches.forEach{person->
                    val density=LocalDensity.current;val revealPx=with(density){84.dp.toPx()}
                    var reveal by rememberSaveable(person.id){mutableFloatStateOf(0f)}
                    Box(Modifier.fillMaxWidth().height(IntrinsicSize.Min).then(if(care)Modifier else Modifier.pointerInput(person.id){
                        detectHorizontalDragGestures(onDragEnd={reveal=if(reveal>revealPx/2)revealPx else 0f},onDragCancel={reveal=0f}) {change,amount->
                            change.consume();reveal=(reveal-amount).coerceIn(0f,revealPx)
                        }
                    })) {
                        if(reveal>0&&!care)Box(Modifier.matchParentSize().background(Color(0xFFE9A08F),RoundedCornerShape(22.dp)),contentAlignment=Alignment.CenterEnd) {
                            TextButton({reveal=0f;pendingDelete=person},Modifier.width(84.dp).fillMaxHeight()) {
                                Column(horizontalAlignment=Alignment.CenterHorizontally) {JournalIcon("trash","删除${person.name}",tint=Color.White);Text("删除",style=JournalTypography.body(12),color=Color.White)}
                            }
                        }
                        JournalCard(Modifier.fillMaxWidth().padding(end=with(density){reveal.toDp()})
                            .combinedClickable(onClick={if(reveal<8)onSelect(person)},onLongClick={if(!care)pendingDelete=person})
                            .testTag("member.${person.id}").semantics {customActions=listOf(CustomAccessibilityAction("选择人物"){onSelect(person);true},CustomAccessibilityAction("删除人物"){pendingDelete=person;true})},care,contentPadding=PaddingValues(horizontal=if(care)16.dp else 14.dp,vertical=if(care)16.dp else 12.dp)) {
                            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
                                LocalPortrait(person.id,person,size=if(care)56.dp else 52.dp)
                                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                                    if(care){Text(person.name,style=JournalTypography.body(24,true),color=JournalColors.Ink);Text(person.relationship,style=JournalTypography.body(18),color=JournalColors.SecondaryInk)}
                                    else {
                                        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                            Text(person.relationship.ifBlank{person.name},style=JournalTypography.body(17,true),color=JournalColors.Ink)
                                            if(person.relationship.isNotBlank())Text(person.name,style=JournalTypography.body(12),color=JournalColors.Muted)
                                        }
                                        Text(if(person.memoryCount==0)"还没有回忆"else"${person.memoryCount} 段回忆",style=JournalTypography.body(12),color=JournalColors.Muted)
                                    }
                                }
                                if(!care)Box(Modifier.size(34.dp).background(JournalColors.Soft,CircleShape),contentAlignment=Alignment.Center){JournalIcon("chat",tint=JournalColors.AccentDeep)}
                                else JournalIcon("chev")
                            }
                        }
                    }
                }
                if(matches.isEmpty()&&!loading)Text(if(people.isEmpty())"先添加一位家人，家人的名字会出现在这里。"else"没有找到这位家人，试试真实姓名或家庭身份。",style=JournalTypography.body(if(care)22 else 15),color=JournalColors.SecondaryInk)
                BrowseError(error,care,onRefresh)
                JournalAction(if(care)"添加一位家人"else"添加新的家庭人物",care,secondary=true,modifier=Modifier.testTag("members.addAnother"),icon="plus",onClick=onAdd)
            }
        }
    }
    pendingDelete?.let{person->JournalBottomSheet("删除「${person.name}」？","该人物将从列表中移除，仅属于此人的回忆将不再显示。",care,onCancel={pendingDelete=null}) {
        JournalSheetAction("删除","trash",destructive=true,care=care){pendingDelete=null;onDelete(person)}
    }}
}

@OptIn(ExperimentalLayoutApi::class,ExperimentalMaterial3Api::class)
@Composable
fun AddPersonScreen(
    loading:Boolean=false,error:String?=null,care:Boolean=false,onAdd:(String,String,String)->Unit={_,_,_->},onBack:()->Unit={},
) {
    var name by rememberSaveable{mutableStateOf("")};var relationship by rememberSaveable{mutableStateOf("")}
    var birthday by rememberSaveable{mutableStateOf<String?>(null)};var picker by rememberSaveable{mutableStateOf(false)}
    val focus=LocalFocusManager.current
    val valid=name.isNotBlank()&&relationship.isNotBlank()&&birthday?.let{runCatching{!LocalDate.parse(it).isAfter(LocalDate.now())}.getOrDefault(false)}==true
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding()) {
            if(care)BrowseBar("添加家人",true,onBack) else Box(Modifier.fillMaxWidth().height(48.dp)) {
                IconButton(onBack,enabled=!loading,modifier=Modifier.align(Alignment.CenterStart).padding(start=12.dp).testTag("member.close")){JournalIcon("x","关闭")}
                Row(Modifier.align(Alignment.Center),horizontalArrangement=Arrangement.spacedBy(6.dp),verticalAlignment=Alignment.CenterVertically) {
                    Box(Modifier.size(22.dp,6.dp).background(JournalColors.Accent,CircleShape));repeat(2){Box(Modifier.size(6.dp).background(JournalColors.Line,CircleShape))}
                }
            }
            BrowseScroll(care=care,modifier=Modifier.weight(1f)) {
                if(!care)Text("新的回忆   ·   01 添加人物",style=JournalTypography.body(12),color=JournalColors.Muted)
                PageTitle(if(care)"先记下家人的名字"else"每一段回忆，\n都从一个人开始。",if(care)"这些资料，之后也可以查看。"else"把重要的人，放进你的回忆里。",care,size=27)
                Text(if(care)"怎么称呼这位家人"else"家庭身份 · 选一个熟悉的称呼",style=JournalTypography.body(if(care)20 else 14,true),color=JournalColors.Ink)
                if(!care)FlowRow(horizontalArrangement=Arrangement.spacedBy(8.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    listOf("爷爷","奶奶","外公","外婆","爸爸","妈妈","姑姑","舅舅").forEach{role->
                        FilterChip(relationship==role,{relationship=role;focus.clearFocus()},label={Text(role,style=JournalTypography.body(14))},shape=CircleShape,
                            colors=FilterChipDefaults.filterChipColors(selectedContainerColor=JournalColors.Accent,selectedLabelColor=Color.White,containerColor=JournalColors.Surface),modifier=Modifier.heightIn(min=48.dp).testTag("member.role.$role"))
                    }
                }
                JournalInput("家庭身份",relationship,{relationship=it},"例如爷爷、奶奶",care,!loading,"member.relationship",next=true)
                if(!care)Text("家庭身份支持自定义，例如姑姑、舅舅。",style=JournalTypography.body(12),color=JournalColors.SecondaryInk)
                JournalInput("真实姓名",name,{name=it},"填写家人的真实姓名",care,!loading,"member.realName")
                JournalCard(Modifier.fillMaxWidth().clickable(enabled=!loading){focus.clearFocus();picker=true}.testTag("member.birthday"),care) {
                    Text("生日",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                    Row(verticalAlignment=Alignment.CenterVertically) {
                        Text(birthday?.displayDay()?:"选择家人的生日",style=JournalTypography.body(if(care)22 else 16),color=if(birthday==null)JournalColors.Placeholder else JournalColors.Ink,modifier=Modifier.weight(1f).padding(vertical=8.dp))
                        JournalIcon("cal",tint=JournalColors.Accent)
                    }
                }
                BrowseError(error,care){if(valid)onAdd(name.trim(),relationship.trim(),birthday!!)}
                JournalAction(if(care)"添加并开始讲述"else"添加并继续",care,enabled=valid,loading=loading,modifier=Modifier.testTag("member.add")) {
                    focus.clearFocus();onAdd(name.trim(),relationship.trim(),birthday!!)
                }
                if(!care)TextButton(onBack,Modifier.fillMaxWidth().heightIn(min=48.dp),enabled=!loading){Text("已添加过家人？选择已有的人物 ›",style=JournalTypography.body(14))}
            }
        }
    }
    if(picker) {
        val selected=rememberDatePickerState(initialSelectedDateMillis=runCatching{LocalDate.parse(birthday?:"1950-01-01").atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()}.getOrNull(),
            selectableDates=object:SelectableDates{override fun isSelectableDate(utcTimeMillis:Long)=!Instant.ofEpochMilli(utcTimeMillis).atZone(ZoneOffset.UTC).toLocalDate().isAfter(LocalDate.now())})
        DatePickerDialog(onDismissRequest={picker=false},confirmButton={TextButton({selected.selectedDateMillis?.let{birthday=Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate().toString()};picker=false},enabled=selected.selectedDateMillis!=null,modifier=Modifier.testTag("member.confirmBirthday")){Text("确定")}},
            dismissButton={TextButton({picker=false}){Text("取消")}}){DatePicker(selected,title={Text("家人的生日",modifier=Modifier.padding(20.dp))})}
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun FamilyFilmScreen(
    people:List<Person>,memories:List<Memory>,loading:Boolean=false,error:String?=null,care:Boolean=false,allPeople:Boolean=false,
    storageScope:String="",onRefresh:()->Unit={},onPerson:(Person)->Unit={},onMemory:(Memory)->Unit={},onAdd:(Person?)->Unit={},onAllPeople:()->Unit={},
) {
    var search by rememberSaveable{mutableStateOf("")};var portraitPerson by remember{mutableStateOf<Person?>(null)}
    var portraitRevision by remember{mutableIntStateOf(0)};var portraitError by remember{mutableStateOf<String?>(null)}
    var menuPerson by remember{mutableStateOf<Person?>(null)}
    val context=LocalContext.current;val scope=rememberCoroutineScope();val actualScope=storageScope.ifBlank{LocalBrowseStorageScope.current}
    val picker=rememberPhotoPicker(1){uris->
        val uri=uris.firstOrNull()
        val person=portraitPerson
        if(uri!=null&&person!=null)scope.launch {try{savePortrait(context,actualScope,person.id,uri);portraitRevision++}catch(e:Exception){portraitError=e.message}}
    }
    val filtered=people.filter{search.isBlank()||"${it.name} ${it.relationship}".contains(search,true)}.let{if(allPeople)it else it.take(3)}
    BrowseScroll(loading,onRefresh,care) {
        if(allPeople)BrowseBar("",care,onAllPeople)
        PageTitle(if(allPeople)"家人的胶卷"else"我们的家庭",if(allPeople)"一人一卷，慢慢翻阅。"else"把日子连起来，就成了我们的故事。",care)
        SectionHeading("${people.size} 位家人 · ${memories.map{it.id}.distinct().size} 段回忆",if(allPeople)""else"查看全部家人",care,onAllPeople)
        if(allPeople)SearchBox(search,{search=it},"搜索家人的姓名或身份",care)
        if(!allPeople&&people.isNotEmpty())Text("家人的胶卷",style=JournalTypography.story(20),color=JournalColors.Ink)
        filtered.forEach{person->
            val events=memories.filter{person.id in it.personIds}.sortedWith(compareByDescending<Memory>{storyYear(it)?:Int.MIN_VALUE}.thenByDescending{it.createdAt})
            Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment=Alignment.CenterVertically) {
                    Row(Modifier.weight(1f).combinedClickable(onClick={onPerson(person)},onLongClick={menuPerson=person}).heightIn(min=48.dp).testTag("film.person.${person.name}"),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                        LocalPortrait(person.id,person,actualScope,if(care)56.dp else 38.dp,portraitRevision)
                        Column(Modifier.weight(1f)) {
                            Text(person.relationship.ifBlank{person.name},style=JournalTypography.body(if(care)24 else 15,true),color=JournalColors.Ink)
                            if(person.relationship.isNotBlank())Text(person.name,style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                        }
                        Text("${events.size} 段回忆",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk,modifier=Modifier.testTag("film.count.${person.name}"))
                    }
                    IconButton({onAdd(person)},Modifier.size(48.dp).testTag("film.add.${person.name}")){JournalIcon("plus","记录关于${person.name}的回忆",tint=JournalColors.AccentDeep)}
                }
                Column(Modifier.fillMaxWidth().background(JournalColors.Film,RoundedCornerShape(12.dp)).padding(vertical=6.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                    FilmPerforations()
                    LazyRow(modifier=Modifier.testTag("film.roll.${person.name}"),contentPadding=PaddingValues(horizontal=8.dp,vertical=6.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        items(events,key={it.id}){memory->FilmFrame(memory,care){onMemory(memory)}}
                        if(events.isEmpty())item{Column(Modifier.widthIn(min=240.dp).heightIn(min=if(care)120.dp else 82.dp).clickable{onAdd(person)}.padding(16.dp),verticalArrangement=Arrangement.Center) {
                            Text("这一卷，等一个故事",style=JournalTypography.story(if(care)20 else 14),color=JournalColors.Paper)
                            Text("记下你们的第一段回忆",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.Paper)
                        }}
                    }
                    FilmPerforations()
                }
            }
        }
        if(filtered.isEmpty()&&!loading) {
            Text(if(people.isEmpty())"第一卷，留给谁？"else"没有找到这位家人",style=JournalTypography.story(24),color=JournalColors.Ink)
            if(people.isEmpty())JournalAction("添加一位家人",care,onClick={onAdd(null)})
        }
        BrowseError(error,care,onRefresh)
    }
    menuPerson?.let{person->AlertDialog(onDismissRequest={menuPerson=null},title={Text(person.name)},
        text={Column {TextButton({menuPerson=null;onPerson(person)}){Text("查看人物回忆")};TextButton({menuPerson=null;portraitPerson=person;picker()}){Text("更换人物照片")}}},
        confirmButton={TextButton({menuPerson=null}){Text("取消")}},containerColor=JournalColors.Surface)}
    portraitError?.let{message->AlertDialog(onDismissRequest={portraitError=null},title={Text("人物照片")},text={Text(message)},confirmButton={TextButton({portraitError=null}){Text("确定")}})}
}

@Composable
private fun FilmPerforations() {
    Row(Modifier.fillMaxWidth().padding(horizontal=6.dp),horizontalArrangement=Arrangement.SpaceBetween) {
        repeat(16){Box(Modifier.size(7.dp,5.dp).background(JournalColors.Paper.copy(alpha=.85f),RoundedCornerShape(1.5.dp)))}
    }
}

@Composable
private fun FilmFrame(memory:Memory,care:Boolean,onClick:()->Unit) {
    val hasPhoto=memory.media.isNotEmpty()
    Box(Modifier.size(if(care)150.dp else 101.dp,if(care)120.dp else 82.dp).clip(RoundedCornerShape(7.dp)).background(JournalColors.PaperSecondary).clickable(onClick=onClick)) {
        if(hasPhoto) {MemoryPhoto(memory.media.first(),Modifier.fillMaxSize(),radius=7.dp);Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent,JournalColors.Film))))}
        storyYear(memory)?.let{Text(it.toString(),style=JournalTypography.body(if(care)14 else 10,true),color=if(hasPhoto)Color.White else JournalColors.SecondaryInk,
            modifier=Modifier.align(Alignment.TopStart).padding(6.dp).background(if(hasPhoto)JournalColors.Film.copy(alpha=.72f)else JournalColors.Surface,RoundedCornerShape(20.dp)).padding(horizontal=6.dp,vertical=3.dp))}
        Text(memory.title,style=JournalTypography.body(if(care)18 else 11,true),color=if(hasPhoto)Color.White else JournalColors.Ink,maxLines=2,overflow=TextOverflow.Ellipsis,modifier=Modifier.align(Alignment.BottomStart).padding(7.dp))
    }
}

@Composable
fun PersonDetailScreen(
    person:Person,memories:List<Memory>,care:Boolean=false,storageScope:String="",onBack:()->Unit={},onMemory:(Memory)->Unit={},onCompose:()->Unit={},onMemoir:()->Unit={},
) {
    val events=memories.filter{person.id in it.personIds}.sortedByDescending{it.createdAt}
    val ownStories=events.any{it.primaryPersonId==person.id}
    val actualScope=storageScope.ifBlank{LocalBrowseStorageScope.current}
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            BrowseBar("人物资料",care,onBack)
            BrowseScroll(care=care,modifier=Modifier.weight(1f)) {
                Column(Modifier.fillMaxWidth().background(Brush.linearGradient(listOf(Color(0xFFFCEBDD),Color(0xFFF7E1CF))),RoundedCornerShape(28.dp)).padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    Row(horizontalArrangement=Arrangement.spacedBy(16.dp),verticalAlignment=Alignment.CenterVertically) {
                        LocalPortrait(person.id,person,actualScope,88.dp)
                        Column(verticalArrangement=Arrangement.spacedBy(5.dp)) {
                            Text(person.relationship,style=JournalTypography.body(if(care)20 else 12),color=JournalColors.AccentDeep)
                            Text(person.name,style=JournalTypography.story(if(care)28 else 25),color=JournalColors.Ink)
                            Text("生日 · ${person.birthDate?.displayDay()?:"待补充"}",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                        }
                    }
                    Text("还有很多故事，等你慢慢说。",style=JournalTypography.story(if(care)20 else 14),color=JournalColors.SecondaryInk)
                }
                JournalAction("制作／继续制作回忆录",care,secondary=true,enabled=ownStories,modifier=Modifier.testTag("person-memoir"),onClick=onMemoir)
                if(!ownStories)Text("先保存一段以这位家人为主人物的回忆，再制作回忆录。",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                Text("关于${person.relationship.ifBlank{person.name}}   ·   ${events.size} 段",style=JournalTypography.story(if(care)25 else 20),color=JournalColors.Ink)
                events.forEachIndexed{index,memory->
                    if(care)MemoryCard(memory,true,onClick={onMemory(memory)})
                    else Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                        val colors=listOf(JournalColors.Accent,JournalColors.Sage,JournalColors.Butter)
                        Box(Modifier.size(8.dp).background(colors[index%3],CircleShape))
                        JournalCard(Modifier.weight(1f).clickable{onMemory(memory)},contentPadding=PaddingValues(10.dp)) {
                            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                                if(memory.media.isNotEmpty())MemoryPhoto(memory.media.first(),Modifier.size(58.dp),radius=12.dp)
                                else Box(Modifier.size(58.dp).background(JournalColors.SageSoft,RoundedCornerShape(12.dp)),contentAlignment=Alignment.Center){JournalIcon("quote",tint=JournalColors.SageInk)}
                                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                                    Text(memory.title,style=JournalTypography.story(16),color=JournalColors.Ink,maxLines=1,overflow=TextOverflow.Ellipsis)
                                    Text(memory.dateLabel,style=JournalTypography.body(12),color=JournalColors.Muted,maxLines=1,overflow=TextOverflow.Ellipsis)
                                }
                            }
                        }
                    }
                }
            }
            JournalAction("记录与${person.relationship.ifBlank{person.name}}的故事",care,modifier=Modifier.padding(horizontal=22.dp,vertical=12.dp),onClick=onCompose)
        }
    }
}
