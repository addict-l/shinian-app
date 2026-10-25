package cn.shinian.app.ui.browse

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import cn.shinian.app.R
import cn.shinian.app.data.*
import cn.shinian.app.ui.theme.*
import cn.shinian.app.ui.care.*
import java.time.LocalDate
import java.time.format.TextStyle
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun BrowseScroll(loading:Boolean=false,onRefresh:()->Unit={},care:Boolean=false,
    modifier:Modifier=Modifier,topPadding:Dp=if(care)20.dp else 6.dp,
    spacing:Dp=if(care)18.dp else 14.dp,content:@Composable ColumnScope.()->Unit) {
    val page: @Composable BoxScope.()->Unit = {
        PullToRefreshBox(loading,onRefresh,Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize()
                .verticalScroll(rememberScrollState()).padding(horizontal=if(care)20.dp else 22.dp)
                .padding(top=topPadding,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(spacing),content=content)
        }
    }
    if(care) CareBackdrop(modifier.fillMaxSize(),content = page) else JournalBackdrop(modifier.fillMaxSize(),page)
}

@Composable
fun HomeScreen(
    people:List<Person>,memories:List<Memory>,loading:Boolean=false,error:String?=null,care:Boolean=false,
    onRefresh:()->Unit={},onNewMemory:()->Unit={},onAllMemories:()->Unit={},onMemory:(Memory)->Unit={},onProfile:()->Unit={},onContinue:(Person)->Unit={},
) {
    if (care) {
        CareHomeScreen(people, memories, loading, error, onRefresh, onNewMemory, onAllMemories, onMemory, onContinue)
        return
    }
    val events=memories.sortedByDescending{it.createdAt};val first=events.firstOrNull()
    BrowseScroll(loading,onRefresh,care) {
        if(care) {
            Text("拾年 · 关怀模式",style=JournalTypography.body(18),color=JournalColors.AuthAccent,
                modifier=Modifier.fillMaxWidth(),textAlign=TextAlign.Center)
            Image(painterResource(R.drawable.journal_welcome),null,Modifier.fillMaxWidth().height(160.dp).clip(RoundedCornerShape(30.dp)),contentScale=ContentScale.Crop)
            PageTitle("慢慢讲，都是好时光。","把您的故事，好好留下来。",true)
            JournalAction("开始讲述",true,modifier=Modifier.testTag("home.newMemory"),onClick=onNewMemory)
            if(first!=null) {
                SectionHeading("最近的回忆","全部",true,onAllMemories)
                MemoryCard(first,care=true,showsPhoto=false,onClick={onMemory(first)})
            } else if(!loading&&error==null)Text("还没有回忆。点“开始讲述”，留下第一段故事。",style=JournalTypography.body(22),color=JournalColors.SecondaryInk)
        } else {
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                Text("拾年",style=JournalTypography.body(12,true),color=JournalColors.AccentDeep)
                Text("   ·   ${LocalDate.now().dayOfWeek.getDisplayName(TextStyle.FULL,Locale.SIMPLIFIED_CHINESE)}",style=JournalTypography.body(12),color=JournalColors.Muted)
                Spacer(Modifier.weight(1f))
                if(first!=null)IconButton(onProfile){LocalPortrait("profile",size=38.dp)}
            }
            PageTitle("把平凡，\n留成永远。",if(first!=null||loading||error!=null)"有些瞬间，值得被好好记住。" else null)
            if(first!=null) {
                Column(Modifier.fillMaxWidth().background(Brush.linearGradient(listOf(JournalColors.AccentGlow,JournalColors.AccentDark)),RoundedCornerShape(26.dp)).padding(20.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                    Text("今天，想起了谁？",style=JournalTypography.body(13),color=Color.White.copy(alpha=.85f))
                    Text("和 AI 聊一聊，\n把记忆慢慢说出来",style=JournalTypography.story(21),color=Color.White)
                    Button(onNewMemory,colors=ButtonDefaults.buttonColors(containerColor=Color.White,contentColor=JournalColors.AccentDeep),modifier=Modifier.heightIn(min=48.dp).testTag("home.newMemory")) {
                        JournalIcon("plus",tint=JournalColors.AccentDeep);Spacer(Modifier.width(6.dp));Text("记录一段回忆",style=JournalTypography.body(14,true))
                    }
                }
                SectionHeading("最近的回忆","查看全部 ›",false,onAllMemories,tag="home.allMemories")
                Box(Modifier.testTag("home.featured")){MemoryCard(first,featured=true,onClick={onMemory(first)})}
            } else if(!loading&&error==null) {
                Image(painterResource(R.drawable.journal_welcome),null,Modifier.fillMaxWidth().height(230.dp),contentScale=ContentScale.Crop)
                Text("把想念的人，写进第一页",style=JournalTypography.story(20),color=JournalColors.Ink,textAlign=TextAlign.Center,modifier=Modifier.fillMaxWidth())
                JournalCard(Modifier.fillMaxWidth().testTag("home.empty")) {
                    HomeOnboardingStep(if(people.isEmpty())"1"else"✓","添加第一位家人","先记下家人的名字，再留住那些平凡又珍贵的瞬间。",JournalColors.Soft,JournalColors.AccentDeep)
                    HorizontalDivider(Modifier.padding(start=46.dp,top=14.dp,bottom=14.dp),color=JournalColors.Line)
                    HomeOnboardingStep("2","第一段回忆，慢慢说","一个熟悉的声音，一顿家常饭。从你此刻想起的小事开始。",JournalColors.SageSoft,JournalColors.SageInk)
                }
                JournalAction("记录第一段回忆",modifier=Modifier.testTag("home.newMemory"),icon="plus",onClick=onNewMemory)
            }
        }
        if(loading&&events.isEmpty())CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
        BrowseError(error,care,onRefresh)
    }
}

@Composable
private fun HomeOnboardingStep(number:String,title:String,message:String,fill:Color,ink:Color) {
    Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(34.dp).background(fill,androidx.compose.foundation.shape.CircleShape),contentAlignment=Alignment.Center){Text(number,style=JournalTypography.story(15),color=ink)}
        Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Text(title,style=JournalTypography.body(16,true),color=JournalColors.Ink)
            Text(message,style=JournalTypography.body(12),color=JournalColors.Muted)
        }
    }
}

@Composable
internal fun SectionHeading(title:String,action:String,care:Boolean=false,onClick:()->Unit,tag:String?=null) {
    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
        Text(title,style=if(care)JournalTypography.body(24,true)else JournalTypography.story(19),color=JournalColors.Ink,modifier=Modifier.weight(1f))
        TextButton(onClick,Modifier.heightIn(min=48.dp).then(if(tag!=null)Modifier.testTag(tag)else Modifier)){Text(action,style=JournalTypography.body(if(care)20 else 13),color=JournalColors.AccentDeep)}
    }
}

@Composable
internal fun MemoryCard(memory:Memory,care:Boolean=false,featured:Boolean=false,modifier:Modifier=Modifier,grid:Boolean=false,showsPhoto:Boolean=true,onClick:()->Unit) {
    if (care) { CareMemoryCard(memory, emptyList(), compact = !showsPhoto, modifier = modifier, onClick = onClick); return }
    JournalCard(modifier.fillMaxWidth().clickable(onClick=onClick).testTag("memory.card.${memory.id}"),care,
        contentPadding=PaddingValues(if(care)18.dp else if(featured)10.dp else if(grid)8.dp else 16.dp)) {
        if(showsPhoto&&memory.media.isNotEmpty()) {
            MemoryPhoto(memory.media.first(),Modifier.fillMaxWidth().height(if(care)140.dp else if(featured)150.dp else 120.dp).testTag("memory.card.photo.${memory.id}"))
            Spacer(Modifier.height(12.dp))
        }
        if(!grid){Text("${memory.personName} · ${memory.dateLabel}",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk);Spacer(Modifier.height(8.dp))}
        Text(memory.title,style=if(care)JournalTypography.body(24,true)else JournalTypography.story(if(featured)18 else if(grid)15 else 16),color=JournalColors.Ink,
            maxLines=if(care)Int.MAX_VALUE else if(grid)1 else 2,overflow=TextOverflow.Ellipsis)
        Spacer(Modifier.height(6.dp))
        if(grid)Text("${memory.personName} · ${memory.dateLabel.removePrefix(storyYear(memory)?.let{"${it}年"}?:"\u0000")}",style=JournalTypography.body(12),color=JournalColors.Muted,maxLines=1,overflow=TextOverflow.Ellipsis)
        else Text(memory.content,style=JournalTypography.body(if(care)20 else 13),color=JournalColors.SecondaryInk,maxLines=2,overflow=TextOverflow.Ellipsis)
        if(care) {Spacer(Modifier.height(12.dp));Text("打开看看   →",style=JournalTypography.body(20,true),color=JournalColors.AuthAccent)}
    }
}

@Composable
private fun MemoryCollectionRow(memory:Memory,onClick:()->Unit) {
    val photo=memory.media.firstOrNull()
    JournalCard(Modifier.fillMaxWidth().clickable(onClick=onClick).testTag("memory.card.${memory.id}"),contentPadding=PaddingValues(if(photo!=null)10.dp else 14.dp)) {
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
            if(photo!=null)MemoryPhoto(photo,Modifier.size(70.dp))
            else Box(Modifier.size(44.dp).background(JournalColors.SageSoft,RoundedCornerShape(14.dp)),contentAlignment=Alignment.Center){JournalIcon("quote",tint=JournalColors.SageInk)}
            Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Text(memory.title,style=JournalTypography.story(16),color=JournalColors.Ink,maxLines=1,overflow=TextOverflow.Ellipsis)
                Text(if(photo!=null)memory.content else "${memory.personName} · ${memory.dateLabel}",style=JournalTypography.body(12),color=JournalColors.Muted,maxLines=if(photo!=null)2 else 1,overflow=TextOverflow.Ellipsis)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemoriesScreen(
    people:List<Person>,memories:List<Memory>,loading:Boolean=false,error:String?=null,care:Boolean=false,isRoot:Boolean=false,
    onBack:()->Unit={},onMemory:(Memory)->Unit={},onCompose:()->Unit={},onRefresh:()->Unit={},
) {
    if (care) {
        CareMemoriesScreen(people, memories, loading, error, isRoot, onBack, onMemory, onCompose, onRefresh)
        return
    }
    var search by rememberSaveable{mutableStateOf("")};var selected by rememberSaveable{mutableStateOf<String?>(null)}
    var searching by rememberSaveable{mutableStateOf(false)}
    val filtered=memories.filter{(care||selected==null||selected in it.personIds)&&
        (search.isBlank()||"${it.title} ${it.content} ${it.personName}".contains(search,ignoreCase=true))}.sortedByDescending{it.createdAt}
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            if(!isRoot)BrowseBar(if(care)"珍藏的回忆" else "",care,onBack)
            PullToRefreshBox(loading,onRefresh,Modifier.weight(1f).fillMaxWidth()) {
            LazyColumn(Modifier.fillMaxSize().testTag("memories.list").then(if(care)Modifier.background(Color(0xFFF8F3E9))else Modifier),
                contentPadding=PaddingValues(horizontal=if(care)20.dp else 22.dp,vertical=16.dp),verticalArrangement=Arrangement.spacedBy(if(care)16.dp else 14.dp)) {
                item("header"){Column(verticalArrangement=Arrangement.spacedBy(14.dp)) {
                if(!care||isRoot)PageTitle(if(care)"珍藏的回忆" else "所有回忆",if(care)"点开一段，慢慢看看。" else "那些平凡日子里的，珍贵片刻。   ${memories.size} 段回忆",care)
                if(!care||searching)SearchBox(search,{search=it},"搜索回忆、人物或一句话",care,if(care)"care.memories.search" else "memories.search")
                else if(memories.isNotEmpty())TextButton({searching=true}){Text("找一段回忆",style=JournalTypography.body(20))}
                if(!care)Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected==null,{selected=null},label={Text("全部")},shape=androidx.compose.foundation.shape.CircleShape,
                        colors=FilterChipDefaults.filterChipColors(selectedContainerColor=JournalColors.Accent,selectedLabelColor=Color.White,containerColor=JournalColors.Surface))
                    people.forEach{person->FilterChip(selected==person.id,{selected=person.id},label={Text(person.relationship.ifBlank{person.name})},shape=androidx.compose.foundation.shape.CircleShape,
                        colors=FilterChipDefaults.filterChipColors(selectedContainerColor=JournalColors.Accent,selectedLabelColor=Color.White,containerColor=JournalColors.Surface))}
                }
                BrowseError(error,care,onRefresh)
                }}
                if(filtered.isEmpty()&&!loading&&error==null) {
                    item("empty"){Column(verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    Spacer(Modifier.height(32.dp))
                    Text(if(search.isBlank())"还没有回忆，先讲一段故事吧。" else "没有找到相关回忆，换一句话试试。",style=JournalTypography.body(if(care)22 else 16),color=JournalColors.SecondaryInk)
                    if(search.isBlank())JournalAction("开始讲述",care,onClick=onCompose)
                    }}
                }
                if(care)items(filtered,key={it.id}) {memory->MemoryCard(memory,true,onClick={onMemory(memory)})}
                else {
                    val groups=filtered.groupBy{storyYear(it)}.toSortedMap(compareByDescending<Int?>{it?:Int.MIN_VALUE})
                    groups.forEach{(year,group)->
                        item("year-$year"){Text(year?.let{"— $it 年"}?:"— 时间待补充",style=JournalTypography.body(12),color=JournalColors.Muted)}
                        val photo=group.filter{it.media.isNotEmpty()};val paired=photo.take(photo.size/2*2)
                        items(paired.chunked(2),key={row->row.joinToString{it.id}}){row->Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                            row.forEach{memory->MemoryCard(memory,modifier=Modifier.weight(1f),grid=true,onClick={onMemory(memory)})}
                        }}
                        items(photo.drop(paired.size)+group.filter{it.media.isEmpty()},key={it.id}){memory->MemoryCollectionRow(memory,onClick={onMemory(memory)})}
                    }
                }
            }
            }
        }
    }
}
