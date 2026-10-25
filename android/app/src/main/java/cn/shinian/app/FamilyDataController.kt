package cn.shinian.app

import cn.shinian.app.data.BackendRepository
import cn.shinian.app.data.Memory
import cn.shinian.app.data.Person
import cn.shinian.app.data.AuthException
import cn.shinian.app.data.AuthErrorKind
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class FamilyState(
    val people: List<Person> = emptyList(),
    val memories: List<Memory> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
)

/** Account-bound family loading, shared by the Android view model and its regression tests. */
class FamilyDataController(private val scope: CoroutineScope) {
    private val mutableState = MutableStateFlow(FamilyState())
    val state = mutableState.asStateFlow()
    var repository: BackendRepository? = null
        private set
    private var refreshJob: Job? = null
    private var generation = 0L
    private var memoriesLoaded = false

    fun bind(value: BackendRepository?) {
        repository?.invalidate()
        cancelRefresh()
        repository = value
        memoriesLoaded = false
        mutableState.value = FamilyState()
    }

    fun refresh(): Job? {
        val captured = repository ?: return null
        cancelRefresh()
        val requestedGeneration = generation
        mutableState.update { it.copy(loading = true, error = null) }
        return scope.launch {
            try {
                val listing = captured.familyListing()
                val people = listing.people
                val memories = listing.memories
                if (repository !== captured || generation != requestedGeneration) return@launch
                memoriesLoaded = memoriesLoaded || memories.isSuccess
                mutableState.update { old ->
                    val retainedMemories = memories.getOrNull() ?: old.memories
                    val retainedPeople = people.getOrNull() ?: old.people
                    FamilyState(
                        people = if (memoriesLoaded) retainedPeople.map { person ->
                            person.copy(memoryCount = retainedMemories.count { person.id in it.personIds })
                        } else retainedPeople,
                        memories = retainedMemories,
                        error = listOfNotNull(people.exceptionOrNull()?.message, memories.exceptionOrNull()?.message)
                            .distinct().joinToString("\n").ifBlank { null },
                    )
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                if (repository === captured && generation == requestedGeneration) mutableState.update {
                    it.copy(loading = false, error = error.message ?: "读取失败，请重试。")
                }
            }
        }.also { refreshJob = it }
    }

    suspend fun deleteMember(personId: String) {
        val captured = requireRepository()
        captured.deleteMember(personId)
        if (repository !== captured) return
        cancelRefresh()
        mutableState.update { old ->
            val people = old.people.filterNot { it.id == personId }
            // The server unlinks a deleted person, but retains the family's saved stories.
            old.copy(people = people, memories = old.memories.map { memory ->
                val ids = memory.personIds.filterNot { it == personId }
                memory.copy(personIds = ids,
                    personName = ids.joinToString("、") { id -> people.firstOrNull { it.id == id }?.name ?: "家庭成员" },
                    primaryPersonId = memory.primaryPersonId?.takeUnless { it == personId })
            }, loading = false, error = null)
        }
    }

    suspend fun deleteMemory(memory: Memory) {
        val captured = requireRepository()
        captured.deleteMemory(memory)
        if (repository !== captured) return
        cancelRefresh()
        mutableState.update { old ->
            val memories = old.memories.filterNot { it.id == memory.id }
            old.copy(memories = memories, people = old.people.map { person ->
                person.copy(memoryCount = memories.count { person.id in it.personIds })
            }, loading = false, error = null)
        }
    }

    private fun requireRepository() = repository
        ?: throw AuthException(AuthErrorKind.Authentication, "登录已失效，请重新登录。")

    private fun cancelRefresh() {
        refreshJob?.cancel()
        generation++
    }

}
