package cn.shinian.app.ui.media

import android.Manifest
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Build
import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cn.shinian.app.ui.theme.ShinianTheme
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Opt in after denying/fixing image permission on the disposable Android review emulator. */
@RunWith(AndroidJUnit4::class)
class PhotoPickerPermissionDeniedTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun deniedLibraryKeepsTheSystemPickerEscapeReachableWithoutConfirming() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        assumeTrue(InstrumentationRegistry.getArguments().getString("verifyDeniedPhotos") == "true")
        val permission = if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE
        assumeTrue(context.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED)
        compose.activityRule.scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT }
        var showing by mutableStateOf(true)
        var confirmed = 0
        var system = 0
        compose.setContent { ShinianTheme {
            if (showing) WechatPhotoPicker(9, onDismiss = { showing = false },
                onConfirm = { confirmed++; showing = false },
                onSystemPicker = { system++; showing = false })
        } }
        compose.waitUntil(15_000) { compose.onAllNodesWithTag("picker.permission").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("picker.done").assertIsNotEnabled()
        compose.onNodeWithTag("picker.systemPicker").assertIsDisplayed().assertIsEnabled()
        val output = File(context.getExternalFilesDir(null), "wechat-picker-screenshots").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try { File(output, "permission-denied.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { bitmap.recycle() }
        compose.onNodeWithTag("picker.systemPicker").performClick()
        compose.waitUntil(5_000) { system == 1 }
        compose.runOnIdle { assertEquals(0, confirmed) }
        compose.onNodeWithTag("picker.root").assertDoesNotExist()
    }
}
