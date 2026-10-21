package cn.shinian.app.ui.chat

import android.graphics.Bitmap
import android.graphics.Color
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.data.AuthSession
import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.ChatMessage
import cn.shinian.app.data.Media
import cn.shinian.app.ui.theme.ShinianTheme
import java.io.ByteArrayOutputStream
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the actual message layout and authenticated image transport with deterministic pixels. */
@RunWith(AndroidJUnit4::class)
class ChatPhotoInteractionTest {
    @get:Rule val compose = createComposeRule()
    private val transport = PhotoTransport()
    private val repository = BackendRepository(transport.session, OkHttpClient.Builder().addInterceptor(transport).build())
    private val density get() = InstrumentationRegistry.getInstrumentation().targetContext.resources.displayMetrics.density
    @After fun cleanup() { repository.invalidate() }
    private fun bounds(tag:String):Rect = compose.onNodeWithTag(tag, useUnmergedTree = true).fetchSemanticsNode().boundsInRoot
    private fun photo(index:Int) = Media(UUID(0L,index.toLong()+1).toString(), "/api/v1/media/${UUID(0L,index.toLong()+1)}")

    @Test fun singleAndTwoPhotosKeepIosRatiosAboveTheSeparateTextBubble() {
        var count by mutableIntStateOf(1)
        compose.setContent {
            ShinianTheme { Box(Modifier.fillMaxSize().testTag("host")) {
                ChatMessageView(ChatMessage("story","user","照片里的那一天",(0 until count).map(::photo)), repository)
            } }
        }
        val firstId = photo(0).id
        var image = bounds("chat.photo.$firstId")
        val grid = bounds("chat.message.photos.story")
        assertEquals(4f/3f,image.width/image.height,.015f)
        assertTrue(grid.width/density <= 264.5f)
        assertTrue(grid.left-bounds("host").left >= 60f*density-.5f)
        assertTrue(grid.bottom <= bounds("chat.message.text.story").top)
        compose.onNodeWithTag("chat.message.story").assertTextEquals("照片里的那一天")
        compose.runOnIdle { count = 2 }
        image = bounds("chat.photo.$firstId")
        assertEquals(129f/96f,image.width/image.height,.015f)
        assertEquals(image.width,bounds("chat.photo.${photo(1).id}").width,1f)
    }

    @Test fun fourPhotosKeepTheLastCellSquareAndAlignedWithTheFirstColumn() {
        compose.setContent { ShinianTheme {
            ChatMessageView(ChatMessage("four","user","",(0 until 4).map(::photo)),repository)
        } }
        val first = bounds("chat.photo.${photo(0).id}")
        val last = bounds("chat.photo.${photo(3).id}")
        assertEquals(first.width,first.height,1f)
        assertEquals(first.width,last.width,1f)
        assertEquals(first.left,last.left,1f)
        assertTrue(last.top > first.bottom)
        compose.onNodeWithTag("chat.message.four").assertDoesNotExist()
    }

    @Test fun allNinePendingPhotosRemainVisibleAndTakePriorityOverPartialRemoteAttachments() {
        val photos = (0 until 9).map { SelectedPhoto("pending-$it",transport.png) }
        compose.setContent { ShinianTheme { Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            ChatMessageView(ChatMessage("pending","user","九张照片",listOf(photo(0))),repository,localPhotos=photos)
        } } }
        photos.forEach { compose.onNodeWithTag("chat.pendingPhoto.${it.id}").assertExists() }
        val firstWidth = bounds("chat.pendingPhoto.pending-0").width
        compose.onNodeWithTag("chat.pendingPhoto.pending-8").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("chat.photo.${photo(0).id}").assertDoesNotExist()
        assertEquals(firstWidth,bounds("chat.pendingPhoto.pending-8").width,1f)
        compose.runOnIdle { assertEquals(0,transport.requests.get()) }
    }

    @Test fun failedPhotoAtDoubleFontCanBeReadAndRetriedByTappingTheWholeCell() {
        transport.failFirst = true
        var opened = 0
        val media = photo(0)
        compose.setContent { ShinianTheme {
            val current = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(current.density,2f)) {
                Box(Modifier.fillMaxSize().padding(32.dp)) { RemoteChatPhoto(media,repository,Modifier.size(84.dp),onOpen={opened++}) }
            }
        } }
        compose.waitUntil(10_000) {
            runCatching { compose.onNodeWithTag("chat.photo.${media.id}").fetchSemanticsNode().config[SemanticsProperties.StateDescription] == "照片加载失败" }.getOrDefault(false)
        }
        compose.onNodeWithText("加载失败",useUnmergedTree=true).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("chat.photo.${media.id}").performClick()
        compose.waitUntil(10_000) {
            runCatching { compose.onNodeWithTag("chat.photo.${media.id}").fetchSemanticsNode().config[SemanticsProperties.StateDescription] == "照片已加载" }.getOrDefault(false)
        }
        assertEquals(2,transport.requests.get())
        assertTrue(transport.authenticated)
        compose.onNodeWithTag("chat.photo.${media.id}").performClick()
        compose.runOnIdle { assertEquals(1,opened) }
    }

    private class PhotoTransport : Interceptor {
        val session=AuthSession("https://photo-test.invalid",UUID.randomUUID().toString(),UUID.randomUUID().toString(),"photo_test",token="photo-test-token",expiresAt="2099-01-01T00:00:00Z")
        val requests=AtomicInteger()
        @Volatile var failFirst=false
        @Volatile var authenticated=false
        val png:ByteArray by lazy {
            val bitmap=Bitmap.createBitmap(160,120,Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(Color.rgb(130,80,45))
            ByteArrayOutputStream().use { bytes -> bitmap.compress(Bitmap.CompressFormat.PNG,100,bytes);bitmap.recycle();bytes.toByteArray() }
        }
        override fun intercept(chain:Interceptor.Chain):Response {
            val request=chain.request()
            authenticated=request.header("Authorization")=="Bearer ${session.token}"
            val attempt=requests.incrementAndGet()
            val failed=failFirst&&attempt==1
            val body=if(failed) "{\"detail\":\"照片暂时无法读取，请重新加载。\"}".toByteArray() else png
            return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(if(failed)503 else 200).message(if(failed)"Unavailable"else"OK")
                .body(body.toResponseBody((if(failed)"application/json"else"image/png").toMediaType())).build()
        }
    }
}
