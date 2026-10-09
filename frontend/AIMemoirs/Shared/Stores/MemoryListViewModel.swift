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

    init(api: (any MemoryAPI)? = nil) { self.api = api ?? BackendRepository.shared }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let events = try await api.list()
            try Task.checkCancellation()
            memoryEvents = events
            hasLoaded = true
        } catch is CancellationError {
        } catch { errorMessage = error.localizedDescription }
    }

    func getMemoryEvents(for personID: UUID) -> [MemoryEvent] {
        getAllMemoryEvents().filter { $0.personIDs.contains(personID) }
    }

    func getAllMemoryEvents() -> [MemoryEvent] {
        memoryEvents.sorted { ($0.date ?? $0.createdAt) > ($1.date ?? $1.createdAt) }
    }
}
