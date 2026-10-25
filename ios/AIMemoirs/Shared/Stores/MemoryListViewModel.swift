import SwiftUI

// MARK: - Memory list state

/// 首页、人物、胶片及详情共用的回忆数据源，由 App 创建并注入。
/// 集中加载和筛选，避免多个页面分别持有无法同步的回忆副本。
@MainActor
final class MemoryListViewModel: ObservableObject {
    @Published private(set) var memoryEvents: [MemoryEvent] = []
    @Published private(set) var isLoading = false
    @Published private(set) var hasLoaded = false
    @Published var errorMessage: String?
    private let api: any MemoryAPI
    private var mutationVersion = 0

    init(api: (any MemoryAPI)? = nil) { self.api = api ?? BackendRepository() }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        let version = mutationVersion
        defer { isLoading = false }
        do {
            let events = try await api.list()
            try Task.checkCancellation()
            guard version == mutationVersion else { return }
            memoryEvents = events
            hasLoaded = true
        } catch is CancellationError {
        } catch { if version == mutationVersion { errorMessage = error.localizedDescription } }
    }

    func upsert(_ memory: MemoryEvent) {
        mutationVersion += 1
        memoryEvents.removeAll { $0.id == memory.id }; memoryEvents.append(memory)
    }
    func remove(id: UUID) { mutationVersion += 1; memoryEvents.removeAll { $0.id == id } }

    /// Only a confirmed server deletion and required local cleanup remove the story.
    func delete(_ memory: MemoryEvent, afterServerDelete: () throws -> Void) async throws {
        mutationVersion += 1
        try await api.deleteMemory(memory)
        try afterServerDelete()
        remove(id: memory.id)
    }

    /// The server unlinks a deleted person; retained and shared stories stay intact.
    func unlink(personID: UUID, remainingMembers: [FamilyMember]) {
        mutationVersion += 1
        memoryEvents = memoryEvents.map { $0.removing(personID: personID, remainingMembers: remainingMembers) }
    }

    func getMemoryEvents(for personID: UUID) -> [MemoryEvent] {
        getAllMemoryEvents().filter { $0.personIDs.contains(personID) }
    }

    func getAllMemoryEvents() -> [MemoryEvent] {
        memoryEvents.sorted { ($0.date ?? $0.createdAt) > ($1.date ?? $1.createdAt) }
    }
}
