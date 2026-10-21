package cn.shinian.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import cn.shinian.app.data.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class FamilyState(
    val people: List<Person> = emptyList(),
    val memories: List<Memory> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    val authentication = AuthController(AuthApi(), SessionStore(application), viewModelScope)
    val auth = authentication.state
    private val mutableFamily = MutableStateFlow(FamilyState())
    val family = mutableFamily.asStateFlow()
    var repository: BackendRepository? = null
        private set
    private var refreshJob: Job? = null
    private var refreshGeneration = 0L

    init {
        viewModelScope.launch {
            auth.map { it.session }.distinctUntilChanged().collectLatest { session ->
                repository?.invalidate()
                refreshJob?.cancel()
                refreshGeneration++
                repository = session?.let { saved -> BackendRepository(saved, onUnauthorized = { authentication.handleUnauthorized(saved) }) }
                mutableFamily.value = FamilyState()
                if (session != null) refresh()
            }
        }
        authentication.restore()
    }

    fun refresh() {
        val captured = repository ?: return
        refreshJob?.cancel()
        val generation = ++refreshGeneration
        mutableFamily.update { it.copy(loading = true, error = null) }
        refreshJob = viewModelScope.launch {
            try {
                val peopleTask = async { loadResult { captured.members() } }
                val memoriesTask = async { loadResult { captured.memories() } }
                val people = peopleTask.await()
                val memories = memoriesTask.await()
                if (repository !== captured || refreshGeneration != generation) return@launch
                mutableFamily.update { old -> FamilyState(
                    people = people.getOrNull() ?: old.people,
                    memories = memories.getOrNull() ?: old.memories,
                    error = listOfNotNull(people.exceptionOrNull()?.message, memories.exceptionOrNull()?.message).distinct().joinToString("\n").ifBlank { null },
                ) }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                if (repository === captured && refreshGeneration == generation) mutableFamily.update {
                    it.copy(loading = false, error = error.message ?: "读取失败，请重试。")
                }
            }
        }
    }

    private suspend fun <T> loadResult(block: suspend () -> T): Result<T> = try { Result.success(block()) }
    catch (cancelled: CancellationException) { throw cancelled }
    catch (error: Exception) { Result.failure(error) }
}
