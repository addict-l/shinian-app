package cn.shinian.app.ui.care

import android.content.res.Resources
import android.graphics.PathMeasure
import android.graphics.RectF
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.asAndroidPath
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import cn.shinian.app.R
import cn.shinian.app.ui.browse.JournalIcon
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import org.xmlpull.v1.XmlPullParser

/** Fixed square design icons. System-symbol call sites use [CareSymbol] explicitly. */
@Composable
fun CareIcon(name: String, description: String? = null, modifier: Modifier = Modifier, tint: Color = CareColors.SecondaryInk) {
    JournalIcon(name, description, modifier, tint)
}

/** Numeric frame/ink measurements only; artwork comes from our own project vectors. */
private data class SymbolMetrics(val width: Float, val height: Float, val left: Float, val top: Float, val inkWidth: Float, val inkHeight: Float)

private fun canonicalSymbol(name: String): String = when (name) {
    "back" -> "chevron.left"
    "chev", "nextChevron" -> "chevron.right"
    "chevronUp", "upChevron" -> "chevron.up"
    "down", "chevronDown" -> "chevron.down"
    "next", "arrow" -> "arrow.right"
    "up" -> "arrow.up"
    "x" -> "xmark"
    "edit" -> "pencil"
    "chat" -> "bubble.left"
    "image" -> "photo"
    "speaker" -> "speaker.wave.2"
    "spark" -> "sparkles"
    "check" -> "checkmark"
    "checkCircle" -> "checkmark.circle"
    "cal" -> "calendar"
    "gear" -> "gearshape"
    "users" -> "person.2"
    "home" -> "house"
    "refresh" -> "arrow.clockwise"
    "more" -> "ellipsis"
    "pin", "location" -> "mappin.and.ellipse"
    "grid" -> "square.grid.2x2"
    "sun" -> "sun.max"
    "cup" -> "cup.and.saucer"
    "error" -> "exclamationmark.circle"
    "stop" -> "stop.fill"
    "stopCircle" -> "stop.circle"
    "shield" -> "checkmark.shield"
    "info" -> "info.circle"
    "text", "textBook" -> "text.book.closed"
    "textCheck" -> "text.badge.checkmark"
    "diagonal" -> "arrow.up.right"
    "logout" -> "rectangle.portrait.and.arrow.right"
    else -> name
}

private fun symbolResource(name: String): Int = when (name) {
    "chevron.left" -> R.drawable.ic_design_back
    "chevron.right" -> R.drawable.ic_design_chev
    "chevron.up" -> R.drawable.ic_care_chevron_up
    "chevron.down" -> R.drawable.ic_design_down
    "arrow.right" -> R.drawable.ic_care_next
    "arrow.up" -> R.drawable.ic_design_up
    "mic" -> R.drawable.ic_care_mic
    "pause" -> R.drawable.ic_care_pause
    "xmark" -> R.drawable.ic_design_x
    "pencil" -> R.drawable.ic_design_edit
    "bubble.left" -> R.drawable.ic_design_chat
    "photo" -> R.drawable.ic_design_image
    "speaker.wave.2" -> R.drawable.ic_design_speaker
    "sparkles" -> R.drawable.ic_care_spark
    "heart" -> R.drawable.ic_design_heart
    "checkmark" -> R.drawable.ic_design_check
    "checkmark.circle" -> R.drawable.ic_care_check_circle
    "calendar" -> R.drawable.ic_design_cal
    "gearshape" -> R.drawable.ic_care_gear
    "person.2" -> R.drawable.ic_design_users
    "person" -> R.drawable.ic_design_person
    "book" -> R.drawable.ic_design_book
    "house" -> R.drawable.ic_design_home
    "arrow.clockwise" -> R.drawable.ic_design_refresh
    "shuffle" -> R.drawable.ic_journal_shuffle
    "ellipsis" -> R.drawable.ic_design_more
    "eye" -> R.drawable.ic_design_eye
    "mappin.and.ellipse" -> R.drawable.ic_care_pin
    "keyboard" -> R.drawable.ic_design_keyboard
    "square.grid.2x2" -> R.drawable.ic_design_grid
    "sun.max" -> R.drawable.ic_design_sun
    "briefcase" -> R.drawable.ic_design_briefcase
    "cup.and.saucer" -> R.drawable.ic_design_cup
    "exclamationmark.circle" -> R.drawable.ic_design_error
    "stop.fill" -> R.drawable.ic_care_stop
    "stop.circle" -> R.drawable.ic_care_stop_circle
    "checkmark.shield" -> R.drawable.ic_design_shield
    "text.book.closed" -> R.drawable.ic_care_text_book
    "text.badge.checkmark" -> R.drawable.ic_design_text_check
    "plus" -> R.drawable.ic_design_plus
    "arrow.up.right" -> R.drawable.ic_care_diagonal
    "rectangle.portrait.and.arrow.right" -> R.drawable.ic_design_logout
    else -> R.drawable.ic_journal_info
}

private val symbolMetrics: Map<String, SymbolMetrics> = mapOf(
    "chevron.left" to SymbolMetrics(0.7333333f, 0.9833333f, 0.0666667f, 0.0666667f, 0.4833333f, 0.85f),
    "chevron.right" to SymbolMetrics(0.7333333f, 0.9833333f, 0.1833333f, 0.0666667f, 0.4833333f, 0.85f),
    "chevron.up" to SymbolMetrics(1.0833333f, 0.6166667f, 0.1166667f, 0.0666667f, 0.85f, 0.4833333f),
    "chevron.down" to SymbolMetrics(1.0833333f, 0.6166667f, 0.1166667f, 0.0666667f, 0.85f, 0.4833333f),
    "arrow.right" to SymbolMetrics(1.15f, 0.8833333f, 0.1166667f, 0.0666667f, 0.9166667f, 0.75f),
    "arrow.up" to SymbolMetrics(0.9833333f, 1.0666667f, 0.1166667f, 0.0666667f, 0.75f, 0.9333333f),
    "mic" to SymbolMetrics(1.0f, 1.1833333f, 0.15f, 0.0666667f, 0.7f, 1.05f),
    "pause" to SymbolMetrics(0.65f, 0.95f, 0.1166667f, 0.0666667f, 0.4166667f, 0.8166667f),
    "xmark" to SymbolMetrics(1.0166667f, 0.9166667f, 0.1166667f, 0.0666667f, 0.7833333f, 0.7833333f),
    "pencil" to SymbolMetrics(1.0166667f, 0.9333333f, 0.1166667f, 0.0666667f, 0.7916667f, 0.7875f),
    "bubble.left" to SymbolMetrics(1.3166667f, 1.15f, 0.1166667f, 0.0666667f, 1.0833333f, 1.0166667f),
    "photo" to SymbolMetrics(1.4f, 1.0333333f, 0.1166667f, 0.0666667f, 1.1666667f, 0.9f),
    "speaker.wave.2" to SymbolMetrics(1.4f, 1.0f, 0.15f, 0.0666667f, 1.1f, 0.8666667f),
    "sparkles" to SymbolMetrics(1.1166667f, 1.25f, 0.1f, 0.0666667f, 0.9166667f, 1.1166667f),
    "heart" to SymbolMetrics(1.2166667f, 1.0333333f, 0.1166667f, 0.0666667f, 0.9833333f, 0.9f),
    "checkmark" to SymbolMetrics(1.0833333f, 0.9833333f, 0.1166667f, 0.0666667f, 0.85f, 0.8416667f),
    "calendar" to SymbolMetrics(1.2166667f, 1.0333333f, 0.1166667f, 0.0666667f, 0.9833333f, 0.9f),
    "gearshape" to SymbolMetrics(1.2166667f, 1.1833333f, 0.0833333f, 0.0666667f, 1.05f, 1.05f),
    "person.2" to SymbolMetrics(1.6f, 1.1166667f, 0.1166667f, 0.125f, 1.3708333f, 0.925f),
    "person" to SymbolMetrics(1.1f, 1.05f, 0.1166667f, 0.0666667f, 0.8666667f, 0.9166667f),
    "book" to SymbolMetrics(1.3333333f, 1.05f, 0.1166667f, 0.0666667f, 1.1f, 0.9166667f),
    "house" to SymbolMetrics(1.4f, 1.1666667f, 0.1166667f, 0.0666667f, 1.1666667f, 1.0333333f),
    "arrow.clockwise" to SymbolMetrics(1.0333333f, 1.1833333f, 0.0833333f, 0.0666667f, 0.8666667f, 1.05f),
    "shuffle" to SymbolMetrics(1.3666667f, 1.0333333f, 0.1166667f, 0.0666667f, 1.1333333f, 0.8916667f),
    "ellipsis" to SymbolMetrics(1.0833333f, 0.3333333f, 0.0833333f, 0.0666667f, 0.9166667f, 0.2f),
    "eye" to SymbolMetrics(1.55f, 0.9833333f, 0.1f, 0.0666667f, 1.3416667f, 0.85f),
    "mappin.and.ellipse" to SymbolMetrics(1.1f, 1.3f, 0.0833333f, 0.0666667f, 0.9333333f, 1.0875f),
    "keyboard" to SymbolMetrics(1.4666667f, 0.9166667f, 0.1166667f, 0.0666667f, 1.2333333f, 0.7833333f),
    "square.grid.2x2" to SymbolMetrics(1.1333333f, 1.0333333f, 0.1166667f, 0.0666667f, 0.9f, 0.9f),
    "sun.max" to SymbolMetrics(1.2333333f, 1.2f, 0.0833333f, 0.0666667f, 1.0666667f, 1.0666667f),
    "briefcase" to SymbolMetrics(1.3666667f, 1.0833333f, 0.1166667f, 0.0666667f, 1.1333333f, 0.95f),
    "cup.and.saucer" to SymbolMetrics(1.5166667f, 1.0833333f, 0.1166667f, 0.0666667f, 1.2833333f, 0.95f),
    "exclamationmark.circle" to SymbolMetrics(1.1666667f, 1.1333333f, 0.0833333f, 0.0666667f, 1.0f, 1.0f),
    "checkmark.circle" to SymbolMetrics(1.1666667f, 1.1333333f, 0.0833333f, 0.0666667f, 1.0f, 1.0f),
    "stop.fill" to SymbolMetrics(1.0333333f, 0.9333333f, 0.1166667f, 0.0666667f, 0.8f, 0.8f),
    "stop.circle" to SymbolMetrics(1.1666667f, 1.1333333f, 0.0833333f, 0.0666667f, 1.0f, 1.0f),
    "checkmark.shield" to SymbolMetrics(1.05f, 1.1333333f, 0.1166667f, 0.0666667f, 0.8166667f, 1.0f),
    "info.circle" to SymbolMetrics(1.1666667f, 1.1333333f, 0.0833333f, 0.0666667f, 1.0f, 1.0f),
    "text.book.closed" to SymbolMetrics(1.0666667f, 1.1833333f, 0.1166667f, 0.0666667f, 0.8333333f, 1.05f),
    "text.badge.checkmark" to SymbolMetrics(1.2333333f, 1.0666667f, 0.1166667f, 0.0666667f, 0.9916667f, 0.9333333f),
    "plus" to SymbolMetrics(1.05f, 0.95f, 0.1166667f, 0.0666667f, 0.8166667f, 0.8166667f),
    "arrow.up.right" to SymbolMetrics(0.9666667f, 0.8666667f, 0.1166667f, 0.0666667f, 0.7333333f, 0.7333333f),
    "rectangle.portrait.and.arrow.right" to SymbolMetrics(1.3833333f, 1.1833333f, 0.1166667f, 0.0666667f, 1.1416667f, 1.05f),
)

fun careSymbolWidth(name: String, fontSize: Dp): Dp = fontSize * (symbolMetrics[canonicalSymbol(name)] ?: symbolMetrics.getValue("info.circle")).width
fun careSymbolHeight(name: String, fontSize: Dp): Dp = fontSize * (symbolMetrics[canonicalSymbol(name)] ?: symbolMetrics.getValue("info.circle")).height

/**
 * Matches each symbol's measured layout frame and visible ink, rather than fitting every
 * glyph into a square. XML paths are authored in this repository, not exported Apple glyphs.
 */
@Composable
fun CareSymbol(name: String, fontSize: Dp, description: String? = null,
    tint: Color = CareColors.SecondaryInk, modifier: Modifier = Modifier) {
    val canonical = canonicalSymbol(name)
    val metrics = symbolMetrics[canonical] ?: symbolMetrics.getValue("info.circle")
    val resource = symbolResource(canonical)
    val resources = LocalContext.current.resources
    val vector = remember(resource, resources) { ownVectorGeometry(resources, resource) }
    val painter = painterResource(resource)
    val accessible = if (description == null) Modifier else Modifier.semantics { contentDescription = description }
    Canvas(modifier.size(fontSize * metrics.width, fontSize * metrics.height).then(accessible)) {
        val point = fontSize.toPx()
        val sx = point * metrics.inkWidth / vector.bounds.width()
        val sy = point * metrics.inkHeight / vector.bounds.height()
        withTransform({
            translate(point * metrics.left - vector.bounds.left * sx, point * metrics.top - vector.bounds.top * sy)
            scale(sx, sy, Offset.Zero)
        }) {
            with(painter) { draw(Size(vector.width, vector.height), colorFilter = ColorFilter.tint(tint)) }
        }
    }
}

private data class OwnVectorGeometry(val width: Float, val height: Float, val bounds: RectF)
private val ownVectorCache = ConcurrentHashMap<Int, OwnVectorGeometry>()
private const val androidNamespace = "http://schemas.android.com/apk/res/android"

/** Resolve the visible bounds of our stroked/filled paths once; SVG viewport padding is not ink. */
private fun ownVectorGeometry(resources: Resources, id: Int): OwnVectorGeometry = ownVectorCache.getOrPut(id) {
    val parser = resources.getXml(id)
    var width = 24f
    var height = 24f
    var left = Float.POSITIVE_INFINITY
    var right = Float.NEGATIVE_INFINITY
    var top = Float.POSITIVE_INFINITY
    var bottom = Float.NEGATIVE_INFINITY
    try {
        while (parser.eventType != XmlPullParser.END_DOCUMENT) {
            if (parser.eventType == XmlPullParser.START_TAG && parser.name == "vector") {
                width = parser.getAttributeFloatValue(androidNamespace, "viewportWidth", 24f)
                height = parser.getAttributeFloatValue(androidNamespace, "viewportHeight", 24f)
            } else if (parser.eventType == XmlPullParser.START_TAG && parser.name == "path") {
                val data = parser.getAttributeValue(androidNamespace, "pathData")
                val fillVisible = vectorColorVisible(parser.getAttributeValue(androidNamespace, "fillColor")) &&
                    parser.getAttributeFloatValue(androidNamespace, "fillAlpha", 1f) > 0f
                val strokeVisible = vectorColorVisible(parser.getAttributeValue(androidNamespace, "strokeColor")) &&
                    parser.getAttributeFloatValue(androidNamespace, "strokeAlpha", 1f) > 0f
                val stroke = if (strokeVisible) parser.getAttributeFloatValue(androidNamespace, "strokeWidth", 0f) / 2 else 0f
                if (data != null && (fillVisible || stroke > 0f)) {
                    val path = PathParser().parsePathString(data).toPath().asAndroidPath()
                    val measure = PathMeasure(path, false)
                    val point = FloatArray(2)
                    do {
                        val length = measure.length
                        val samples = ceil(length * 16).toInt().coerceIn(1, 2400)
                        for (index in 0..samples) if (measure.getPosTan(length * index / samples, point, null)) {
                            left = min(left, point[0] - stroke); right = max(right, point[0] + stroke)
                            top = min(top, point[1] - stroke); bottom = max(bottom, point[1] + stroke)
                        }
                    } while (measure.nextContour())
                }
            }
            parser.next()
        }
    } finally { parser.close() }
    val bounds = if (left.isFinite() && right > left && bottom > top) RectF(left, top, right, bottom) else RectF(0f, 0f, width, height)
    OwnVectorGeometry(width, height, bounds)
}

private fun vectorColorVisible(value: String?): Boolean = when {
    value == null || value == "@android:color/transparent" -> false
    value.startsWith("#") && value.length == 9 -> value.substring(1, 3).toIntOrNull(16) != 0
    value == "#0000" -> false
    else -> true
}
