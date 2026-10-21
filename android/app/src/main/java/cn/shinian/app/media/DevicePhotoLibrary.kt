package cn.shinian.app.media

import android.content.ContentUris
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.util.Size
import androidx.exifinterface.media.ExifInterface
import java.io.FileNotFoundException
import java.io.IOException
import java.util.LinkedHashMap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext

data class DevicePhoto(
    val id: Long,
    val uri: Uri,
    val albumId: String,
    val albumName: String,
    val displayName: String,
    val size: Long,
    val width: Int,
    val height: Int,
)

/** Reads only MediaStore metadata until a visible cell asks for its pixels. */
class DevicePhotoLibrary(context: Context) {
    private val resolver = context.applicationContext.contentResolver
    private val cache = ThumbnailCache()

    /** The UI owns permission requests, including Android 14's selected-photo access. */
    suspend fun load(): List<DevicePhoto> = withContext(Dispatchers.IO) {
        val collection = if (Build.VERSION.SDK_INT >= 29) MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
            else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.BUCKET_ID,
            MediaStore.Images.Media.BUCKET_DISPLAY_NAME,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.SIZE,
            MediaStore.Images.Media.WIDTH,
            MediaStore.Images.Media.HEIGHT,
        )
        val filters = buildList {
            if (Build.VERSION.SDK_INT >= 29) add("${MediaStore.Images.Media.IS_PENDING} = 0")
            if (Build.VERSION.SDK_INT >= 30) add("${MediaStore.Images.Media.IS_TRASHED} = 0")
        }
        val cursor = resolver.query(collection, projection, filters.takeIf { it.isNotEmpty() }?.joinToString(" AND "), null,
            "${MediaStore.Images.Media.DATE_ADDED} DESC, ${MediaStore.Images.Media._ID} DESC")
            ?: throw IOException("设备相册暂时无法读取，请重试。")
        cursor.use {
            val idIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val albumIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media.BUCKET_ID)
            val albumNameIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media.BUCKET_DISPLAY_NAME)
            val nameIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val sizeIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media.SIZE)
            val widthIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media.WIDTH)
            val heightIndex = it.getColumnIndexOrThrow(MediaStore.Images.Media.HEIGHT)
            buildList {
                while (it.moveToNext()) {
                    coroutineContext.ensureActive()
                    val id = it.getLong(idIndex)
                    if (id <= 0) continue
                    add(DevicePhoto(id, ContentUris.withAppendedId(collection, id),
                        it.getString(albumIndex)?.takeIf(String::isNotBlank) ?: "other",
                        it.getString(albumNameIndex)?.takeIf(String::isNotBlank) ?: "其他照片",
                        it.getString(nameIndex).orEmpty(), it.getLong(sizeIndex).coerceAtLeast(0),
                        it.getInt(widthIndex).coerceAtLeast(0), it.getInt(heightIndex).coerceAtLeast(0)))
                }
            }
        }
    }

    /** Cached bitmaps are shared with visible cells. Callers must not recycle them. */
    suspend fun thumbnail(photo: DevicePhoto, maxSize: Int = 256): Bitmap? = withContext(Dispatchers.IO) {
        imageSlots.withPermit {
            val limit = maxSize.coerceIn(1, 512)
            try {
                // Check access even on a cache hit so a revoked URI never reuses stale pixels.
                requireReadable(photo.uri)
                val key = ThumbnailKey(photo.uri, limit, photo.size, photo.width, photo.height)
                cache[key]?.let { return@withPermit it }
                val bitmap = if (Build.VERSION.SDK_INT >= 29) {
                    try { bounded(resolver.loadThumbnail(photo.uri, Size(limit, limit), null), limit) }
                    catch (failure: SecurityException) { throw failure }
                    catch (_: IOException) { decode(photo.uri, limit) }
                    catch (_: UnsupportedOperationException) { decode(photo.uri, limit) }
                    catch (_: IllegalArgumentException) { decode(photo.uri, limit) }
                } else decode(photo.uri, limit)
                coroutineContext.ensureActive()
                bitmap?.also { cache.put(key, it) }
            } catch (failure: SecurityException) { throw failure }
            catch (_: IOException) { null }
        }
    }

    /** Original pixels are sampled before decoding; the longest displayed edge never exceeds 2048. */
    suspend fun preview(photo: DevicePhoto, maxSize: Int = 2048): Bitmap? = withContext(Dispatchers.IO) {
        imageSlots.withPermit {
            try {
                requireReadable(photo.uri)
                decode(photo.uri, maxSize.coerceIn(1, 2048)).also { coroutineContext.ensureActive() }
            } catch (failure: SecurityException) { throw failure }
            catch (_: IOException) { null }
        }
    }

    private fun requireReadable(uri: Uri) {
        resolver.openFileDescriptor(uri, "r")?.use { } ?: throw FileNotFoundException("照片暂时无法读取。")
    }

    private fun decode(uri: Uri, limit: Int): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds); Unit } ?: return null
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sample > limit) sample *= 2
        val options = BitmapFactory.Options().apply { inSampleSize = sample; inPreferredConfig = Bitmap.Config.ARGB_8888 }
        val decoded = resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) } ?: return null
        val orientation = try {
            resolver.openInputStream(uri)?.use {
                ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            } ?: ExifInterface.ORIENTATION_NORMAL
        } catch (failure: SecurityException) { throw failure }
        catch (_: IOException) { ExifInterface.ORIENTATION_NORMAL }
        val transform = Matrix().apply {
            when (orientation) {
                ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
                ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
                ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
                ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
                ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(270f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(270f)
            }
        }
        val oriented = if (transform.isIdentity) decoded else Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, transform, true)
        return bounded(oriented, limit)
    }

    private fun bounded(bitmap: Bitmap, limit: Int): Bitmap {
        val longest = maxOf(bitmap.width, bitmap.height)
        if (longest <= limit) return bitmap
        val scale = limit.toFloat() / longest
        return Bitmap.createScaledBitmap(bitmap, (bitmap.width * scale).toInt().coerceAtLeast(1),
            (bitmap.height * scale).toInt().coerceAtLeast(1), true)
    }

    private data class ThumbnailKey(val uri: Uri, val maxSize: Int, val bytes: Long, val width: Int, val height: Int)

    private class ThumbnailCache {
        private val entries = LinkedHashMap<ThumbnailKey, Bitmap>(32, .75f, true)
        private var bytes = 0L
        @Synchronized operator fun get(key: ThumbnailKey): Bitmap? = entries[key]
        @Synchronized fun put(key: ThumbnailKey, bitmap: Bitmap) {
            entries.put(key, bitmap)?.let { bytes -= it.allocationByteCount }
            bytes += bitmap.allocationByteCount
            val iterator = entries.iterator()
            while ((bytes > MAX_CACHE_BYTES || entries.size > MAX_CACHE_ENTRIES) && iterator.hasNext()) {
                bytes -= iterator.next().value.allocationByteCount
                iterator.remove()
                // Compose may still be drawing an evicted bitmap; only release the cache reference.
            }
        }
    }

    private companion object {
        const val MAX_CACHE_BYTES = 12L * 1024 * 1024
        const val MAX_CACHE_ENTRIES = 96
        val imageSlots = Semaphore(3)
    }
}
