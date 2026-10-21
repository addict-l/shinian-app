package cn.shinian.app.media

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import android.net.Uri
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Decode with a bounded pixel count, preserve EXIF orientation, and upload JPEG only. */
suspend fun preparePhoto(context: Context, uri: Uri): ByteArray = withContext(Dispatchers.IO) {
    val resolver = context.contentResolver
    fun stream() = resolver.openInputStream(uri)
        ?: throw IllegalArgumentException("照片无法读取，请重新选择。")
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    stream().use { BitmapFactory.decodeStream(it, null, bounds) }
    require(bounds.outWidth > 0 && bounds.outHeight > 0) { "照片无法读取，请重新选择。" }
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 5120) sample *= 2
    val options = BitmapFactory.Options().apply {
        inSampleSize = sample
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }
    var image = stream().use { BitmapFactory.decodeStream(it, null, options) }
        ?: throw IllegalArgumentException("照片无法读取，请重新选择。")
    try {
        val orientation = runCatching {
            stream().use { ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL) }
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
        val matrix = Matrix().apply {
            when (orientation) {
                ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
                ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
                ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
                ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
                ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(270f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(270f)
            }
            val scale = minOf(1f, 2560f / maxOf(image.width, image.height))
            postScale(scale, scale)
        }
        if (!matrix.isIdentity) {
            val transformed = Bitmap.createBitmap(image, 0, 0, image.width, image.height, matrix, true)
            if (transformed !== image) { image.recycle(); image = transformed }
        }
        for (quality in listOf(85, 65, 45)) {
            val bytes = ByteArrayOutputStream().use { output ->
                check(image.compress(Bitmap.CompressFormat.JPEG, quality, output)) { "照片压缩失败，请重新选择。" }
                output.toByteArray()
            }
            if (bytes.isNotEmpty() && bytes.size <= 8 * 1024 * 1024) return@withContext bytes
        }
        throw IllegalArgumentException("照片压缩后仍超过 8 MB，请选择较小的图片。")
    } finally { image.recycle() }
}
