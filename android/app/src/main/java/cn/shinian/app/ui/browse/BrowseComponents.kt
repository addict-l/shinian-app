package cn.shinian.app.ui.browse

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.DialogWindowProvider
import androidx.exifinterface.media.ExifInterface
import cn.shinian.app.R
import cn.shinian.app.data.*
import cn.shinian.app.ui.theme.*
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.time.LocalDate
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

val LocalBrowseRepository = staticCompositionLocalOf<BackendRepository?> { null }
internal val LocalBrowseStorageScope = staticCompositionLocalOf { "signed-out" }

@Composable
fun ProvideBrowseEnvironment(repository: BackendRepository, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalBrowseRepository provides repository,
        LocalBrowseStorageScope provides repository.session.scopeKey, content = content)
}

@Composable
fun JournalIcon(name: String, description: String? = null, modifier: Modifier = Modifier, tint: Color = JournalColors.SecondaryInk) {
    val context = LocalContext.current
    val alias = when(name) { "gear" -> "settings"; "x" -> "close"; "chev" -> "next"; else -> name }
    val id = remember(name) {
        listOf("ic_design_$name", "ic_journal_$name", "ic_journal_$alias", "ic_design_$alias")
            .map { context.resources.getIdentifier(it, "drawable", context.packageName) }.firstOrNull { it != 0 }
            ?: R.drawable.ic_journal_info
    }
    Icon(painterResource(id), description, modifier.size(22.dp), tint)
}

@Composable
internal fun PageTitle(title: String, subtitle: String? = null, care: Boolean = false,size:Int=30) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
        Text(title, style = if(care) JournalTypography.body(28, true) else JournalTypography.story(size),
            color = JournalColors.Ink, modifier = Modifier.semantics { heading() })
        subtitle?.let { Text(it, style = JournalTypography.body(if(care) 20 else 14), color = JournalColors.SecondaryInk) }
    }
}

@Composable
internal fun BrowseBar(title: String = "", care: Boolean = false, onBack: () -> Unit,
    trailing: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth().heightIn(min = if(care) 64.dp else 48.dp).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack, modifier = Modifier.size(48.dp).testTag("browse.back")) {
            Box(Modifier.size(40.dp).shadow(if(care)0.dp else 3.dp,CircleShape).background(JournalColors.Surface,CircleShape),contentAlignment=Alignment.Center) {
                Icon(painterResource(R.drawable.ic_journal_back), "返回", tint = JournalColors.Ink)
            }
        }
        Text(title, style = JournalTypography.body(if(care) 23 else 16, true), color = JournalColors.Ink,
            modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
        if(title.isNotEmpty()) Spacer(Modifier.width(48.dp))
        trailing()
    }
}

@Composable
internal fun JournalCard(modifier: Modifier = Modifier, care: Boolean = false,contentPadding:PaddingValues=PaddingValues(if(care)18.dp else 16.dp), content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(if(care) 18.dp else 22.dp)
    Column(modifier.shadow(if(care) 0.dp else 4.dp, shape, ambientColor = JournalColors.Shadow.copy(alpha=.12f),
        spotColor = JournalColors.Shadow.copy(alpha=.12f)).background(JournalColors.Surface, shape)
        .border(1.dp, if(care) Color(0xFFDFD3C3) else JournalColors.CardBorder, shape)
        .clip(shape).padding(contentPadding), content = content)
}

@Composable
internal fun JournalInput(label:String,value:String,onChange:(String)->Unit,placeholder:String="",care:Boolean=false,enabled:Boolean=true,tag:String="",next:Boolean=false) {
    val focus=LocalFocusManager.current
    Column(Modifier.fillMaxWidth().background(JournalColors.Surface,RoundedCornerShape(18.dp))
        .border(1.dp,JournalColors.Line,RoundedCornerShape(18.dp)).padding(horizontal=16.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
        Text(label,style=JournalTypography.body(if(care)18 else 12),color=JournalColors.Muted)
        BasicTextField(value,onChange,Modifier.fillMaxWidth().heightIn(min=24.dp).testTag(tag).semantics{contentDescription=label},
            enabled=enabled,singleLine=true,textStyle=JournalTypography.body(if(care)22 else 16).copy(color=JournalColors.Ink),
            cursorBrush=SolidColor(JournalColors.Accent),keyboardOptions=KeyboardOptions(imeAction=if(next)ImeAction.Next else ImeAction.Done),
            keyboardActions=KeyboardActions(onNext={focus.moveFocus(FocusDirection.Down)},onDone={focus.clearFocus()}),
            decorationBox={inner->Box(contentAlignment=Alignment.CenterStart){if(value.isEmpty())Text(placeholder,style=JournalTypography.body(if(care)22 else 16),color=JournalColors.Placeholder);inner()}})
    }
}

@Composable
internal fun JournalAction(title: String, care: Boolean = false, secondary: Boolean = false, enabled: Boolean = true,
    loading: Boolean = false, modifier: Modifier = Modifier, icon:String?=null,onClick: () -> Unit) {
    Button(onClick, modifier.fillMaxWidth().heightIn(min = if(care) 64.dp else 54.dp),
        enabled = enabled && !loading, shape = if(care) RoundedCornerShape(16.dp) else CircleShape,
        colors = ButtonDefaults.buttonColors(containerColor = if(secondary) JournalColors.Surface else if(care) Color(0xFF9E4C2D) else JournalColors.Accent,
            contentColor = if(secondary) JournalColors.AccentDeep else Color.White,
            disabledContainerColor=if(secondary)JournalColors.Surface else if(care)Color(0xFF9E4C2D).copy(alpha=.5f)else JournalColors.Accent.copy(alpha=.5f),
            disabledContentColor=if(secondary)JournalColors.Muted else Color.White),
        border = if(secondary) androidx.compose.foundation.BorderStroke(1.5.dp, JournalColors.Soft) else null,
        contentPadding = PaddingValues(horizontal=18.dp, vertical=14.dp)) {
        if(loading) { CircularProgressIndicator(Modifier.size(18.dp), strokeWidth=2.dp); Spacer(Modifier.width(10.dp)) }
        else if(icon!=null){JournalIcon(icon,tint=if(secondary)JournalColors.AccentDeep else Color.White);Spacer(Modifier.width(8.dp))}
        Text(title, style = JournalTypography.body(if(care) 22 else 16, true), textAlign = TextAlign.Center)
    }
}

@Composable
internal fun BrowseError(error: String?, care: Boolean = false, onRetry: () -> Unit) {
    if(error != null) JournalCard(Modifier.fillMaxWidth(), care) {
        Text(error, style = JournalTypography.body(if(care) 20 else 13), color=JournalColors.Danger,
            modifier=Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        TextButton(onRetry, Modifier.heightIn(min=48.dp)) { Text("再试一次", style=JournalTypography.body(if(care) 20 else 14)) }
    }
}

@Composable
internal fun SearchBox(value: String, onChange: (String)->Unit, prompt: String, care: Boolean = false, tag: String="browse.search") {
    OutlinedTextField(value,onChange,Modifier.fillMaxWidth().testTag(tag), singleLine=true,
        placeholder = { Text(prompt,style=JournalTypography.body(if(care) 20 else 14)) },
        leadingIcon = { JournalIcon("search") }, shape=RoundedCornerShape(16.dp),
        textStyle=JournalTypography.body(if(care) 22 else 16),
        colors=OutlinedTextFieldDefaults.colors(unfocusedContainerColor=JournalColors.Surface,
            focusedContainerColor=JournalColors.Surface,unfocusedBorderColor=JournalColors.Line))
}

@Composable
internal fun LocalPortrait(id: String, person: Person? = null, scope: String = LocalBrowseStorageScope.current,
    size: Dp = 52.dp, refresh: Int = 0, modifier: Modifier = Modifier) {
    val context=LocalContext.current
    var bitmap by remember(id,scope,refresh) { mutableStateOf<ImageBitmap?>(null) }
    LaunchedEffect(id,scope,refresh) { bitmap=withContext(Dispatchers.IO) {
        runCatching { portraitFile(context.filesDir,scope,id).takeIf{it.exists()}?.let { BitmapFactory.decodeFile(it.path)?.asImageBitmap() } }.getOrNull()
    } }
    val colors=listOf(JournalColors.Sage,JournalColors.AccentGlow,JournalColors.Butter,JournalColors.Rose)
    val index=runCatching{UUID.fromString(id).let{uuid->val first=((uuid.mostSignificantBits ushr 56)and 255).toInt();val last=(uuid.leastSignificantBits and 255).toInt();if(last==4)0 else(first xor last)%colors.size}}.getOrDefault(0)
    val color=if(person==null)JournalColors.Soft else colors[index]
    val border=if(size>=80.dp)4.dp else if(size<=26.dp)1.5.dp else if(size<=34.dp)2.dp else 2.5.dp
    Box(modifier.size(size).shadow(5.dp,CircleShape,ambientColor=JournalColors.Shadow.copy(alpha=.15f),spotColor=JournalColors.Shadow.copy(alpha=.15f))
        .clip(CircleShape).background(color).border(border,Color.White,CircleShape),contentAlignment=Alignment.Center) {
        if(bitmap!=null) Image(bitmap!!,null,Modifier.fillMaxSize(),contentScale=ContentScale.Crop)
        else if(person==null)JournalIcon("person",modifier=Modifier.size(size*.46f),tint=JournalColors.Accent)
        else {
            val initial=when(person.relationship){"爸爸"->"父";"妈妈"->"母";else->person.relationship.ifBlank{person.name}.take(1)}
            Text(initial,style=JournalTypography.story((size.value*.36).toInt()),color=Color.White)
        }
    }
}

internal fun portraitFile(root: File, scope:String,id:String)=File(root,"Accounts/${scope.replace(Regex("[^A-Za-z0-9_-]"),"_")}/Portraits/${id.replace(Regex("[^A-Za-z0-9_-]"),"_")}.jpg")
internal suspend fun savePortrait(context: android.content.Context, scope: String, id:String,uri:Uri) = withContext(Dispatchers.IO) {
    val bytes=context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: error("照片读取失败，请重新选择。")
    val compressed=compressBrowsePhoto(bytes,512)
    val target=portraitFile(context.filesDir,scope,id);target.parentFile!!.mkdirs()
    val pending=File(target.path+".tmp");pending.writeBytes(compressed)
    if(!pending.renameTo(target)) { pending.delete(); error("头像未保存，请重试。") }
}

internal fun compressBrowsePhoto(data:ByteArray,maxDimension:Int=2560):ByteArray {
    val bounds=BitmapFactory.Options().apply{inJustDecodeBounds=true};BitmapFactory.decodeByteArray(data,0,data.size,bounds)
    require(bounds.outWidth>0&&bounds.outHeight>0){"照片无法读取，请重新选择。"}
    var sample=1;while(maxOf(bounds.outWidth,bounds.outHeight)/sample>maxDimension*2)sample*=2
    var bitmap=BitmapFactory.decodeByteArray(data,0,data.size,BitmapFactory.Options().apply{inSampleSize=sample}) ?: error("照片无法读取。")
    val orientation=runCatching{ExifInterface(ByteArrayInputStream(data)).getAttributeInt(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_NORMAL)}.getOrDefault(1)
    val transform=Matrix().apply { when(orientation) {
        2->setScale(-1f,1f);3->setRotate(180f);4->setScale(1f,-1f);5->{setRotate(90f);postScale(-1f,1f)}
        6->setRotate(90f);7->{setRotate(-90f);postScale(-1f,1f)};8->setRotate(-90f)
    } }
    if(!transform.isIdentity)bitmap=Bitmap.createBitmap(bitmap,0,0,bitmap.width,bitmap.height,transform,true)
    if(maxOf(bitmap.width,bitmap.height)>maxDimension){val factor=maxDimension.toFloat()/maxOf(bitmap.width,bitmap.height)
        bitmap=Bitmap.createScaledBitmap(bitmap,(bitmap.width*factor).toInt().coerceAtLeast(1),(bitmap.height*factor).toInt().coerceAtLeast(1),true)}
    for(quality in listOf(85,65,45)){val out=ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.JPEG,quality,out)
        if(out.size()<=8*1024*1024)return out.toByteArray()}
    error("照片压缩后仍超过 8 MB，请选择较小的图片。")
}

@Composable
fun MemoryPhoto(media: Media, modifier: Modifier=Modifier, fit:Boolean=false,radius:Dp=14.dp,onClick:(()->Unit)?=null) {
    val repo=LocalBrowseRepository.current
    var bitmap by remember(media.id,repo?.session?.scopeKey) { mutableStateOf<ImageBitmap?>(null) }
    var error by remember(media.id) { mutableStateOf(false) }; var retry by remember(media.id){mutableIntStateOf(0)}
    LaunchedEffect(media.id,repo,retry) {
        if(repo==null)return@LaunchedEffect
        error=false
        try {bitmap=withContext(Dispatchers.IO){
                val bytes=repo.loadMedia(media)
                val bounds=BitmapFactory.Options().apply{inJustDecodeBounds=true};BitmapFactory.decodeByteArray(bytes,0,bytes.size,bounds)
                var sample=1;val limit=if(fit)2000 else 1000
                while(maxOf(bounds.outWidth,bounds.outHeight)/sample>limit)sample*=2
                BitmapFactory.decodeByteArray(bytes,0,bytes.size,BitmapFactory.Options().apply{inSampleSize=sample})?.asImageBitmap()
            }
            if(bitmap==null)error=true
        } catch(e:CancellationException){throw e} catch(e:Exception){error=true}
    }
    Box(modifier.clip(RoundedCornerShape(radius)).background(JournalColors.PaperSecondary)
        .then(if(onClick!=null)Modifier.clickable(onClick=onClick) else Modifier),contentAlignment=Alignment.Center) {
        if(bitmap!=null)Image(bitmap!!,"回忆照片",Modifier.fillMaxSize(),contentScale=if(fit)ContentScale.Fit else ContentScale.Crop)
        else if(error)TextButton({retry++}){Text("重试照片",color=JournalColors.AuthAccent)}
        else CircularProgressIndicator(Modifier.size(20.dp),strokeWidth=2.dp,color=JournalColors.Muted)
    }
}

@Composable
internal fun PhotoViewer(media:List<Media>,initial:Int,onClose:()->Unit) {
    var index by remember{mutableIntStateOf(initial.coerceIn(0,media.lastIndex.coerceAtLeast(0)))}
    var zoom by remember(index){mutableFloatStateOf(1f)}
    Dialog(onClose,DialogProperties(usePlatformDefaultWidth=false)) {
        Column(Modifier.fillMaxSize().background(Color.Black).systemBarsPadding()) {
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                Text("${index+1} / ${media.size}",color=Color.White,modifier=Modifier.weight(1f).padding(20.dp))
                TextButton(onClose){Text("关闭",color=Color.White)}
            }
            Box(Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(0.dp))) {
                media.getOrNull(index)?.let {MemoryPhoto(it,Modifier.fillMaxSize().pointerInput(index){
                    detectTransformGestures { _,_,scale,_->zoom=(zoom*scale).coerceIn(1f,4f) }
                }.graphicsLayer{scaleX=zoom;scaleY=zoom},fit=true,radius=0.dp)}
            }
            Row(Modifier.fillMaxWidth().padding(12.dp),horizontalArrangement=Arrangement.SpaceBetween) {
                TextButton({index--},enabled=index>0){Text("上一张",color=Color.White)}
                TextButton({zoom=1f}){Text("还原大小",color=Color.White)}
                TextButton({index++},enabled=index<media.lastIndex){Text("下一张",color=Color.White)}
            }
        }
    }
}

internal fun storyYear(memory:Memory):Int? {
    if(memory.time.status in listOf("unknown","withheld"))return null
    val value=memory.memoryDate?:memory.time.value?:return null
    return if(value.matches(Regex("^[1-9][0-9]{3}(-[0-9]{2}(-[0-9]{2})?)?$"))||
        value.matches(Regex("^[1-9][0-9]{3}年(春天|夏天|秋天|冬天|春|夏|秋|冬|初|末)?$")))value.take(4).toIntOrNull() else null
}
internal fun memoryIdentity(memory:Memory,people:List<Person>):String {
    val person=people.firstOrNull{it.id==(memory.primaryPersonId?:memory.personIds.firstOrNull())}
    return person?.let{if(it.relationship.isBlank())"关于${it.name}" else "关于${it.relationship} · ${it.name}"}?:"关于${memory.personName}"
}
internal fun String.displayDay():String=runCatching{LocalDate.parse(take(10)).let{"${it.year} 年 ${it.monthValue} 月 ${it.dayOfMonth} 日"}}.getOrDefault(this)

@Composable
internal fun JournalBottomSheet(title:String,message:String?=null,care:Boolean=false,onCancel:()->Unit,content:@Composable ColumnScope.()->Unit) {
    Dialog(onCancel,DialogProperties(usePlatformDefaultWidth=false,decorFitsSystemWindows=false)) {
        val dialogWindow=(LocalView.current.parent as? DialogWindowProvider)?.window
        SideEffect {dialogWindow?.setDimAmount(0f)}
        Box(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxSize().background(JournalColors.Ink.copy(alpha=.28f)).clickable(onClick=onCancel).clearAndSetSemantics{})
            Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().padding(horizontal=12.dp,vertical=4.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                Column(Modifier.fillMaxWidth().background(JournalColors.Surface,RoundedCornerShape(26.dp)).padding(bottom=8.dp)) {
                    Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=16.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(6.dp)) {
                        Text(title,style=JournalTypography.body(if(care)22 else if(message==null)12 else 15,message!=null),color=if(message==null)JournalColors.Muted else JournalColors.Ink,textAlign=TextAlign.Center)
                        message?.let{Text(it,style=JournalTypography.body(if(care)19 else 12),color=JournalColors.SecondaryInk,textAlign=TextAlign.Center)}
                    }
                    content()
                }
                TextButton(onCancel,modifier=Modifier.fillMaxWidth().heightIn(min=if(care)64.dp else 54.dp).background(JournalColors.Surface,RoundedCornerShape(22.dp))) {
                    Text("取消",style=JournalTypography.body(if(care)22 else 16,true),color=JournalColors.AccentDeep)
                }
            }
        }
    }
}

@Composable
internal fun JournalSheetAction(title:String,icon:String,destructive:Boolean=false,care:Boolean=false,onClick:()->Unit) {
    HorizontalDivider(color=JournalColors.Line)
    Row(Modifier.fillMaxWidth().heightIn(min=if(care)64.dp else 52.dp).clickable(onClick=onClick).padding(horizontal=22.dp,vertical=12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
        JournalIcon(icon,tint=if(destructive)JournalColors.Danger else JournalColors.Accent)
        Text(title,style=JournalTypography.body(if(care)22 else 16),color=if(destructive)JournalColors.Danger else JournalColors.Ink)
    }
}
