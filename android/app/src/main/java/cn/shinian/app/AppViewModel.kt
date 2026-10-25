package cn.shinian.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import cn.shinian.app.data.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class AppViewModel(application: Application) : AndroidViewModel(application) {
    val authentication = AuthController(AuthApi(), SessionStore(application), viewModelScope)
    val auth = authentication.state
    private val familyData = FamilyDataController(viewModelScope)
    val family = familyData.state
    val repository: BackendRepository? get() = familyData.repository

    init {
        viewModelScope.launch {
            auth.map { it.session }.distinctUntilChanged().collectLatest { session ->
                familyData.bind(session?.let { saved -> BackendRepository(saved,
                    onUnauthorized = { authentication.handleUnauthorized(saved) }) })
                if (session != null) refresh()
            }
        }
        authentication.restore()
    }

    fun refresh() { familyData.refresh() }
    suspend fun deleteMember(personId: String) { familyData.deleteMember(personId) }
    suspend fun deleteMemory(memory: Memory) { familyData.deleteMemory(memory) }
}
