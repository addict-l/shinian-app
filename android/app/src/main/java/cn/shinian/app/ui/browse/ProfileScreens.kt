package cn.shinian.app.ui.browse

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import cn.shinian.app.data.*
import cn.shinian.app.ui.media.rememberPhotoPicker
import cn.shinian.app.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun ProfileScreen(
    people:List<Person>,memories:List<Memory>,storageScope:String="",displayName:String="回忆的收藏者",care:Boolean=false,
    onAllMemories:()->Unit={},onFamily:()->Unit={},onSettings:()->Unit={},onPrivacy:()->Unit={},onCareChange:(Boolean)->Unit={},
) {
    val context=LocalContext.current;val scope=rememberCoroutineScope();val env=LocalBrowseStorageScope.current
    val accountScope=storageScope.ifBlank{env};var portraitRevision by remember{mutableIntStateOf(0)}
    var portraitError by remember{mutableStateOf<String?>(null)};var switchMode by rememberSaveable{mutableStateOf(false)}
    val picker=rememberPhotoPicker(1){uris->
        val uri=uris.firstOrNull()
        if(uri!=null)scope.launch {try{savePortrait(context,accountScope,"profile",uri);portraitRevision++}catch(e:Exception){portraitError=e.message}}
    }
    BrowseScroll(care=care) {
        if(care) {
            CareMoreContent(people, memories, onFamily, onSettings, onPrivacy) { switchMode = true }
        } else {
            PageTitle("我的")
            Column(Modifier.fillMaxWidth().background(Brush.linearGradient(listOf(Color(0xFFE8EEDD),Color(0xFFF6EBD9))),RoundedCornerShape(28.dp)).padding(20.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
                Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
                    LocalPortrait("profile",scope=accountScope,size=66.dp,refresh=portraitRevision,
                        modifier=Modifier.clickable(onClickLabel="更换我的头像",onClick=picker))
                    Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text(displayName,style=JournalTypography.story(21),color=JournalColors.Ink)
                        Text("和家人一起，记住生活。",style=JournalTypography.body(12),color=JournalColors.SecondaryInk)
                    }
                }
                Row(Modifier.fillMaxWidth().background(JournalColors.Surface.copy(alpha=.75f),RoundedCornerShape(18.dp)).padding(vertical=12.dp)) {
                    ProfileStatistic(people.size,"家庭人物",Modifier.weight(1f))
                    Box(Modifier.width(1.dp).height(38.dp).background(JournalColors.Line))
                    ProfileStatistic(memories.map{it.id}.distinct().size,"珍藏回忆",Modifier.weight(1f))
                    Box(Modifier.width(1.dp).height(38.dp).background(JournalColors.Line))
                    ProfileStatistic(people.count{person->memories.any{person.id in it.personIds}},"有故事的家人",Modifier.weight(1f))
                }
            }
            JournalCard(Modifier.fillMaxWidth(),contentPadding=PaddingValues(horizontal=16.dp,vertical=4.dp)) {
                ProfileRow("我的全部回忆","heart",JournalColors.Soft,JournalColors.AccentDeep,onAllMemories)
                HorizontalDivider(color=JournalColors.Line)
                ProfileRow("管理家庭人物","users",JournalColors.SageSoft,JournalColors.SageInk,onFamily)
            }
            JournalCard(Modifier.fillMaxWidth(),contentPadding=PaddingValues(horizontal=16.dp,vertical=4.dp)) {
                ProfileRow("设置","gear",JournalColors.ButterSoft,JournalColors.ButterInk,onSettings)
                HorizontalDivider(color=JournalColors.Line)
                ProfileRow("隐私与数据","shield",JournalColors.RoseSoft,JournalColors.RoseInk,onPrivacy)
            }
            Text("拾年 · 留住时光",style=JournalTypography.story(14),color=JournalColors.SecondaryInk,modifier=Modifier.fillMaxWidth(),textAlign=TextAlign.Center)
            Text("给回忆一个长久安放的地方。",style=JournalTypography.body(12),color=JournalColors.Muted,modifier=Modifier.fillMaxWidth(),textAlign=TextAlign.Center)
        }
    }
    if(switchMode)AlertDialog(onDismissRequest={switchMode=false},title={Text("切换到普通模式？")},
        text={Text("家人和回忆都会保留。之后可以在设置中重新开启关怀模式。")},
        confirmButton={TextButton({switchMode=false;onCareChange(false)}){Text("切换普通模式")}},
        dismissButton={TextButton({switchMode=false}){Text("继续使用关怀模式")}})
    portraitError?.let{message->AlertDialog(onDismissRequest={portraitError=null},title={Text("头像未保存")},text={Text(message)},confirmButton={TextButton({portraitError=null}){Text("知道了")}})}
}

@Composable
private fun ProfileStatistic(count:Int,title:String,modifier:Modifier) {
    Column(modifier.testTag("profile.stat.$title"),horizontalAlignment=Alignment.CenterHorizontally) {
        Text(count.toString(),style=JournalTypography.story(22),color=JournalColors.AccentDeep)
        Text(title,style=JournalTypography.body(12),color=JournalColors.Muted)
    }
}

@Composable
private fun ProfileRow(title:String,icon:String,fill:Color,ink:Color,onClick:()->Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min=64.dp).clickable(onClick=onClick),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(38.dp).background(fill,RoundedCornerShape(12.dp)),contentAlignment=Alignment.Center){JournalIcon(icon,tint=ink)}
        Text(title,style=JournalTypography.body(16),color=JournalColors.Ink,modifier=Modifier.weight(1f))
        JournalIcon("chev",tint=JournalColors.Muted)
    }
}

@Composable
fun SettingsScreen(
    displayName:String="回忆的收藏者",care:Boolean=false,loading:Boolean=false,error:String?=null,
    onDisplayNameChange:(String)->Unit={},onCareChange:(Boolean)->Unit={},onLogout:()->Unit={},onBack:()->Unit={},
) {
    if (care) { CareSettingsContent(displayName, loading, error, onDisplayNameChange, onCareChange, onLogout, onBack); return }
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding()) {
            BrowseBar("设置",care,onBack)
            BrowseScroll(care=care,modifier=Modifier.weight(1f)) {
                JournalCard(Modifier.fillMaxWidth(),care) {
                    Row(verticalAlignment=Alignment.CenterVertically) {
                        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                            Text("关怀模式",style=JournalTypography.body(if(care)22 else 18,true),color=JournalColors.Ink)
                            Text("大字号、大按钮，更简单的讲述与回看。",style=JournalTypography.body(if(care)18 else 14),color=JournalColors.SecondaryInk)
                        }
                        Switch(care,onCareChange,modifier=Modifier.testTag("settings.careMode"))
                    }
                }
                Text("个人展示",style=JournalTypography.body(if(care)20 else 12),color=JournalColors.Muted)
                JournalInput("显示名称",displayName,onDisplayNameChange,care=care,tag="settings.displayName")
                Text("家庭胶片",style=JournalTypography.body(if(care)20 else 12),color=JournalColors.Muted)
                JournalCard(Modifier.fillMaxWidth(),care) {
                    Text("每位家人拥有自己的胶卷，左右滑动翻阅回忆。点击“查看全部家人”可搜索和浏览所有胶卷，长按人物头像可以更换照片。",style=JournalTypography.body(if(care)20 else 14),color=JournalColors.SecondaryInk)
                }
                Text("关于",style=JournalTypography.body(if(care)20 else 12),color=JournalColors.Muted)
                JournalCard(Modifier.fillMaxWidth(),care) {
                    Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                        Box(Modifier.size(54.dp).background(Brush.linearGradient(listOf(JournalColors.AccentGlow,JournalColors.AccentDark)),RoundedCornerShape(16.dp)),contentAlignment=Alignment.Center){Text("拾",style=JournalTypography.story(22),color=Color.White)}
                        Column(verticalArrangement=Arrangement.spacedBy(3.dp)) {
                            Text("拾年 · 留住时光",style=JournalTypography.story(if(care)24 else 16),color=JournalColors.Ink)
                            Text("界面版本 V1",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.Muted)
                        }
                    }
                }
                JournalAction(if(loading)"正在退出…"else"退出家庭登录",care,secondary=true,loading=loading,modifier=Modifier.testTag("settings.logout"),onClick=onLogout)
                Text("仅退出当前设备，家庭和回忆会保留。",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                BrowseError(error,care,onLogout)
            }
        }
    }
}

@Composable
fun PrivacyScreen(care:Boolean=false,onBack:()->Unit={}) {
    if (care) { CarePrivacyContent(onBack); return }
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding()) {
            BrowseBar("隐私与数据",care,onBack)
            BrowseScroll(care=care,modifier=Modifier.weight(1f)) {
                Column(Modifier.fillMaxWidth().background(JournalColors.SageSoft,RoundedCornerShape(24.dp)).padding(18.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    Text("你的回忆，只属于你的家。",style=JournalTypography.story(if(care)24 else 16),color=JournalColors.SageInk)
                    Text("只有点击“保存这段回忆”后，草稿才会成为正式回忆。",style=JournalTypography.body(if(care)20 else 13),color=JournalColors.SageInk)
                }
                PrivacyCard("照片与 AI 对话","image",listOf("照片选择只显示你授权访问的照片。你可以在系统中管理照片访问范围，也可以使用系统选图入口。只有确认选择的照片才会加入讲述或编辑内容。","对话文字由服务器调用 AI 整理。照片上传到家庭服务器，用于聊天展示、回忆和回忆录，不发送给 AI 分析。"),care)
                PrivacyCard("回忆数据","heart",listOf("人物和已保存回忆通过家庭账号同步到服务器。草稿需经你确认保存，才会出现在回忆列表中。","尚未发送的对话、制作缓存、显示名称和人物头像保存在本机；头像不会自动上传或同步。"),care)
                PrivacyCard("数据管理","gear",listOf("可在人物列表和回忆详情中删除相应记录；回忆录支持 PDF 预览与导出。批量导出和账号权限管理暂无服务端接口。"),care)
            }
        }
    }
}

@Composable
private fun PrivacyCard(title:String,icon:String,paragraphs:List<String>,care:Boolean) {
    JournalCard(Modifier.fillMaxWidth(),care) {
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            JournalIcon(icon,tint=JournalColors.Accent)
            Text(title,style=JournalTypography.body(if(care)23 else 16,true),color=JournalColors.Ink)
        }
        paragraphs.forEach{Spacer(Modifier.height(8.dp));Text(it,style=JournalTypography.body(if(care)20 else 14),color=JournalColors.SecondaryInk)}
    }
}
