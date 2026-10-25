package cn.shinian.app.ui.care

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.dropShadow
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.shadow.Shadow
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.ui.browse.JournalIcon
import cn.shinian.app.ui.theme.JournalColors
import cn.shinian.app.ui.theme.JournalTypography
import cn.shinian.app.ui.theme.JournalBackdrop
import cn.shinian.app.R

private val LocalCareBackdropProvided = staticCompositionLocalOf { false }


object CareTypography {
    // Measured from the current iOS UIFont, rather than Material's default line box.
    fun body(size: Int = 22, medium: Boolean = false, lineSpacing: Float = 0f) = JournalTypography.body(size, medium).copy(
        lineHeight = (size * 1.4f + lineSpacing).sp, platformStyle = PlatformTextStyle(includeFontPadding = false),
        lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Proportional, if (lineSpacing > 0) LineHeightStyle.Trim.Both else LineHeightStyle.Trim.None))
    fun story(size: Int, lineSpacing: Float = 0f) = story(size.toFloat(), lineSpacing)
    fun story(size: Float, lineSpacing: Float = 0f) = JournalTypography.story(1).copy(fontSize = size.sp,
        lineHeight = (size * 1.437f + lineSpacing).sp, platformStyle = PlatformTextStyle(includeFontPadding = false),
        lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Proportional, if (lineSpacing > 0) LineHeightStyle.Trim.Both else LineHeightStyle.Trim.None))
}

/** Independent care-mode tokens, matching iOS CareTheme; ordinary mode keeps its tokens. */
object CareColors {
    val Paper = JournalColors.Paper
    val PaperSecondary = JournalColors.PaperSecondary
    val Surface = JournalColors.Surface
    val Ink = JournalColors.Ink
    val SecondaryInk = JournalColors.SecondaryInk
    val Accent = Color(0xFFAD5634)
    val AccentTop = Color(0xFFC46A41)
    val Accent2 = Color(0xFFC2683F)
    val Soft = Color(0xFFF8E3D5)
    val Faint = Color(0xFFFCF1E9)
    val Border = Color(0xFFE6D5C2)
    val Line = Color(0xFFEADBC9)
    val SageSoft = Color(0xFFE6ECDD)
    val Sage = Color(0xFF8EA27C)
    val SageInk = Color(0xFF4F6443)
    val ButterSoft = Color(0xFFFBEFD3)
    val ButterInk = Color(0xFF8A611A)
    val RoseSoft = Color(0xFFF7E4E1)
    val RoseInk = Color(0xFF97504B)
    val DangerSoft = Color(0xFFFBE6E1)
    val DangerInk = Color(0xFF9C3F2F)
    val RecordSoft = Color(0xFFFBE3DD)
    val RecordInk = Color(0xFFA3402B)
    val RecordDot = Color(0xFFD44B33)
}

enum class CareTone(val fill: Color, val ink: Color) {
    Apricot(CareColors.Soft, CareColors.Accent),
    Sage(CareColors.SageSoft, CareColors.SageInk),
    Butter(CareColors.ButterSoft, CareColors.ButterInk),
    Rose(CareColors.RoseSoft, CareColors.RoseInk),
}

@Composable
fun CareCard(modifier: Modifier = Modifier, padding: Dp = 18.dp, fill: Color = CareColors.Surface,
    radius: Dp = 26.dp, spacing: Dp = if (padding == 0.dp) 0.dp else 14.dp, content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(radius)
    Column(modifier.careShadow(shape, 7.dp, 4.dp, .08f).clip(shape)
        .background(fill).border(1.dp, JournalColors.CardBorder, shape)
        .padding(padding), verticalArrangement = Arrangement.spacedBy(spacing), content = content)
}

fun Modifier.careShadow(shape: Shape, radius: Dp = 7.dp, y: Dp = 4.dp, opacity: Float = .08f,
    color: Color = JournalColors.Shadow): Modifier = dropShadow(shape, Shadow(radius = radius, color = color.copy(alpha = opacity), offset = DpOffset(0.dp, y)))

@Composable
fun CareHeading(title: String, subtitle: String? = null) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = CareTypography.body(30, true), color = CareColors.Ink,
            modifier = Modifier.semantics { heading() })
        subtitle?.let { Text(it, style = CareTypography.body(19), color = CareColors.SecondaryInk) }
    }
}

@Composable
fun CareButton(title: String, modifier: Modifier = Modifier, icon: String? = null,
    secondary: Boolean = false, enabled: Boolean = true, loading: Boolean = false,
    minimumHeight: Dp = if (secondary) 64.dp else 68.dp, fontSize: Int = 24, onClick: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    val active = enabled && !loading
    val fill = Brush.verticalGradient(if (secondary) listOf(CareColors.Surface, CareColors.Surface) else listOf(CareColors.AccentTop, CareColors.Accent))
    Box(modifier.fillMaxWidth().heightIn(min = minimumHeight).alpha(if (active) 1f else .45f)
        .careShadow(shape, if (secondary) 3.dp else 12.dp, if (secondary) 2.dp else 6.dp,
            if (secondary) .03f else .22f, CareColors.Accent)
        .clip(shape).background(fill).then(if (secondary) Modifier.border(1.5.dp, CareColors.Border, shape) else Modifier)
        .clickable(enabled = active, role = Role.Button, onClick = onClick).padding(horizontal = 14.dp, vertical = 14.dp),
        contentAlignment = Alignment.Center) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (loading) CircularProgressIndicator(Modifier.size(24.dp), color = if (secondary) CareColors.Accent else Color.White, strokeWidth = 2.dp)
            else icon?.let { CareSymbol(it, fontSize.dp, tint = if (secondary) CareColors.Accent else Color.White) }
            Text(title, style = CareTypography.body(fontSize, true), color = if (secondary) CareColors.Ink else Color.White,
                textAlign = TextAlign.Center, modifier = Modifier.weight(1f, fill = false))
        }
    }
}

@Composable
fun CarePill(title: String, modifier: Modifier = Modifier, icon: String? = null, enabled: Boolean = true,
    compact: Boolean = false, onClick: () -> Unit) {
    Box(modifier.heightIn(min = if (compact) 48.dp else 56.dp).alpha(if (enabled) 1f else .45f)
        .clip(CircleShape).background(if (compact) CareColors.Faint else CareColors.Surface)
        .then(if (compact) Modifier else Modifier.border(1.5.dp, CareColors.Border, CircleShape))
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
        .padding(horizontal = if (compact) 12.dp else 14.dp, vertical = if (compact) 8.dp else 10.dp), contentAlignment = Alignment.Center) {
        Row(horizontalArrangement = Arrangement.spacedBy(if (compact) 4.dp else 7.dp), verticalAlignment = Alignment.CenterVertically) {
            icon?.let { CareSymbol(it, if (compact) 18.dp else 20.dp, tint = CareColors.Accent) }
            Text(title, style = CareTypography.body(if (compact) 18 else 20, true), textAlign = TextAlign.Center,
                color = if (compact) CareColors.Accent else CareColors.Ink, modifier = Modifier.weight(1f, fill = false))
        }
    }
}

@Composable
fun CareToolbar(title: String, onBack: () -> Unit, modifier: Modifier = Modifier,
    backTitle: String = "返回", step: String? = null, enabled: Boolean = true, backTag: String = "browse.back") {
    Row(modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(top = 6.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.heightIn(min = 52.dp).alpha(if (enabled) 1f else .45f).careShadow(CircleShape, 3.dp, 2.dp, .06f)
            .clip(CircleShape).background(CareColors.Surface).border(1.5.dp, CareColors.Border, CircleShape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onBack).testTag(backTag).padding(horizontal = 12.dp, vertical = 10.dp), contentAlignment = Alignment.Center) {
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
                CareSymbol(when (backTitle) { "暂停" -> "pause"; "取消" -> "x"; else -> "back" }, 20.dp, tint = CareColors.Accent)
                Text(backTitle, style = CareTypography.body(20, true), color = CareColors.Ink)
            }
        }
        Text(title, Modifier.weight(1f).semantics { heading() }, style = CareTypography.body(22, true),
            textAlign = TextAlign.Center, color = CareColors.Ink)
        Box(Modifier.widthIn(min = 76.dp), contentAlignment = Alignment.CenterEnd) {
            if (step != null) Text(step, style = CareTypography.body(19, true), color = CareColors.Accent,
                modifier = Modifier.background(CareColors.Faint, CircleShape).padding(horizontal = 11.dp, vertical = 9.dp))
        }
    }
}

@Composable
fun CareIconTile(icon: String, tone: CareTone = CareTone.Apricot, size: Dp = 56.dp) {
    Box(Modifier.size(size).background(tone.fill, RoundedCornerShape(size * .32f)), contentAlignment = Alignment.Center) {
        CareSymbol(icon, size * .48f, tint = tone.ink)
    }
}

@Composable
fun CareQuestionCard(text: String, modifier: Modifier = Modifier, label: String = "回忆助手问您", compact: Boolean = false) {
    val shape = RoundedCornerShape(if (compact) 22.dp else 26.dp)
    Box(modifier.fillMaxWidth().careShadow(shape, 8.dp, 4.dp, .06f).clip(shape)
        .background(Brush.linearGradient(listOf(CareColors.Faint, CareColors.Surface)))
        .border(1.dp, CareColors.Border.copy(alpha = .65f), shape).padding(if (compact) 14.dp else 22.dp)) {
        if (compact) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            CareIconTile("spark", size = 40.dp)
            Text(text, style = CareTypography.body(19), color = CareColors.SecondaryInk, modifier = Modifier.weight(1f))
        } else Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CareSymbol("spark", 19.dp, tint = CareColors.Accent)
                Text(label, style = CareTypography.body(19, true), color = CareColors.Accent)
            }
            Text(text, style = CareTypography.body(27, true, lineSpacing = 5f), color = CareColors.Ink)
        }
    }
}

@Composable
fun CareDock(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth().background(Brush.verticalGradient(0f to CareColors.Paper.copy(alpha = 0f), .24f to CareColors.Paper, 1f to CareColors.Paper))
        .padding(horizontal = 20.dp).padding(top = 14.dp, bottom = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
}

@Composable
fun CareBackdrop(modifier: Modifier = Modifier, force: Boolean = false, content: @Composable BoxScope.() -> Unit = {}) {
    val alreadyPainted = !force && LocalCareBackdropProvided.current
    Box(modifier) {
        if (!alreadyPainted) Canvas(Modifier.matchParentSize()) {
            drawRect(CareColors.Paper)
            // SwiftUI's EllipticalGradient is sized from each axis, not from maxDimension.
            withTransform({ translate(size.width, 0f); scale(size.width * 1.2f, size.height * .6f, Offset.Zero) }) {
                drawCircle(Brush.radialGradient(0f to Color(0xFFFDE9D9), .55f to Color(0x00FDE9D9), center = Offset.Zero, radius = 1f), 1f, Offset.Zero)
            }
            withTransform({ translate(0f, size.height); scale(size.width * .9f, size.height * .5f, Offset.Zero) }) {
                drawCircle(Brush.radialGradient(0f to Color(0xFFEEF1E4), .6f to Color(0x00EEF1E4), center = Offset.Zero, radius = 1f), 1f, Offset.Zero)
            }
        }
        CompositionLocalProvider(LocalCareBackdropProvided provides true) { content() }
    }
}

@Composable
fun CareModeBackdrop(care: Boolean, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    if (care) CareBackdrop(modifier, content = content) else JournalBackdrop(modifier, content)
}

@Composable
fun CarePage(content: @Composable ColumnScope.() -> Unit) {
    CareBackdrop(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding(), content = content)
    }
}

@Composable
fun CareProgressBar(current: Int, total: Int, modifier: Modifier = Modifier) {
    val count = total.coerceAtLeast(1)
    Box(modifier.fillMaxWidth().height(7.dp).semantics { contentDescription = "第 $current 个问题，共 $total 个" }) {
        if (count > 16) {
            Box(Modifier.fillMaxSize().clip(CircleShape).background(CareColors.Line)) {
                Box(Modifier.fillMaxHeight().fillMaxWidth(((current - .5f) / count).coerceIn(0f, 1f)).background(CareColors.Accent2))
            }
        } else Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            repeat(count) { index ->
                Box(Modifier.weight(1f).fillMaxHeight().clip(CircleShape).background(Color(0xFFEBDDCC))) {
                    if (index < current) Box(Modifier.fillMaxHeight().fillMaxWidth(if (index == current - 1) .5f else 1f).background(CareColors.Accent2))
                }
            }
        }
    }
}

@Composable
fun CareError(message: String, retry: (() -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().background(CareColors.DangerSoft, RoundedCornerShape(22.dp)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CareSymbol("error", 19.dp, tint = CareColors.DangerInk)
            Text(message, style = CareTypography.body(19), color = CareColors.DangerInk, modifier = Modifier.weight(1f))
        }
        retry?.let { CareButton("再试一次", icon = "refresh", secondary = true, onClick = it) }
    }
}

@Composable
fun CareBusyOverlay(text: String) {
    Box(Modifier.fillMaxSize().background(CareColors.Paper.copy(alpha = .94f)), contentAlignment = Alignment.Center) {
        Column(Modifier.padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(24.dp)) {
            CircularProgressIndicator(Modifier.size(54.dp), color = CareColors.Accent)
            Text(text, style = CareTypography.body(22, true), color = CareColors.Ink, textAlign = TextAlign.Center)
        }
    }
}

fun careMeaningful(value: String?): String? = value?.trim()?.takeIf {
    it.isNotEmpty() && it !in setOf("待补充", "未提及", "未知", "时间待补充", "时间记不清", "时间暂不透露", "记不清", "暂不透露")
}
