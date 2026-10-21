package cn.shinian.app.ui.browse

import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cn.shinian.app.data.*
import cn.shinian.app.ui.media.rememberPhotoPicker
import cn.shinian.app.ui.theme.*
import java.io.File
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

private val editSaver=listSaver<MemoryEdit,String>(
    save={listOf(it.title,it.content,Json.encodeToString(it.time),Json.encodeToString(it.place),Json.encodeToString(it.feeling),Json.encodeToString(it.mediaIds))},
    restore={MemoryEdit(it[0],it[1],Json.decodeFromString(it[2]),Json.decodeFromString(it[3]),Json.decodeFromString(it[4]),Json.decodeFromString(it[5]))},
)

@Composable
fun MemoryEditorScreen(
    memory:Memory,repository:BackendRepository,care:Boolean=false,onBack:()->Unit={},onSaved:(Memory)->Unit={},
) {
    var base by remember(memory.id){mutableStateOf(memory)}
    var edit by rememberSaveable(memory.id,stateSaver=editSaver){mutableStateOf(MemoryEdit(memory))}
    var latest by remember{mutableStateOf<Memory?>(null)}
    var error by remember{mutableStateOf<String?>(null)};var busy by remember{mutableStateOf(false)}
    var discard by remember{mutableStateOf(false)};var resolve by remember{mutableStateOf(false)}
    var pendingIds by rememberSaveable(memory.id){mutableStateOf(listOf<String>())}
    var discardedIds by rememberSaveable(memory.id){mutableStateOf(listOf<String>())}
    val receipts=remember(memory.id){mutableStateMapOf<String,Media>()}
    var timeAnchor by remember{mutableStateOf(memory.time)};var timeInput by remember{mutableStateOf<TimePreviewInput?>(null)}
    val context=LocalContext.current;val scope=rememberCoroutineScope();val focus=LocalFocusManager.current
    val directory=remember(memory.id,repository.session.scopeKey){File(context.filesDir,"MemoryEdits/${repository.session.scopeKey}/${memory.id}")}
    val changed=edit!=MemoryEdit(base)||pendingIds.isNotEmpty()

    suspend fun discardUpload(id:String) {
        try{repository.discardMemoryPhoto(base.id,id)}catch(e:AuthException){if(e.statusCode !in listOf(404,409))throw e}
    }
    fun cancel() {if(busy)return;scope.launch {busy=true;error=null
        try{(pendingIds+discardedIds).distinct().forEach{discardUpload(it)};directory.deleteRecursively();onBack()}
        catch(e:CancellationException){throw e}catch(e:Exception){error="取消尚未完成，新照片仍待清理，请重试。${e.message.orEmpty()}"}finally{busy=false}}}
    fun requestBack(){if(!busy){focus.clearFocus();if(changed)discard=true else cancel()}}
    fun save() {if(busy||!edit.isValid||latest!=null)return;focus.clearFocus();scope.launch {busy=true;error=null
        try {
            for(id in pendingIds)if(receipts[id]==null) {
                val bytes=withContext(Dispatchers.IO){File(directory,"$id.jpg").readBytes()}
                receipts[id]=repository.uploadMemoryPhoto(base.id,bytes,id)
            }
            discardedIds.distinct().forEach{discardUpload(it)};discardedIds=emptyList()
            val result=repository.updateMemory(base,edit.copy(mediaIds=edit.mediaIds+pendingIds.map{receipts[it]?.id?:it}))
            directory.deleteRecursively();pendingIds=emptyList();base=result;edit=MemoryEdit(result);onSaved(result)
        }catch(e:CancellationException){throw e}catch(e:Exception){error=e.message
            if((e as? AuthException)?.statusCode==409)latest=runCatching{repository.getMemory(base.id)}.getOrNull()
        }finally{busy=false}}}
    BackHandler{requestBack()}
    val picker=rememberPhotoPicker(9){uris->
        if(uris.isNotEmpty())scope.launch {busy=true;error=null
            try{for(uri in uris){val id=UUID.randomUUID().toString();withContext(Dispatchers.IO){
                val bytes=context.contentResolver.openInputStream(uri)?.use{it.readBytes()}?:throw IllegalStateException("无法读取照片")
                val jpeg=compressBrowsePhoto(bytes);directory.mkdirs();File(directory,"$id.jpg").writeBytes(jpeg)
            };pendingIds=pendingIds+id}}
            catch(e:CancellationException){throw e}catch(e:Exception){error=e.message}finally{busy=false}}
    }
    JournalBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding()) {
            Row(Modifier.fillMaxWidth().heightIn(min=56.dp).padding(horizontal=12.dp),verticalAlignment=Alignment.CenterVertically) {
                TextButton({requestBack()},enabled=!busy){Text("取消",style=JournalTypography.body(if(care)20 else 16))}
                Text("编辑回忆",style=JournalTypography.body(if(care)23 else 17,true),modifier=Modifier.weight(1f))
                TextButton({save()},enabled=edit.isValid&&!busy&&latest==null,modifier=Modifier.testTag("memory.saveEdits")){Text("保存修改",style=JournalTypography.body(if(care)20 else 16))}
            }
            if(busy)LinearProgressIndicator(Modifier.fillMaxWidth())
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                OutlinedTextField(edit.title,{edit=edit.copy(title=it)},Modifier.fillMaxWidth().testTag("memory.editTitle"),label={Text("标题")},enabled=!busy,textStyle=JournalTypography.body(if(care)22 else 16),shape=RoundedCornerShape(16.dp),supportingText={Text("${edit.title.length} / 200")})
                OutlinedTextField(edit.content,{edit=edit.copy(content=it)},Modifier.fillMaxWidth().heightIn(min=240.dp).testTag("memory.editBody"),label={Text("正文")},enabled=!busy,textStyle=JournalTypography.body(if(care)22 else 16),shape=RoundedCornerShape(16.dp))
                DimensionEditor("时间",edit.time,care,!busy,"memory.edit.time"){edit=edit.copy(time=it)}
                JournalAction("核对标题与正文中的时间",care,secondary=true,enabled=edit.isValid&&!busy&&latest==null,modifier=Modifier.testTag("memory.timePreview")){
                    focus.clearFocus();timeInput=TimePreviewInput(edit.title,edit.content,timeAnchor,edit.time)
                }
                Text("逐项核对后选择要更新的文字，保存修改后才会写入回忆。",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                DimensionEditor("地点",edit.place,care,!busy,"memory.edit.place"){edit=edit.copy(place=it)}
                DimensionEditor("感受",edit.feeling,care,!busy,"memory.edit.feeling"){edit=edit.copy(feeling=it)}
                Text("照片",style=JournalTypography.body(if(care)24 else 18,true),color=JournalColors.Ink)
                val photos=(memory.media+base.media).distinctBy{it.id}.filter{it.id in edit.mediaIds}
                photos.forEach{photo->Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                    MemoryPhoto(photo,Modifier.size(80.dp));Spacer(Modifier.weight(1f))
                    TextButton({edit=edit.copy(mediaIds=edit.mediaIds-photo.id)},enabled=!busy,modifier=Modifier.testTag("memory.removePhoto.${photo.id}")){Text("移除",color=JournalColors.Danger)}
                }}
                pendingIds.forEach{id->Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                    LocalEditPhoto(File(directory,"$id.jpg"));Text("新照片",modifier=Modifier.weight(1f))
                    TextButton({pendingIds=pendingIds-id;discardedIds=discardedIds+id},enabled=!busy){Text("移除",color=JournalColors.Danger)}
                }}
                JournalAction("＋ 添加照片",care,secondary=true,enabled=!busy,modifier=Modifier.testTag("memory.addPhotos")){
                    focus.clearFocus();picker()
                }
                Text("照片和文字会在保存修改后一起更新。原始聊天中的照片会保留，整段删除时一并清除。",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                BrowseError(error,care){scope.launch {busy=true;try{latest=repository.getMemory(base.id)}catch(e:Exception){error="读取最新版本失败；本机修改仍保留。${e.message.orEmpty()}"}finally{busy=false}}}
                latest?.let{cloud->JournalCard(Modifier.fillMaxWidth(),care) {
                    Text("最新版本 · 本机修改仍保留在上方",style=JournalTypography.body(if(care)22 else 16,true),color=JournalColors.AuthAccent)
                    Spacer(Modifier.height(8.dp));Text(cloud.title,style=JournalTypography.story(if(care)24 else 18),color=JournalColors.Ink)
                    Text(cloud.content,style=JournalTypography.body(if(care)20 else 14),color=JournalColors.SecondaryInk)
                    Text("时间：${cloud.dateLabel}\n地点：${cloud.place.label}\n感受：${cloud.feeling.label}\n照片：${cloud.media.size} 张",style=JournalTypography.body(if(care)18 else 13),color=JournalColors.SecondaryInk)
                    Text("核对后保存会使用本机文字、信息和照片选择，替换此最新版本。",style=JournalTypography.body(if(care)18 else 13),color=JournalColors.SecondaryInk)
                    JournalAction("核对后保存本机修改",care,secondary=true,enabled=!busy,modifier=Modifier.testTag("memory.resolveConflict")){resolve=true}
                }}
            }
        }
    }
    if(discard)AlertDialog(onDismissRequest={discard=false},title={Text("放弃本次修改？")},text={Text("已保存的回忆不会改变，这次新选的照片也不会加入回忆。")},
        dismissButton={TextButton({discard=false}){Text("继续编辑")}},confirmButton={TextButton({discard=false;cancel()}){Text("放弃修改",color=JournalColors.Danger)}})
    if(resolve)AlertDialog(onDismissRequest={resolve=false},title={Text("用本机修改更新最新版本？")},text={Text("请确认已核对其他设备的修改。若再次发生版本变化，仍会保留本机内容并提示核对。")},
        dismissButton={TextButton({resolve=false}){Text("继续核对")}},confirmButton={TextButton({resolve=false;latest?.let{base=it};latest=null;save()}){Text("保存我的修改")}})
    timeInput?.let{input->TimeCheckDialog(input,care,{repository.previewMemoryTime(base,input)},{timeInput=null}){preview,selected->
        check(edit.title==input.title&&edit.content==input.content&&edit.time==input.newTime){"编辑内容已变化，请重新核对时间。"}
        val result=preview.applying(selected,input);edit=edit.copy(title=result.first,content=result.second);timeAnchor=edit.time;timeInput=null
    }}
}

@Composable
private fun LocalEditPhoto(file:File) {
    val image by produceState<androidx.compose.ui.graphics.ImageBitmap?>(null,file.path){value=withContext(Dispatchers.IO){runCatching{BitmapFactory.decodeFile(file.path)?.asImageBitmap()}.getOrNull()}}
    image?.let{Image(it,"新照片",Modifier.size(80.dp))}
}

@Composable
private fun DimensionEditor(title:String,value:InformationDimension,care:Boolean,enabled:Boolean,tag:String,onChange:(InformationDimension)->Unit) {
    var expanded by remember{mutableStateOf(false)}
    val statuses=listOf("known" to "确定","approximate" to "大概记得","unknown" to "记不清","withheld" to "暂时不想说","missing" to "待补充")
    JournalCard(Modifier.fillMaxWidth(),care) {
        Text(title,style=JournalTypography.body(if(care)24 else 16,true),color=JournalColors.Ink)
        Box {
            TextButton({expanded=true},enabled=enabled,modifier=Modifier.heightIn(min=48.dp).testTag("$tag.status")){Text("记录方式：${statuses.firstOrNull{it.first==value.status}?.second?:"待补充"}",style=JournalTypography.body(if(care)20 else 14))}
            DropdownMenu(expanded,{expanded=false}) {statuses.forEach{(status,label)->DropdownMenuItem(text={Text(label)},onClick={
                expanded=false
                val next=when(status){"missing"->null;"unknown"->"记不清了";"withheld"->"暂时不想说";else->value.value.orEmpty()}
                onChange(value.copy(status=status,value=next,sourceMessageIds=emptyList(),userEdited=true))
            })}}
        }
        if(value.status!="missing")OutlinedTextField(value.value.orEmpty(),{onChange(value.copy(value=it,sourceMessageIds=emptyList(),userEdited=true))},Modifier.fillMaxWidth().testTag(tag),
            enabled=enabled,label={Text(if(title=="时间")"例如：2008年夏天，或 2008-06-01"else"写下你的说明")},textStyle=JournalTypography.body(if(care)22 else 16))
    }
}

@Composable
private fun TimeCheckDialog(input:TimePreviewInput,care:Boolean,load:suspend()->TimePreview,onClose:()->Unit,onApply:(TimePreview,Set<String>)->Unit) {
    var preview by remember{mutableStateOf<TimePreview?>(null)};var busy by remember{mutableStateOf(true)}
    var error by remember{mutableStateOf<String?>(null)};var retry by remember{mutableIntStateOf(0)}
    var selected by remember{mutableStateOf(setOf<String>())}
    LaunchedEffect(retry){busy=true;error=null;preview=null;selected=emptySet()
        try{preview=load()}catch(e:CancellationException){throw e}catch(e:Exception){error=e.message}finally{busy=false}}
    androidx.compose.ui.window.Dialog(onClose,androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth=false)) {
        JournalBackdrop(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().systemBarsPadding()) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    TextButton(onClose){Text("返回编辑")};Text("核对时间文字",style=JournalTypography.body(if(care)22 else 17,true),modifier=Modifier.weight(1f))
                    TextButton({preview?.let{try{onApply(it,selected)}catch(e:Exception){error=e.message}}},enabled=!busy&&selected.isNotEmpty(),modifier=Modifier.testTag("time.apply")){Text("应用所选")}
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    Text("原时间：${input.oldTime.label}\n修改为：${input.newTime.label}",style=JournalTypography.body(if(care)22 else 16),color=JournalColors.Ink)
                    if(busy)CircularProgressIndicator()
                    BrowseError(error,care){retry++}
                    preview?.let{result->
                        Text(result.message,style=JournalTypography.body(if(care)20 else 14),color=JournalColors.SecondaryInk)
                        listOf("title" to "标题","summary" to "正文").forEach{(field,label)->
                            Text(label,style=JournalTypography.body(if(care)24 else 18,true),color=JournalColors.Ink)
                            val suggestions=result.suggestions.filter{it.field==field}
                            if(suggestions.isEmpty())Text("未找到对应时间，保留原文。",style=JournalTypography.body(if(care)20 else 14))
                            suggestions.forEach{item->JournalCard(Modifier.fillMaxWidth(),care) {
                                Text(item.context,style=JournalTypography.body(if(care)20 else 15),color=JournalColors.Ink)
                                if(item.after!=null)Row(verticalAlignment=Alignment.CenterVertically) {
                                    Checkbox(item.id in selected,{checked->selected=if(checked)selected+item.id else selected-item.id},Modifier.testTag("time.suggestion.${item.id}"))
                                    Text("原文：${item.before}\n改为：${item.after}",style=JournalTypography.body(if(care)20 else 15),color=JournalColors.SecondaryInk)
                                }
                                Text(item.reason,style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                            }}
                        }
                        Text("这里只更新编辑框中的文字，点击保存后才会写入回忆。未选中的内容请继续手动核对。",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk)
                    }
                }
            }
        }
    }
}
