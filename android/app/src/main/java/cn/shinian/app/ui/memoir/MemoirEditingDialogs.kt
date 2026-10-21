package cn.shinian.app.ui.memoir

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import cn.shinian.app.data.*
import cn.shinian.app.ui.theme.*
import java.io.File
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Every displayed cover uses the same renderer and crop geometry as the PDF. */
@Composable
internal fun rememberBookCover(
    model:MemoirController,settings:MemoirSettings,personName:String,revision:String?,onError:(String)->Unit,
):State<Bitmap?> {
    val context=LocalContext.current
    val report by rememberUpdatedState(onError)
    return produceState<Bitmap?>(null,model,settings,personName,revision) {
        value=null
        try {
            val files=linkedMapOf<String,File>()
            for(photo in settings.coverPhotos.take(coverLimit(settings))) {
                files[photo.id]=model.image(photo.id)
            }
            value=withContext(Dispatchers.Default){MemoirPdf.coverBitmap(context,settings,personName,files)}
        } catch(e:CancellationException){throw e}
        catch(e:Exception){value=null;report(e.message?:"封面照片暂时无法读取，请重试或更换。")}
    }
}

@Composable
internal fun MemoirCropDialog(
    model:MemoirController,person:Person,settings:MemoirSettings,revision:String?,selectedId:String,care:Boolean,
    onSelect:(String)->Unit,onClose:()->Unit,onError:(String)->Unit,
) {
    val latest by rememberUpdatedState(settings)
    val selected by rememberUpdatedState(selectedId)
    val density=LocalDensity.current.density
    val cover by rememberBookCover(model,settings,person.name,revision,onError)
    val active=settings.coverPhotos.take(coverLimit(settings))
    val photo=active.firstOrNull{it.id==selectedId}?:active.firstOrNull()
    fun change(transform:(MemoirCoverPhoto)->MemoirCoverPhoto) {
        val current=latest
        val id=current.coverPhotos.firstOrNull{it.id==selected}?.id?:current.coverPhotos.firstOrNull()?.id?:return
        model.update(current.copy(coverPhotos=current.coverPhotos.map{if(it.id==id)transform(it)else it}))
    }
    Dialog(onClose,DialogProperties(usePlatformDefaultWidth=false,decorFitsSystemWindows=false)) {
        cn.shinian.app.ui.theme.ShinianImmersiveWindow()
        Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.displayCutout.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal)).systemBarsPadding().background(JournalColors.Paper)) {
            Row(Modifier.fillMaxWidth().heightIn(min=56.dp).padding(horizontal=16.dp),verticalAlignment=Alignment.CenterVertically) {
                Text("调整照片取景",style=JournalTypography.body(if(care)24 else 18,true),modifier=Modifier.weight(1f))
                TextButton(onClose,modifier=Modifier.testTag("memoir-crop-done")){Text("完成")}
            }
            BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
                val previewWidth=minOf(maxWidth-48.dp,maxHeight*.42f*148f/210f).coerceAtLeast(120.dp)
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    val gesture=Modifier.pointerInput(selectedId){detectTransformGestures{_,pan,zoom,_->
                        change{it.copy(x=(it.x+pan.x/(120*density)).coerceIn(-1.0,1.0),y=(it.y+pan.y/(160*density)).coerceIn(-1.0,1.0),zoom=(it.zoom*zoom).coerceIn(1.0,4.0))}
                    }}
                    if(cover!=null)Image(cover!!.asImageBitmap(),"完整封面实时取景",Modifier.width(previewWidth).aspectRatio(148f/210f).then(gesture).testTag("memoir-crop-preview"))
                    else Box(Modifier.width(previewWidth).aspectRatio(148f/210f).background(JournalColors.PaperSecondary),contentAlignment=Alignment.Center){Text("照片暂时无法读取，请更换或重试。")}
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                        active.forEachIndexed{index,item->
                            Box(Modifier.size(58.dp).border(if(photo?.id==item.id)2.dp else 1.dp,if(photo?.id==item.id)JournalColors.Accent else JournalColors.Line)
                                .clickable{onSelect(item.id)}.semantics{contentDescription="调整第 ${index+1} 张封面照片"},contentAlignment=Alignment.Center) {
                                BookPhoto(model,item.id,Modifier.fillMaxSize())
                            }
                        }
                    }
                    if(photo!=null) {
                        CropSlider("缩放",photo.zoom.toFloat(),1f..4f,care,"memoir.crop.zoom"){value->change{it.copy(zoom=value.toDouble())}}
                        CropSlider("左右位置",photo.x.toFloat(),-1f..1f,care,"memoir.crop.x"){value->change{it.copy(x=value.toDouble())}}
                        CropSlider("上下位置",photo.y.toFloat(),-1f..1f,care,"memoir.crop.y"){value->change{it.copy(y=value.toDouble())}}
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            TextButton({change{it.copy(x=0.0,y=0.0,zoom=1.0)}},modifier=Modifier.testTag("memoir.crop.reset")){Text("重置取景")}
                            val index=settings.coverPhotos.indexOfFirst{it.id==photo.id}
                            if(index>0)TextButton({
                                val moved=settings.coverPhotos.toMutableList();val previous=moved[index-1];moved[index-1]=moved[index];moved[index]=previous
                                model.update(settings.copy(coverPhotos=moved))
                            },modifier=Modifier.testTag("memoir.crop.movePrevious")){Text("前移")}
                            TextButton({
                                val remaining=settings.coverPhotos.filterNot{it.id==photo.id};model.update(settings.copy(coverPhotos=remaining))
                                if(remaining.isEmpty())onClose()else onSelect(remaining.first().id)
                            }){Text("移除",color=JournalColors.Danger)}
                        }
                    }
                    Text("可在上方封面中拖动或双指缩放，也可使用滑块。故事中的照片不会被裁剪。",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                }
            }
        }
    }
}

@Composable
private fun CropSlider(label:String,value:Float,range:ClosedFloatingPointRange<Float>,care:Boolean,tag:String,onValue:(Float)->Unit) {
    Column(Modifier.fillMaxWidth()) {
        Text("$label  ${String.format(Locale.ROOT,"%.2f",value)}",style=JournalTypography.body(if(care)20 else 13),color=JournalColors.SecondaryInk)
        Slider(value,onValue,valueRange=range,modifier=Modifier.testTag(tag).semantics{contentDescription=label})
    }
}

@Composable
internal fun MemoirConflictDialog(
    model:MemoirController,person:Person,local:MemoirSettings,localStories:List<Memory>,cloud:MemoirSnapshot,care:Boolean,
    onClose:()->Unit,onCloud:()->Unit,onLocal:()->Unit,onError:(String)->Unit,
) {
    Dialog(onClose,DialogProperties(usePlatformDefaultWidth=false,decorFitsSystemWindows=false)) {
        cn.shinian.app.ui.theme.ShinianImmersiveWindow()
        Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.displayCutout.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal)).systemBarsPadding().background(JournalColors.Paper)) {
            Row(Modifier.fillMaxWidth().heightIn(min=56.dp).padding(horizontal=16.dp),verticalAlignment=Alignment.CenterVertically) {
                Text("核对制作设置",style=JournalTypography.body(if(care)24 else 18,true),modifier=Modifier.weight(1f))
                TextButton(onClose){Text("完成")}
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.spacedBy(24.dp)) {
                ComparisonVersion("本机设置",model,person,local,localStories,null,care,onError)
                HorizontalDivider(color=JournalColors.Line)
                ComparisonVersion("云端设置",model,person,cloud.settings,cloud.stories,cloud.contentRevision,care,onError)
            }
            Column(Modifier.padding(horizontal=20.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                Button(onCloud,Modifier.fillMaxWidth().heightIn(min=48.dp)){Text("使用云端版本")}
                OutlinedButton(onLocal,Modifier.fillMaxWidth().heightIn(min=48.dp)){Text("用本机设置覆盖")}
            }
        }
    }
}

@Composable
private fun ComparisonVersion(title:String,model:MemoirController,person:Person,settings:MemoirSettings,stories:List<Memory>,revision:String?,care:Boolean,onError:(String)->Unit) {
    val cover by rememberBookCover(model,settings,person.name,revision,onError)
    Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text(title,style=JournalTypography.body(if(care)26 else 20,true),color=JournalColors.Ink)
        cover?.let{Image(it.asImageBitmap(),"$title 封面",Modifier.fillMaxWidth().height(280.dp))}
        val style=when(settings.coverTemplate){"photo"->"单照片";"collage"->"照片拼贴";else->"素雅文字"}
        Text("书名：${settings.title}\n副标题：${settings.subtitle.ifBlank{"未填写"}}\n封面：$style\n正文字号：${settings.textSize} pt\n排序：${if(settings.ordering=="manual")"手动排序"else"故事时间"}",style=JournalTypography.body(if(care)20 else 14),color=JournalColors.Ink)
        settings.ordered(stories).forEachIndexed{index,story->
            val numbers=settings.selectedPhotos(story).map{photo->story.media.indexOfFirst{it.id==photo.id}+1}
            Text("${index+1}. ${story.title}\n照片顺序：${if(numbers.isEmpty())"未选照片"else numbers.joinToString("、")}",style=JournalTypography.body(if(care)20 else 13),color=JournalColors.SecondaryInk)
        }
        settings.coverPhotos.forEachIndexed{index,photo->
            Text("封面第 ${index+1} 张：缩放 ${String.format(Locale.ROOT,"%.2f",photo.zoom)}，左右 ${String.format(Locale.ROOT,"%.2f",photo.x)}，上下 ${String.format(Locale.ROOT,"%.2f",photo.y)}",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
        }
    }
}
