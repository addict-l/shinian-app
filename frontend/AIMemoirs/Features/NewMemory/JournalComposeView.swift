import SwiftUI

/// 新回忆流程容器：协调添加人物、选择人物、聊天及保存后的刷新；各步骤的布局独立维护。
struct JournalComposeView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    let chatAPI: any ChatAPI
    let memoryAPI: any MemoryAPI
    let previewScreen: String?
    @State private var memberDraft = FamilyMemberDraft()
    @State private var search = ""
    @State private var seeded = false
    @State private var personPendingDelete: FamilyMember?
    var body: some View {
        Group {
            switch navigation.composeStep {
            case .add:
                JournalAddPersonView(draft: $memberDraft, loading: members.isSaving, error: members.errorMessage, onAdd: addMember,
                    onSelect: { navigation.composeStep = .select })
            case .select:
                JournalPersonSelectionView(search: $search, onSelect: { person in
                    navigation.person = person
                    navigation.composeStep = .chat
                }, onDelete: { personPendingDelete = $0 }, onAdd: { navigation.composeStep = .add })
            case .chat:
                if let person = navigation.person {
                    JournalChatView(person: person, chatAPI: chatAPI, memoryAPI: memoryAPI, previewScreen: previewScreen) {
                        navigation.composeStep = .select
                    } onSaved: {
                        await members.load(); await memories.load()
                        navigation.composeStep = .select
                        navigation.path.append(.person(person.id))
                    }.id(person.id)
                }
            }
        }
        .journalPage()
        .overlay {
            if let person = personPendingDelete {
                JournalFlatDeleteConfirm(
                    name: person.name,
                    onConfirm: {
                        personPendingDelete = nil
                        Task { if await members.delete(person) { await memories.load() } }
                    },
                    onCancel: { personPendingDelete = nil }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .transition(.opacity)
                .zIndex(50)
            }
        }
        .animation(.easeOut(duration: 0.2), value: personPendingDelete?.id)
        .task {
            #if DEBUG
            if previewScreen == "add", !seeded {
                seeded = true
                memberDraft = FamilyMemberDraft(realName: "陈建国", relationship: "爷爷", birthDate: APIDate.parseDay("1948-05-16"))
            }
            #endif
        }
    }
    private func addMember() {
        Task {
            guard await members.add(memberDraft) != nil else { return }
            memberDraft = FamilyMemberDraft(); search = ""; navigation.composeStep = .select
        }
    }
}
