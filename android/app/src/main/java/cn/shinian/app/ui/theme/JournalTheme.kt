package cn.shinian.app.ui.theme

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cn.shinian.app.R

/** Visual tokens shared with the current SwiftUI JournalTheme. */
object JournalColors {
    val Paper = Color(0xFFFBF5EC)
    val PaperSecondary = Color(0xFFF6EDE0)
    val Surface = Color(0xFFFFFDF9)
    val Ink = Color(0xFF3D2E24)
    val SecondaryInk = Color(0xFF6B5848)
    val Muted = Color(0xFFA08C7B)
    val Placeholder = Color(0xFFC3B09F)
    val Line = Color(0xFFEEE2D3)
    val CardBorder = Color(0xFFE8D7C4).copy(alpha = 0.55f)
    val Accent = Color(0xFFD47B52)
    val AccentDeep = Color(0xFFB9623D)
    val AuthAccent = Color(0xFFAD5634)
    val Soft = Color(0xFFF8E3D5)
    val AccentFaint = Color(0xFFFCF1E9)
    val AccentGlow = Color(0xFFE39468)
    val AccentDark = Color(0xFFC2683F)
    val Sage = Color(0xFF8EA27C)
    val SageSoft = Color(0xFFE6ECDD)
    val SageInk = Color(0xFF5E7350)
    val Butter = Color(0xFFF1C36C)
    val ButterSoft = Color(0xFFFBEFD3)
    val ButterInk = Color(0xFFB07D20)
    val Rose = Color(0xFFD99A96)
    val RoseSoft = Color(0xFFF7E4E1)
    val RoseInk = Color(0xFFA35A55)
    val Danger = Color(0xFFC0574A)
    val StoryInk = Color(0xFF4A392D)
    val Film = Color(0xFF4A3A30)
    val Shadow = Color(0xFF96623A)
}

object JournalDimensions {
    val Gutter = 22.dp
    val CardRadius = 22.dp
    val TouchTarget = 48.dp
}

object JournalTypography {
    // PingFang is an Apple system font and is intentionally not redistributed.
    val Body = FontFamily.SansSerif
    val Story = FontFamily(Font(R.font.noto_serif_sc, FontWeight.Normal))

    fun body(size: Int, medium: Boolean = false) = TextStyle(
        fontFamily = Body,
        fontWeight = if (medium) FontWeight.Medium else FontWeight.Normal,
        fontSize = size.sp,
        letterSpacing = 0.sp,
    )

    fun story(size: Int) = TextStyle(
        fontFamily = Story,
        fontWeight = FontWeight.Normal,
        fontSize = size.sp,
        letterSpacing = 0.sp,
    )
}

private val Colors = lightColorScheme(
    primary = JournalColors.AuthAccent,
    onPrimary = Color.White,
    primaryContainer = JournalColors.Soft,
    onPrimaryContainer = JournalColors.Ink,
    secondary = JournalColors.SageInk,
    onSecondary = Color.White,
    secondaryContainer = JournalColors.SageSoft,
    onSecondaryContainer = JournalColors.Ink,
    background = JournalColors.Paper,
    onBackground = JournalColors.Ink,
    surface = JournalColors.Surface,
    onSurface = JournalColors.Ink,
    surfaceVariant = JournalColors.PaperSecondary,
    onSurfaceVariant = JournalColors.SecondaryInk,
    outline = JournalColors.Line,
    error = JournalColors.Danger,
    onError = Color.White,
)

/** The iOS app currently uses the light paper theme in both system appearances. */
@Composable
fun ShinianTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = Colors,
        typography = Typography(
            displaySmall = JournalTypography.story(32),
            headlineLarge = JournalTypography.story(30),
            headlineMedium = JournalTypography.story(24),
            headlineSmall = JournalTypography.story(22),
            titleLarge = JournalTypography.body(22, medium = true),
            titleMedium = JournalTypography.body(16, medium = true),
            titleSmall = JournalTypography.body(14, medium = true),
            bodyLarge = JournalTypography.body(16),
            bodyMedium = JournalTypography.body(14),
            bodySmall = JournalTypography.body(12),
            labelLarge = JournalTypography.body(16, medium = true),
            labelMedium = JournalTypography.body(13, medium = true),
            labelSmall = JournalTypography.body(12),
        ),
        content = content,
    )
}

/** Warm paper with the same upper-right apricot and lower-left sage light. */
@Composable
fun JournalBackdrop(
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit,
) {
    Box(modifier = modifier) {
        Canvas(Modifier.fillMaxSize()) {
            drawRect(JournalColors.Paper)
            withTransform({
                translate(size.width, 0f)
                scale(1.2f, 0.6f, Offset.Zero)
            }) {
                drawCircle(
                    brush = Brush.radialGradient(
                        0f to Color(0xFFFDE9D9),
                        0.55f to Color.Transparent,
                        center = Offset.Zero,
                        radius = size.maxDimension,
                    ),
                    radius = size.maxDimension,
                    center = Offset.Zero,
                )
            }
            withTransform({
                translate(0f, size.height)
                scale(0.9f, 0.5f, Offset.Zero)
            }) {
                drawCircle(
                    brush = Brush.radialGradient(
                        0f to Color(0xFFEEF1E4),
                        0.6f to Color.Transparent,
                        center = Offset.Zero,
                        radius = size.maxDimension,
                    ),
                    radius = size.maxDimension,
                    center = Offset.Zero,
                )
            }
        }
        content()
    }
}
