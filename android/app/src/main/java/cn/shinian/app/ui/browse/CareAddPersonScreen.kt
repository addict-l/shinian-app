package cn.shinian.app.ui.browse

import android.content.res.Configuration
import android.os.Build
import android.view.ContextThemeWrapper
import android.view.View
import android.view.ViewGroup
import android.widget.DatePicker as AndroidDatePicker
import android.widget.NumberPicker
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.text.input.ImeAction
import cn.shinian.app.R
import cn.shinian.app.ui.care.*
import cn.shinian.app.ui.chat.MandarinDictation
import cn.shinian.app.ui.care.CareTypography as T
import java.time.LocalDate
import java.time.ZoneId
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CareAddPersonScreen(loading: Boolean, error: String?, onAdd: (String, String, String) -> Unit, onBack: () -> Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    var relationship by rememberSaveable { mutableStateOf("") }
    var birthday by rememberSaveable { mutableStateOf<String?>(null) }
    var choosingBirthday by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    val focus = LocalFocusManager.current
    val nameRequester = remember { FocusRequester() }
    var relationshipFocused by remember { mutableStateOf(false) }
    var nameFocused by remember { mutableStateOf(false) }
    val dictation = remember { MandarinDictation(context.applicationContext) { name = it } }
    val mic = rememberCareMicrophone(dictation, "")
    val valid = name.isNotBlank() && relationship.isNotBlank() && birthday?.let {
        runCatching { !LocalDate.parse(it).isAfter(LocalDate.now()) }.getOrDefault(false)
    } == true
    fun submit() { if (valid && !loading && !dictation.busy) { focus.clearFocus(); dictation.cancel(); onAdd(name.trim(), relationship.trim(), birthday!!) } }
    Box(Modifier.fillMaxSize()) {
    CarePage {
        CareToolbar("添加家人", onBack, enabled = !loading)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
            Box(Modifier.padding(bottom = 4.dp)) { CareHeading("先记下家人的名字", "这些资料，之后也可以修改。") }
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                CareAddFieldLabel("怎么称呼这位家人", "users")
                BoxWithConstraints(Modifier.fillMaxWidth()) {
                    val columns = ((maxWidth.value + 10f) / 82f).toInt().coerceAtLeast(1)
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        listOf("爷爷", "奶奶", "外公", "外婆", "爸爸", "妈妈").chunked(columns).forEach { row ->
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                row.forEach { role ->
                                    val chosen = relationship == role
                                    Box(Modifier.weight(1f).clip(RoundedCornerShape(18.dp))
                                        .background(if (chosen) CareColors.Accent else CareColors.Surface)
                                        .border(1.5.dp, if (chosen) CareColors.Accent else CareColors.Border, RoundedCornerShape(18.dp))
                                        .clickable(enabled = !loading, role = Role.Button) { relationship = role; focus.clearFocus() }
                                        .heightIn(min = 64.dp).padding(horizontal = 8.dp, vertical = 4.dp)
                                        .testTag("member.role.$role").semantics { selected = chosen }, contentAlignment = Alignment.Center) {
                                        Text(role, style = T.body(24, chosen), color = if (chosen) Color.White else CareColors.Ink)
                                    }
                                }
                                repeat(columns - row.size) { Spacer(Modifier.weight(1f)) }
                            }
                        }
                    }
                }
                val relationshipShape = RoundedCornerShape(22.dp)
                BasicTextField(relationship, { relationship = it }, Modifier.fillMaxWidth()
                    .background(CareColors.Surface, relationshipShape)
                    .border(if (relationshipFocused) 2.dp else 1.5.dp, if (relationshipFocused) CareColors.Accent else CareColors.Border, relationshipShape)
                    .onFocusChanged { relationshipFocused = it.isFocused }.heightIn(min = 64.dp).padding(horizontal = 18.dp, vertical = 16.dp)
                    .testTag("member.relationship").semantics { contentDescription = "怎么称呼这位家人" },
                    enabled = !loading, textStyle = T.body(22).copy(color = CareColors.Ink), minLines = 1, maxLines = 2,
                    cursorBrush = SolidColor(CareColors.Accent), keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                    keyboardActions = KeyboardActions(onNext = { nameRequester.requestFocus() }), decorationBox = { inner ->
                        Box(contentAlignment = Alignment.CenterStart) {
                            if (relationship.isEmpty()) Text("也可以自己写，例如姑姑、舅舅", style = T.body(22), color = Color(0xFFC7C7CC))
                            inner()
                        }
                    })
            }
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                CareAddFieldLabel("真实姓名", "person")
                val nameShape = RoundedCornerShape(22.dp)
                Row(Modifier.fillMaxWidth().background(CareColors.Surface, nameShape)
                    .border(if (nameFocused || dictation.busy) 2.dp else 1.5.dp, if (nameFocused || dictation.busy) CareColors.Accent else CareColors.Border, nameShape)
                    .padding(start = 18.dp, end = 8.dp, top = 10.dp, bottom = 10.dp).heightIn(min = 48.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BasicTextField(name, { name = it }, Modifier.weight(1f).focusRequester(nameRequester).onFocusChanged { nameFocused = it.isFocused }
                        .testTag("member.realName").semantics { contentDescription = "真实姓名" },
                        enabled = !loading && !dictation.busy, textStyle = T.body(24).copy(color = CareColors.Ink), singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done), keyboardActions = KeyboardActions(onDone = { focus.clearFocus() }),
                        cursorBrush = SolidColor(CareColors.Accent), decorationBox = { inner -> Box(contentAlignment = Alignment.CenterStart) {
                            if (name.isEmpty()) Text("填写家人的姓名", style = T.body(24), color = Color(0xFFC7C7CC)); inner()
                        } })
                    IconButton({ focus.clearFocus(); mic() }, enabled = !loading && dictation.phase != MandarinDictation.Phase.Finishing,
                        modifier = Modifier.size(48.dp).testTag("member.nameDictation")) {
                        CareSymbol(if (dictation.busy) "stopCircle" else "mic", 25.dp, if (dictation.busy) "停止姓名语音输入" else "语音填写姓名", tint = CareColors.Accent)
                    }
                }
                if (dictation.busy) Text(dictation.status, style = T.body(18), color = CareColors.Accent)
            }
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                CareAddFieldLabel("生日", "cal")
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(CareColors.Surface)
                    .border(1.5.dp, CareColors.Border, RoundedCornerShape(22.dp))
                    .clickable(enabled = !loading, role = Role.Button) { focus.clearFocus(); dictation.cancel(); choosingBirthday = true }
                    .heightIn(min = 68.dp).padding(18.dp).testTag("member.birthday"),
                    horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(birthday?.displayDay() ?: "选择家人的生日", style = T.body(22), color = if (birthday == null) CareColors.SecondaryInk else CareColors.Ink,
                        modifier = Modifier.weight(1f))
                    CareSymbol("cal", 25.dp, tint = CareColors.Accent)
                }
            }
            error?.let { CareError(it) }
        }
        CareDock {
            CareButton("添加并开始讲述", icon = "check", enabled = valid && !dictation.busy, loading = loading,
                modifier = Modifier.testTag("member.add"), onClick = ::submit)
        }
    }
    if (loading) CareBusyOverlay("正在添加…")
    }
    if (choosingBirthday) {
        CareBirthdaySheet(birthday, onCancel = { choosingBirthday = false }) { date -> birthday = date; choosingBirthday = false }
    }
    dictation.error?.let { message -> AlertDialog(onDismissRequest = { dictation.error = null }, title = { Text("语音输入") }, text = { Text(message) },
        confirmButton = { TextButton({ dictation.error = null }) { Text("确定") } }) }
}

@Composable
private fun CareAddFieldLabel(title: String, icon: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.semantics { heading() }) {
        CareSymbol(icon, 24.dp, tint = CareColors.Accent)
        Text(title, style = T.body(21, true), color = CareColors.Ink)
    }
}

/** An in-app wheel sheet. Its theme and locale never change device settings. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CareBirthdaySheet(birthday: String?, onCancel: () -> Unit, onConfirm: (String) -> Unit) {
    var selectedDate by remember { mutableStateOf(LocalDate.parse(birthday ?: "1950-01-01")) }
    val context = LocalContext.current
    val density = LocalDensity.current
    val configuration = LocalConfiguration.current
    val screenHeight = configuration.screenHeightDp.dp
    val pickerContext = remember(context, configuration) {
        val localized = context.createConfigurationContext(Configuration(configuration).apply { setLocale(Locale.SIMPLIFIED_CHINESE) })
        ContextThemeWrapper(localized, R.style.CareBirthdayPicker)
    }
    val textSize = with(density) { 22.dp.toPx() }
    val dividerHeight = with(density) { 1.dp.roundToPx() }
    ModalBottomSheet(onDismissRequest = onCancel, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp), containerColor = CareColors.Surface,
        dragHandle = null, contentWindowInsets = { WindowInsets(0, 0, 0, 0) }) {
        Column(Modifier.fillMaxWidth().height((screenHeight * .5f).coerceAtLeast(360.dp)).navigationBarsPadding()) {
            Row(Modifier.fillMaxWidth().heightIn(min = 58.dp).padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onCancel, Modifier.width(64.dp).heightIn(min = 48.dp)) { Text("取消", style = T.body(17), color = CareColors.Accent) }
                Text("家人的生日", Modifier.weight(1f), style = T.body(17, true), color = CareColors.Ink, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                TextButton({ onConfirm(selectedDate.toString()) }, enabled = !selectedDate.isAfter(LocalDate.now()),
                    modifier = Modifier.width(64.dp).heightIn(min = 48.dp).testTag("member.confirmBirthday")) {
                    Text("确定", style = T.body(17, true), color = CareColors.Accent)
                }
            }
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                AndroidView(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp), factory = {
                    AndroidDatePicker(pickerContext).apply {
                        calendarViewShown = false
                        spinnersShown = true
                        maxDate = LocalDate.now().plusDays(1).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli() - 1
                        setBackgroundColor(android.graphics.Color.TRANSPARENT)
                        init(selectedDate.year, selectedDate.monthValue - 1, selectedDate.dayOfMonth) { _, year, month, day ->
                            selectedDate = LocalDate.of(year, month + 1, day)
                        }
                        careStyleDateWheels(this, textSize, dividerHeight)
                    }
                })
            }
        }
    }
}

private fun careStyleDateWheels(view: View, textSize: Float, dividerHeight: Int) {
    if (view is NumberPicker && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        view.textColor = CareColors.Ink.toArgb()
        view.textSize = textSize
        view.selectionDividerHeight = dividerHeight
    }
    if (view is ViewGroup) for (index in 0 until view.childCount) careStyleDateWheels(view.getChildAt(index), textSize, dividerHeight)
}
