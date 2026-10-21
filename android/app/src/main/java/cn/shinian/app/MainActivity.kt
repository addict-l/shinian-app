package cn.shinian.app

import android.os.Bundle
import android.content.Context
import android.content.res.Configuration
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.SystemBarStyle
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.saveable.SaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cn.shinian.app.data.*
import cn.shinian.app.ui.auth.*
import cn.shinian.app.ui.browse.*
import cn.shinian.app.ui.chat.ChatScreen
import cn.shinian.app.ui.chat.invalidateChatAfterMemoryChange
import cn.shinian.app.ui.memoir.MemoirScreen
import cn.shinian.app.ui.theme.*
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import java.util.UUID
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun attachBaseContext(newBase: Context) {
        val configuration = Configuration(newBase.resources.configuration).apply { setLocale(Locale.SIMPLIFIED_CHINESE) }
        super.attachBaseContext(newBase.createConfigurationContext(configuration))
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        applyShinianWindowPolicy(window)
        setContent {
            ShinianTheme {
                ShinianImmersiveWindow()
                Box(Modifier.fillMaxSize().background(JournalColors.Paper)
                    .windowInsetsPadding(WindowInsets.displayCutout.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))) {
                    ShinianApplication()
                }
            }
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) applyShinianWindowPolicy(window)
    }
}

@Composable
private fun ShinianApplication(model: AppViewModel = viewModel()) {
    val auth by model.auth.collectAsStateWithLifecycle()
    val family by model.family.collectAsStateWithLifecycle()
    val session = auth.session
    if (session == null) {
        AuthScreen(
            state = AuthUiState(auth.loading, auth.error, auth.restoring),
            onLogin = model.authentication::login,
            onRegister = model.authentication::register,
            onClearError = model.authentication::clearError,
        )
        return
    }
    val repository = model.repository?.takeIf { it.session.token == session.token && it.session.server == session.server }
    if (repository == null) { Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }; return }
    key(session.scopeKey) {
        val context = LocalContext.current
        val preferences = remember { context.getSharedPreferences("journal_preferences", 0) }
        var care by rememberSaveable { mutableStateOf(preferences.getBoolean("care", false)) }
        var displayName by rememberSaveable(session.scopeKey) { mutableStateOf(preferences.getString("display_name.${session.scopeKey}", "回忆的收藏者") ?: "回忆的收藏者") }
        var tab by rememberSaveable { mutableStateOf(0) }
        var route by rememberSaveable { mutableStateOf("") }
        var previousRoute by rememberSaveable { mutableStateOf("") }
        var personParentRoute by rememberSaveable { mutableStateOf("") }
        val pages = rememberSaveableStateHolder()
        var selectedPersonId by rememberSaveable { mutableStateOf<String?>(null) }
        var selectedMemoryId by rememberSaveable { mutableStateOf<String?>(null) }
        var directMemory by remember { mutableStateOf<Memory?>(null) }
        var directPerson by remember { mutableStateOf<Person?>(null) }
        var actionError by remember { mutableStateOf<String?>(null) }
        var actionBusy by remember { mutableStateOf(false) }
        var pendingAddId by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
        var pendingAddPayload by rememberSaveable { mutableStateOf("") }
        val scope = rememberCoroutineScope()
        val person = family.people.firstOrNull { it.id == selectedPersonId } ?: directPerson?.takeIf { it.id == selectedPersonId }
        val knownMemory = family.memories.firstOrNull { it.id == selectedMemoryId }
        val memory = directMemory?.takeIf { it.id == selectedMemoryId && it.version >= (knownMemory?.version ?: 0) } ?: knownMemory
        fun openMemory(value: Memory) { previousRoute = route; directMemory = value; selectedMemoryId = value.id; route = "memory" }
        fun openPerson(value: Person) { personParentRoute = route; selectedPersonId = value.id; route = "person" }
        suspend fun refreshChatCache(source: String? = null) {
            try { invalidateChatAfterMemoryChange(context, session.scopeKey, source) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                android.widget.Toast.makeText(context, "云端已保存修改，本机聊天记录将在下次打开时重新核对。", android.widget.Toast.LENGTH_LONG).show()
            }
        }
        fun compose(value: Person? = null) {
            selectedPersonId = value?.id; tab = 1
            route = if (value != null) "chat" else if (family.people.isEmpty() && !family.loading && family.error == null) "add" else ""
        }
        fun changeCare(enabled: Boolean) { preferences.edit().putBoolean("care", enabled).apply(); care = enabled; route = ""; tab = 0 }
        fun back() {
            actionError = null
            route = when (route) {
                "editor" -> "memory"
                "memory" -> previousRoute.takeIf { it !in listOf("memory", "editor") } ?: ""
                "memoir" -> "person"
                "person" -> personParentRoute
                else -> ""
            }
        }
        BackHandler(route.isNotEmpty() && route != "chat") { back() }
        BackHandler(route.isEmpty() && tab != 0) { tab = 0 }
        val showTabs = if (care) route.isEmpty() && tab != 1 else route.isEmpty() || route in listOf("person", "memories", "family-all")
        ProvideBrowseEnvironment(repository) {
        JournalBackdrop(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize()) {
                Box(Modifier.weight(1f).then(if (!showTabs && route !in listOf("chat", "memoir")) Modifier.navigationBarsPadding() else Modifier)) {
                    KeepBrowsePageState(pages, "$care.$tab.$route.${if (route in listOf("person", "memoir", "chat")) selectedPersonId else if (route in listOf("memory", "editor")) selectedMemoryId else ""}", route.isEmpty() || route in listOf("person", "family-all", "memories")) {
                    when (route) {
                        "chat" -> if (person != null) ChatScreen(person, repository, care, onBack = { route = "" }, onSaved = { model.refresh() }, onHome = { route = ""; tab = 0 })
                            else MissingContent("人物暂时无法读取", model::refresh) { route = "" }
                        "add" -> AddPersonScreen(actionBusy, actionError, care, onAdd = { name, relationship, birthDate ->
                            if (!actionBusy) {
                                val payload = listOf(name.trim(), relationship.trim(), birthDate).joinToString("\n")
                                if (payload != pendingAddPayload) { pendingAddId = UUID.randomUUID().toString(); pendingAddPayload = payload }
                                actionBusy = true; actionError = null
                                scope.launch {
                                    try {
                                        val value = repository.addMember(name, relationship, birthDate, pendingAddId)
                                        pendingAddId = UUID.randomUUID().toString()
                                        directPerson = value; selectedPersonId = value.id; model.refresh(); tab = 1; route = "chat"
                                    } catch (e: Exception) { actionError = e.message }
                                    finally { actionBusy = false }
                                }
                            }
                        }, onBack = { route = "" })
                        "person" -> if (person != null) PersonDetailScreen(person, family.memories, care, session.scopeKey,
                            onBack = { route = personParentRoute }, onMemory = ::openMemory, onCompose = { compose(person) }, onMemoir = { route = "memoir" })
                            else MissingContent("人物暂时无法读取", model::refresh) { route = "" }
                        "memories" -> MemoriesScreen(family.people, family.memories, family.loading, family.error, care, false,
                            onBack = { route = "" }, onMemory = ::openMemory, onCompose = { compose() }, onRefresh = model::refresh)
                        "family-all" -> FamilyFilmScreen(family.people, family.memories, family.loading, family.error, care, true, session.scopeKey,
                            onRefresh = model::refresh, onPerson = ::openPerson, onMemory = ::openMemory, onAdd = ::compose, onAllPeople = { route = "" })
                        "memory" -> if (memory != null) MemoryDetailScreen(memory, family.people, repository, care,
                            onBack = ::back, onHome = { route = ""; tab = 0 }, onEdit = { directMemory = it; route = "editor" }, onDeleted = {
                                scope.launch {
                                    refreshChatCache(memory.sourceSessionId)
                                    route = ""; directMemory = null; model.refresh()
                                }
                            })
                            else MissingContent("回忆暂时无法读取", model::refresh, ::back)
                        "editor" -> if (memory != null) MemoryEditorScreen(memory, repository, care, onBack = ::back, onSaved = {
                            val updated = it
                            scope.launch {
                                refreshChatCache()
                                directMemory = updated; model.refresh(); route = "memory"
                            }
                        }) else MissingContent("回忆暂时无法读取", model::refresh, ::back)
                        "memoir" -> if (person != null) MemoirScreen(person, repository, care, onBack = { route = "person" })
                            else MissingContent("人物暂时无法读取", model::refresh, ::back)
                        "settings" -> SettingsScreen(displayName, care, auth.loading, auth.error,
                            onDisplayNameChange = { value -> displayName = value; preferences.edit().putString("display_name.${session.scopeKey}", value).apply() },
                            onCareChange = ::changeCare, onLogout = model.authentication::logout, onBack = { route = "" })
                        "privacy" -> PrivacyScreen(care, onBack = { route = "" })
                        else -> when (tab) {
                            0 -> HomeScreen(family.people, family.memories, family.loading, family.error, care,
                                onRefresh = model::refresh, onNewMemory = { compose() }, onAllMemories = { route = "memories" }, onMemory = ::openMemory, onProfile = { tab = 3 })
                            1 -> PersonSelectionScreen(family.people, family.loading || actionBusy, actionError ?: family.error, care,
                                onSelect = { compose(it) }, onAdd = { route = "add" }, onDelete = { value ->
                                    if (!actionBusy) {
                                        actionBusy = true; actionError = null
                                        scope.launch {
                                            try { repository.deleteMember(value.id); model.refresh() }
                                            catch (e: Exception) { actionError = e.message }
                                            finally { actionBusy = false }
                                        }
                                    }
                                }, onRefresh = model::refresh, onBack = { tab = 0 })
                            2 -> if (care) MemoriesScreen(family.people, family.memories, family.loading, family.error, true, true,
                                onBack = { tab = 0 }, onMemory = ::openMemory, onCompose = { compose() }, onRefresh = model::refresh)
                                else FamilyFilmScreen(family.people, family.memories, family.loading, family.error, false, false, session.scopeKey,
                                    onRefresh = model::refresh, onPerson = ::openPerson, onMemory = ::openMemory, onAdd = ::compose, onAllPeople = { route = "family-all" })
                            else -> ProfileScreen(family.people, family.memories, session.scopeKey, displayName, care,
                                onAllMemories = { route = "memories" }, onFamily = { if (care) route = "family-all" else tab = 1 }, onSettings = { route = "settings" },
                                onPrivacy = { route = "privacy" }, onCareChange = ::changeCare)
                        }
                    }
                    }
                }
                if (showTabs) JournalBottomBar(tab, care) { tab = it; route = ""; actionError = null }
            }
        }
        }
    }
}

@Composable
private fun KeepBrowsePageState(holder: SaveableStateHolder, stateKey: String, retain: Boolean, content: @Composable () -> Unit) {
    if (retain) holder.SaveableStateProvider(stateKey, content) else key(stateKey) { content() }
}

@Composable
private fun MissingContent(message: String, onRetry: () -> Unit, onBack: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Text(message); TextButton(onClick = onRetry) { Text("重新读取") }; TextButton(onClick = onBack) { Text("返回") }
    }
}

@Composable
private fun JournalBottomBar(selected: Int, care: Boolean, onSelect: (Int) -> Unit) {
    val tabs = if (care) listOf(0, 2, 3) else listOf(0, 1, 2, 3)
    val titles = if (care) listOf("首页", "回忆", "更多") else listOf("首页", "新的回忆", "家庭胶片", "我的")
    Surface(
        modifier = Modifier.navigationBarsPadding().padding(horizontal = if (care) 0.dp else 16.dp, vertical = 8.dp)
            .shadow(if (care) 0.dp else 8.dp, CircleShape),
        shape = if (care) RoundedCornerShape(0.dp) else CircleShape,
        color = JournalColors.Surface,
        border = BorderStroke(1.dp, JournalColors.Line),
    ) {
        Row(Modifier.fillMaxWidth().heightIn(min = if (care) 82.dp else 66.dp)) {
            titles.forEachIndexed { index, title ->
                val tab = tabs[index]
                val color = if (selected == tab) JournalColors.AccentDeep else JournalColors.SecondaryInk
                Column(Modifier.weight(1f).clickable { onSelect(tab) }.padding(vertical = 12.dp).testTag("tab.$tab"),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    JournalIcon(listOf("home", "plus", "film", "person")[tab], tint = color, modifier = Modifier.size(if (care) 28.dp else 23.dp))
                    Text(title, color = color, style = JournalTypography.body(if (care) 18 else 11, selected == tab))
                }
            }
        }
    }
}
