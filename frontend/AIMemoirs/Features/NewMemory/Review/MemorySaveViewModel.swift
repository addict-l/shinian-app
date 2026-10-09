import SwiftUI

/// 保存草稿的独立状态；负责重复提交保护与保存错误，不控制页面导航。
@MainActor
final class MemorySaveViewModel: ObservableObject {
    @Published private(set) var isSaving = false
    @Published var errorMessage: String?
    private let api: any MemoryAPI

    init(api: (any MemoryAPI)? = nil) { self.api = api ?? BackendRepository.shared }

    func save(_ draft: GeneratedMemory) async -> Bool {
        guard !isSaving else { return false }
        isSaving = true; errorMessage = nil
        defer { isSaving = false }
        do {
            _ = try await api.save(draft); return true
        } catch is CancellationError {
            return false
        } catch {
            errorMessage = error.localizedDescription; return false
        }
    }
}
