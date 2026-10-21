package cn.shinian.app.ui.memoir

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.*
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import cn.shinian.app.ui.theme.*
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionGoTo
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDNamedDestination
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDPageDestination
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

internal data class PdfBookLink(val left:Float,val bottom:Float,val right:Float,val top:Float,val target:Int)
internal data class PdfBookPage(val width:Float,val height:Float,val links:List<PdfBookLink>)

/** The exported PDF's real link rectangles and destinations also drive the in-app reader. */
internal fun readBookPages(file:File):List<PdfBookPage> = PDDocument.load(file).use{document->
    document.pages.map{page->
        val links=page.annotations.filterIsInstance<PDAnnotationLink>().mapNotNull{link->
            val destination=link.destination?:(link.action as? PDActionGoTo)?.destination
            val pageDestination=when(destination){
                is PDPageDestination->destination
                is PDNamedDestination->document.documentCatalog.findNamedDestinationPage(destination)
                else->null
            }
            val target=pageDestination?.retrievePageNumber()?:-1
            val rect=link.rectangle
            if(target !in 0 until document.numberOfPages||rect==null)null
            else PdfBookLink(rect.lowerLeftX,rect.lowerLeftY,rect.upperRightX,rect.upperRightY,target)
        }
        PdfBookPage(page.mediaBox.width,page.mediaBox.height,links)
    }
}

/** PDF coordinates start at the bottom left; Compose pointer positions start at the top left. */
internal fun PdfBookPage.linkAt(point:Offset,size:IntSize,scale:Float,pan:Offset):Int? {
    if(size.width<=0||size.height<=0||scale<=0)return null
    val center=Offset(size.width/2f,size.height/2f)
    val original=(point-center-pan)/scale+center
    if(original.x !in 0f..size.width.toFloat()||original.y !in 0f..size.height.toFloat())return null
    val x=original.x/size.width*width;val y=height-original.y/size.height*height
    return links.firstOrNull{x in it.left..it.right&&y in it.bottom..it.top}?.target
}

@Composable
internal fun MemoirPdfPreview(preview:BookPreview,modifier:Modifier=Modifier,care:Boolean=false,onError:(String)->Unit={}) {
    val list=rememberLazyListState();val scope=rememberCoroutineScope()
    var metadata by remember(preview.file.path){mutableStateOf<List<PdfBookPage>>(emptyList())}
    var reset by remember(preview.file.path){mutableIntStateOf(0)}
    val readingPage by remember(list,preview.pages){derivedStateOf{
        val layout=list.layoutInfo
        val page=layout.visibleItemsInfo.maxByOrNull{item->
            (minOf(item.offset+item.size,layout.viewportEndOffset)-maxOf(item.offset,layout.viewportStartOffset)).coerceAtLeast(0)
        }?.index?:0
        (page+1).coerceIn(1,maxOf(1,preview.pages))
    }}
    val report by rememberUpdatedState(onError)
    LaunchedEffect(preview.file.path){
        try{metadata=withContext(Dispatchers.IO){readBookPages(preview.file)}}
        catch(e:CancellationException){throw e}catch(e:Exception){report(e.message?:"目录暂时无法读取，请重新生成预览。")}
    }
    fun goTo(page:Int){if(page in 0 until preview.pages)scope.launch{list.animateScrollToItem(page)}}
    Column(modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),verticalAlignment=Alignment.CenterVertically) {
            Text("第 $readingPage / ${preview.pages} 页",style=JournalTypography.body(if(care)18 else 12),color=JournalColors.SecondaryInk,
                modifier=Modifier.weight(1f).testTag("memoir-page-count"))
            TextButton({reset++}){Text("还原大小",style=JournalTypography.body(if(care)18 else 12))}
        }
        Text("上下翻阅 · 双指缩放 · 双击复位 · 点击目录跳转",style=JournalTypography.body(if(care)17 else 12),color=JournalColors.SecondaryInk,
            modifier=Modifier.padding(horizontal=20.dp,vertical=6.dp))
        LazyColumn(Modifier.fillMaxSize().testTag("memoir-pdf"),state=list,verticalArrangement=Arrangement.spacedBy(14.dp),contentPadding=PaddingValues(16.dp)) {
            items(preview.pages,key={it}){index->
                InteractiveBookPage(preview.file,index,metadata.getOrNull(index),reset,onError=report,onLink=::goTo)
            }
        }
    }
}

@Composable
private fun InteractiveBookPage(file:File,index:Int,page:PdfBookPage?,reset:Int,onError:(String)->Unit,onLink:(Int)->Unit) {
    var zoom by remember(file.path,index){mutableFloatStateOf(1f)}
    var pan by remember(file.path,index){mutableStateOf(Offset.Zero)}
    var size by remember{mutableStateOf(IntSize.Zero)}
    var failed by remember(file.path,index){mutableStateOf(false)}
    val info by rememberUpdatedState(page);val goTo by rememberUpdatedState(onLink);val report by rememberUpdatedState(onError)
    LaunchedEffect(reset){zoom=1f;pan=Offset.Zero}
    val bitmap by produceState<Bitmap?>(null,file.path,index){
        try{value=withContext(Dispatchers.IO){
            ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY).use{descriptor->
                PdfRenderer(descriptor).use{renderer->renderer.openPage(index).use{pdf->
                    Bitmap.createBitmap(pdf.width*2,pdf.height*2,Bitmap.Config.ARGB_8888).also{image->
                        image.eraseColor(android.graphics.Color.WHITE);pdf.render(image,null,null,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    }
                }}
            }
        }}catch(e:CancellationException){throw e}catch(e:Exception){failed=true;report(e.message?:"第 ${index+1} 页暂时无法读取，请重新生成预览。")}
    }
    fun clamp(value:Offset,scale:Float):Offset {
        val x=size.width*(scale-1)/2;val y=size.height*(scale-1)/2
        return Offset(value.x.coerceIn(-x,x),value.y.coerceIn(-y,y))
    }
    Box(Modifier.fillMaxWidth().aspectRatio(if(page!=null)page.width/page.height else 148f/210f).clipToBounds().background(Color.White)
        .onSizeChanged{size=it}.testTag("memoir.pdf.page.$index")
        .semantics{
            contentDescription="第 ${index+1} 页"
            stateDescription=if(zoom>1f)"已放大，可单指移动，双击还原"else"原始大小，可上下翻阅，双指缩放"
            customActions=listOf(CustomAccessibilityAction("还原大小"){zoom=1f;pan=Offset.Zero;true},CustomAccessibilityAction("放大"){zoom=(zoom+1).coerceAtMost(5f);true})+
                page?.links.orEmpty().map{link->CustomAccessibilityAction("跳转到第 ${link.target+1} 页"){goTo(link.target);true}}
        }
        .pointerInput(file.path,index){detectTapGestures(onDoubleTap={zoom=1f;pan=Offset.Zero},onTap={point->info?.linkAt(point,size,zoom,pan)?.let(goTo)})}
        .pointerInput(file.path,index){
            // Leave a single finger at scale 1 completely unconsumed for LazyColumn scrolling.
            awaitEachGesture {
                awaitFirstDown(requireUnconsumed=false)
                var dragging=false;var accumulated=Offset.Zero
                do {
                    val event=awaitPointerEvent()
                    val multiple=event.changes.count{it.pressed}>=2||event.changes.count{it.previousPressed}>=2
                    val moved=event.calculatePan()
                    if(multiple) {
                        val center=Offset(size.width/2f,size.height/2f)
                        val centroid=event.calculateCentroid(useCurrent=false)
                        val next=(zoom*event.calculateZoom()).coerceIn(1f,5f)
                        val anchor=if(centroid.x.isFinite()&&centroid.y.isFinite())centroid else center
                        pan=clamp(anchor-center-(anchor-center-pan)*(next/zoom)+moved,next);zoom=next
                        event.changes.forEach{it.consume()};dragging=true
                    } else if(zoom>1.001f) {
                        accumulated+=moved
                        if(!dragging&&accumulated.getDistance()>viewConfiguration.touchSlop)dragging=true
                        if(dragging){pan=clamp(pan+moved,zoom);event.changes.forEach{it.consume()}}
                    }
                }while(event.changes.any{it.pressed})
            }
        },contentAlignment=Alignment.Center) {
        bitmap?.let{Image(it.asImageBitmap(),null,Modifier.fillMaxSize().graphicsLayer{scaleX=zoom;scaleY=zoom;translationX=pan.x;translationY=pan.y})}
            ?:if(failed)Text("此页暂时无法读取，请重新生成预览。",color=JournalColors.Danger)
            else CircularProgressIndicator(Modifier.size(24.dp),strokeWidth=2.dp)
    }
}
