package cn.shinian.app.ui.browse

import android.graphics.Canvas
import android.graphics.Paint
import android.text.Spannable
import android.text.SpannableString
import android.text.style.LeadingMarginSpan
import android.widget.TextView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.res.ResourcesCompat
import cn.shinian.app.R
import cn.shinian.app.data.*
import cn.shinian.app.ui.theme.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun MemoryDetailScreen(
    memory:Memory,people:List<Person>,repository:BackendRepository,care:Boolean=false,
    onBack:()->Unit={},onEdit:(Memory)->Unit={},onDeleted:()->Unit={},onHome:()->Unit={},
    deleteMemory:suspend (Memory)->Unit={repository.deleteMemory(it)},
) {
    var current by remember(memory){mutableStateOf(memory)};var actions by remember{mutableStateOf(false)}
    var deleting by remember{mutableStateOf(false)};var busy by remember{mutableStateOf(false)}
    var error by remember{mutableStateOf<String?>(null)};var latest by remember{mutableStateOf<Memory?>(null)}
    var photoIndex by remember{mutableStateOf<Int?>(null)}
    val scope=rememberCoroutineScope()
    fun refresh(edit:Boolean=false) {if(busy)return;scope.launch {busy=true;error=null
        try {current=repository.getMemory(current.id);if(edit)onEdit(current)}
        catch(e:CancellationException){throw e}catch(e:Exception){error=e.message}finally{busy=false}}}
    cn.shinian.app.ui.care.CareModeBackdrop(care, Modifier.fillMaxSize()) {
        if (care) CareStoryScreen(current, people, onBack, onActions = { actions = true }) {
            BrowseError(error, true) { refresh() }
            latest?.let { new -> JournalAction("读取最新回忆", true, secondary = true) { current = new; latest = null; error = null } }
        }
        else {
        Box(Modifier.fillMaxSize().navigationBarsPadding()) {
        Column(Modifier.fillMaxSize()) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(if(care)18.dp else 14.dp)) {
                if(care||current.media.isEmpty())Spacer(Modifier.height(56.dp))
                if(current.media.isNotEmpty())Box(Modifier.fillMaxWidth().height(if(care)220.dp else 360.dp)) {
                    MemoryPhoto(current.media.first(),Modifier.fillMaxSize(),radius=0.dp,onClick={photoIndex=0})
                    if(!care)Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0f to Color(0x403C2819),.3f to Color.Transparent,.7f to Color.Transparent,1f to JournalColors.Paper)))
                }
                Column(Modifier.padding(horizontal=22.dp).padding(bottom=40.dp).offset(y=if(!care&&current.media.isNotEmpty())(-60).dp else 0.dp),verticalArrangement=Arrangement.spacedBy(if(care)18.dp else 14.dp)) {
                    val person=people.firstOrNull{it.id==(current.primaryPersonId?:current.personIds.firstOrNull())}
                    Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        person?.let{LocalPortrait(it.id,it,size=30.dp)}
                        Text(memoryIdentity(current,people),style=JournalTypography.body(if(care)18 else 13),color=JournalColors.SecondaryInk)
                    }
                    Text(current.title,style=if(care)JournalTypography.body(28,true)else JournalTypography.story(28),color=JournalColors.Ink)
                    JournalCard(Modifier.fillMaxWidth(),care) {
                        if(care) {
                            Text("时间：${current.dateLabel}\n地点：${current.place.label}\n感受：${current.feeling.label}",style=JournalTypography.body(20),color=JournalColors.SecondaryInk)
                        } else Row(Modifier.fillMaxWidth()) {
                            MemoryFact("时间",current.dateLabel,Modifier.weight(1f))
                            MemoryFact("地点",current.place.label,Modifier.weight(1f))
                            MemoryFact("感受",current.feeling.label,Modifier.weight(1f),JournalColors.RoseInk)
                        }
                    }
                    if(care)SelectionContainer {Text(current.content,style=JournalTypography.body(24).copy(lineHeight=38.sp),color=JournalColors.StoryInk)}
                    else DropCapStory(current.content)
                    if(current.media.size>1)Text("这段回忆的照片",style=JournalTypography.body(if(care)20 else 12,true),color=JournalColors.Muted)
                    current.media.drop(1).forEachIndexed{index,photo->MemoryPhoto(photo,Modifier.fillMaxWidth().height(240.dp),fit=true,onClick={photoIndex=index+1})}
                    if(care)JournalAction("回忆操作",true,secondary=true){actions=true}
                    if(care)JournalAction("回到首页",true,secondary=true,onClick=onHome)
                    BrowseError(error,care){refresh()}
                    latest?.let{new->JournalAction("读取最新回忆",care,secondary=true){current=new;latest=null;error=null}}
                }
            }
            if(busy)LinearProgressIndicator(Modifier.fillMaxWidth(),color=JournalColors.AuthAccent)
        }
            Row(Modifier.align(Alignment.TopCenter).fillMaxWidth().heightIn(min=if(care)64.dp else 48.dp)
                .then(if(care)Modifier.background(JournalColors.Paper)else Modifier).padding(horizontal=12.dp),verticalAlignment=Alignment.CenterVertically) {
                IconButton(onBack,enabled=!busy,modifier=Modifier.testTag("browse.back")){Box(Modifier.size(40.dp).background(JournalColors.Surface.copy(alpha=.85f),androidx.compose.foundation.shape.CircleShape),contentAlignment=Alignment.Center){JournalIcon("back","返回")}}
                Text(if(care)"回忆"else"",style=JournalTypography.body(if(care)23 else 17,true),modifier=Modifier.weight(1f),textAlign=TextAlign.Center)
                IconButton({actions=true},enabled=!busy,modifier=Modifier.testTag("memory.actions")){Box(Modifier.size(40.dp).background(JournalColors.Surface.copy(alpha=.85f),androidx.compose.foundation.shape.CircleShape),contentAlignment=Alignment.Center){JournalIcon("more","回忆操作")}}
            }
        }
        }
    }
    if(actions)JournalBottomSheet("回忆操作",care=care,onCancel={actions=false}) {
        JournalSheetAction("编辑回忆","edit",care=care){actions=false;refresh(true)}
        JournalSheetAction("删除整段回忆","trash",destructive=true,care=care){actions=false;deleting=true}
    }
    if(deleting)AlertDialog(onDismissRequest={deleting=false},title={Text("删除整段回忆？")},
        text={Text("“${current.title}”及其对应的讲述、AI 回复、草稿和照片会一并删除。AI 开场白和同一人物的其他回忆会保留，已导出到外部的 PDF 不受影响。此操作无法撤销。")},
        dismissButton={TextButton({deleting=false}){Text("保留回忆")}},confirmButton={TextButton({deleting=false;scope.launch{busy=true;error=null
            try{deleteMemory(current);onDeleted()}catch(e:CancellationException){throw e}catch(e:Exception){error=e.message;if((e as? AuthException)?.statusCode==409)latest=runCatching{repository.getMemory(current.id)}.getOrNull()}finally{busy=false}}}){Text("确认删除整段",color=JournalColors.Danger)}})
    photoIndex?.let{PhotoViewer(current.media,it){photoIndex=null}}
}

@Composable
private fun MemoryFact(label:String,value:String,modifier:Modifier,ink:Color=JournalColors.Ink) {
    Column(modifier.padding(horizontal=4.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(3.dp)) {
        Text(label,style=JournalTypography.body(12),color=JournalColors.Muted)
        Text(value,style=JournalTypography.body(14),color=ink,textAlign=TextAlign.Center)
    }
}

/** Android text layout wraps around the first character for the same two-line drop cap. */
@Composable
private fun DropCapStory(text:String) {
    AndroidView(factory={context->TextView(context).apply{setTextIsSelectable(true);includeFontPadding=false}},
        modifier=Modifier.fillMaxWidth(),update={view->
            val clean=text.trim();val boundary=if(clean.isEmpty())0 else android.icu.text.BreakIterator.getCharacterInstance().apply{setText(clean)}.following(0)
            val first=clean.substring(0,boundary);val rest=clean.substring(boundary)
            val density=view.resources.displayMetrics.scaledDensity;val bodySize=16*density;val lineHeight=32*density
            view.typeface=ResourcesCompat.getFont(view.context,R.font.noto_serif_sc)
            view.textSize=16f;view.setTextColor(JournalColors.StoryInk.toArgb());view.setLineSpacing(lineHeight-view.paint.fontSpacing,1f)
            val capPaint=Paint(view.paint).apply{textSize=46*density;color=JournalColors.Accent.toArgb()}
            val span=object:LeadingMarginSpan.LeadingMarginSpan2 {
                override fun getLeadingMargin(firstLine:Boolean)=if(firstLine)(capPaint.measureText(first)+8*density).toInt()else 0
                override fun getLeadingMarginLineCount()=2
                override fun drawLeadingMargin(c:Canvas,p:Paint,x:Int,dir:Int,top:Int,baseline:Int,bottom:Int,t:CharSequence,start:Int,end:Int,firstLine:Boolean,layout:android.text.Layout?) {
                    if(start==0){val fm=capPaint.fontMetrics;val y=top+(lineHeight*2-(fm.descent-fm.ascent))/2-fm.ascent;c.drawText(first,x.toFloat(),y,capPaint)}
                }
            }
            view.text=if(rest.isBlank())clean else SpannableString(rest).apply{setSpan(span,0,length,Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)}
            view.contentDescription=clean
        })
}
