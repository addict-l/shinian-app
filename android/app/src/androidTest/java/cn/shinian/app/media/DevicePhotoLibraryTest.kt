package cn.shinian.app.media

import android.content.ContentUris
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.annotation.RequiresApi
import androidx.exifinterface.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Only creates/deletes two app-owned fixtures in a unique temporary MediaStore album. */
@RunWith(AndroidJUnit4::class)
class DevicePhotoLibraryTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val resolver get() = context.contentResolver

    @Test fun ownPhotosRespectPublicationTrashAndOrderWithBoundedExifAwareDecoding() = runBlocking {
        assumeTrue("App-owned MediaStore insertion without broad storage access requires Android 10", Build.VERSION.SDK_INT >= 29)
        val marker = "ShinianLibraryTest-${UUID.randomUUID()}"
        val temporary = File(context.cacheDir, marker).apply { mkdirs() }
        val inserted = mutableListOf<Uri>()
        try {
            val summer = File(temporary, "summer.jpg")
            instrumentation.context.assets.open("photo-review-summer.jpg").use { input -> summer.outputStream().use { input.copyTo(it) } }
            val original = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(summer.absolutePath, original)
            ExifInterface(summer).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_ROTATE_90.toString())
                saveAttributes()
            }
            val dinner = File(temporary, "dinner.jpg")
            val source = instrumentation.context.assets.open("photo-review-dinner.jpg").use { BitmapFactory.decodeStream(it) }
            assertNotNull(source)
            val enlarged = Bitmap.createScaledBitmap(requireNotNull(source), 3072, 2304, true)
            try { dinner.outputStream().use { assertTrue(enlarged.compress(Bitmap.CompressFormat.JPEG, 85, it)) } }
            finally { if (enlarged !== source) enlarged.recycle(); source.recycle() }

            val first = insertPending(summer, marker, "summer", inserted)
            val second = insertPending(dinner, marker, "dinner", inserted)
            val ids = inserted.map(ContentUris::parseId)
            val library = DevicePhotoLibrary(context)
            assertTrue("Pending rows must remain hidden even from the owning app", library.load().none { it.id in ids })

            inserted.forEach { uri ->
                assertEquals(1, resolver.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null))
            }
            val photos = withTimeout(10_000) {
                var found = library.load().filter { it.id in ids }
                while (found.size != 2 || found.any { it.width <= 0 || it.height <= 0 || it.size <= 0 }) {
                    delay(50)
                    found = library.load().filter { it.id in ids }
                }
                found
            }
            assertEquals("Newer rows, including same-second ID ties, must come first", ids.reversed(), photos.map { it.id })
            assertTrue(photos.all { it.albumName == marker && it.albumId.isNotBlank() && it.displayName.startsWith(marker) && it.size > 0 })
            assertTrue(photos.all { it.width > 0 && it.height > 0 })

            if (Build.VERSION.SDK_INT >= 30) {
                assertEquals(1, resolver.update(second, ContentValues().apply { put(MediaStore.Images.Media.IS_TRASHED, 1) }, null, null))
                assertEquals(listOf(ids.first()), library.load().filter { it.id in ids }.map { it.id })
                assertEquals(1, resolver.update(second, ContentValues().apply { put(MediaStore.Images.Media.IS_TRASHED, 0) }, null, null))
            }

            val firstPhoto = photos.single { it.id == ids.first() }
            val thumbnail = library.thumbnail(firstPhoto, 128)
            assertNotNull(thumbnail)
            assertTrue(maxOf(requireNotNull(thumbnail).width, thumbnail.height) <= 128)
            assertSame("Visible cells should reuse the bounded thumbnail cache", thumbnail, library.thumbnail(firstPhoto, 128))
            val rotated = library.preview(firstPhoto, 320)
            assertNotNull(rotated)
            assertTrue(maxOf(requireNotNull(rotated).width, rotated.height) <= 320)
            assertEquals("EXIF rotation must be applied to preview pixels", original.outHeight.toFloat() / original.outWidth,
                rotated.width.toFloat() / rotated.height, .02f)
            val large = library.preview(photos.single { it.id == ids.last() }, 4096)
            assertNotNull(large)
            assertTrue("Even a larger request must obey the 2048px preview ceiling", maxOf(requireNotNull(large).width, large.height) <= 2048)

            // A cached bitmap must not hide a URI that has become unreadable.
            assertEquals(1, resolver.delete(first, null, null))
            inserted.remove(first)
            val removed = runCatching { library.thumbnail(firstPhoto, 128) }
            assertTrue("A deleted URI must never return cached pixels", removed.getOrNull() == null &&
                (removed.isSuccess || removed.exceptionOrNull() is SecurityException))
        } finally {
            var cleanupFailure: Throwable? = null
            inserted.forEach { uri -> runCatching { resolver.delete(uri, null, null) }.onFailure { cleanupFailure = it } }
            temporary.deleteRecursively()
            cleanupFailure?.let { throw AssertionError("未能清理图库测试素材。", it) }
        }
    }

    @RequiresApi(29)
    private fun insertPending(file: File, album: String, suffix: String, inserted: MutableList<Uri>): Uri {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "$album-$suffix.jpg")
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/$album/")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val uri = requireNotNull(resolver.insert(MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY), values))
        inserted += uri
        requireNotNull(resolver.openOutputStream(uri)).use { output -> file.inputStream().use { it.copyTo(output) } }
        return uri
    }
}
