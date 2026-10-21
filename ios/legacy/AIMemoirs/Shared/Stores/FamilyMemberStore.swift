import SwiftUI

/// 全应用共用的人物状态源，由 App 创建并注入各页面；版本号防止旧查询覆盖新的增删结果。
@MainActor
final class FamilyMemberStore: ObservableObject {
    @Published private(set) var members: [FamilyMember] = []
    @Published private(set) var isLoading = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var isSaving = false
    @Published var errorMessage: String?
    private let api: any FamilyAPI
    private var mutationVersion = 0

    init(api: (any FamilyAPI)? = nil) { self.api = api ?? BackendRepository.shared }

    /// Ignore an older load response when a newer add/delete operation has started.
    func load() async {
        guard !isLoading, !isSaving else { return }
        isLoading = true
        let version = mutationVersion
        defer { isLoading = false }
        do {
            let loaded = try await api.members()
            if version == mutationVersion { members = loaded; hasLoaded = true; errorMessage = nil }
        } catch is CancellationError {
        } catch { errorMessage = error.localizedDescription }
    }

    @discardableResult
    func add(_ draft: FamilyMemberDraft) async -> FamilyMember? {
        guard !isSaving, draft.isValid() else { return nil }
        isSaving = true
        mutationVersion += 1
        defer { isSaving = false }
        do {
            let member = try await api.addMember(draft)
            members.removeAll { $0.id == member.id }
            members.append(member)
            errorMessage = nil
            return member
        } catch { errorMessage = error.localizedDescription; return nil }
    }

    @discardableResult
    func delete(_ member: FamilyMember) async -> Bool {
        guard !isSaving else { return false }
        isSaving = true
        mutationVersion += 1
        defer { isSaving = false }
        do {
            try await api.deleteMember(id: member.id)
            members.removeAll { $0.id == member.id }
            errorMessage = nil
            return true
        } catch { errorMessage = error.localizedDescription; return false }
    }
}
