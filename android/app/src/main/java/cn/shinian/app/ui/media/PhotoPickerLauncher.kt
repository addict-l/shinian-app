package cn.shinian.app.ui.media

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController

/** Share the same gallery UI for narration, saved memories, covers, and local portraits. */
@Composable
fun rememberPhotoPicker(maxSelection: Int = 9, onSelected: (List<Uri>) -> Unit): () -> Unit {
    val maximum = maxSelection.coerceIn(1, 9)
    val receive by rememberUpdatedState(onSelected)
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    var visible by rememberSaveable { mutableStateOf(false) }
    val multiple = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(9)) { uris ->
        if (uris.isNotEmpty()) receive(uris.distinct().take(maximum))
    }
    val single = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) receive(listOf(uri))
    }
    if (visible) WechatPhotoPicker(maximum,
        onDismiss = { visible = false },
        onConfirm = { uris -> visible = false; if (uris.isNotEmpty()) receive(uris.distinct().take(maximum)) },
        onSystemPicker = {
            visible = false
            val request = PickVisualMediaRequest.Builder().setMediaType(ActivityResultContracts.PickVisualMedia.ImageOnly).setOrderedSelection(true)
            if (maximum == 1) single.launch(request.build())
            else multiple.launch(request.setMaxItems(maximum).build())
        })
    return remember(focus, keyboard) { { focus.clearFocus(); keyboard?.hide(); visible = true } }
}
