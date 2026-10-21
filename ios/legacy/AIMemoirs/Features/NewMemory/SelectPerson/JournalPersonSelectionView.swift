import SwiftUI

/// 选择人物页面只维护列表展示；添加、选择和删除意图通过回调交给流程容器处理。
struct JournalPersonSelectionView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @Binding var search: String
    let onSelect: (FamilyMember) -> Void
    let onDelete: (FamilyMember) -> Void
    let onAdd: () -> Void
    private var filteredPeople: [FamilyMember] {
        members.members.filter { search.isEmpty || "\($0.name) \($0.relationship)".localizedStandardContains(search) }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                JournalHeader(kicker: "新的回忆     /     02 选择人物", title: "今天，想起了谁？", subtitle: "选择一位家人，聊聊你们的故事。")
                    .padding(.bottom, 30)
                JournalSearch(prompt: "搜索姓名或家庭身份", text: $search).padding(.bottom, 23)
                LazyVStack(spacing: 12) {
                    ForEach(filteredPeople) { person in
                        JournalPersonRow(person: person)
                            .journalSwipeDelete(
                                onSelect: {
                                    onSelect(person)
                                },
                                onDelete: { onDelete(person) }
                            )
                    }
                }
                if members.isLoading { ProgressView().frame(maxWidth: .infinity).padding(32) }
                if members.members.isEmpty && !members.isLoading {
                    JournalEmptyState(title: "先添加一位家人", message: "家人的名字，会出现在这里。")
                } else if !search.isEmpty && filteredPeople.isEmpty {
                    JournalEmptyState(title: "没有找到这位家人", message: "试试真实姓名或家庭身份。")
                }
                if let error = members.errorMessage { JournalError(message: error) { Task { await members.load() } }.padding(.top, 12) }
                JournalButton(title: "＋  添加新的家庭人物", secondary: true) { onAdd() }
                    .padding(.top, 34).accessibilityIdentifier("members.addAnother")
                Text("点击人物，即可开始 AI 对话。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    .frame(maxWidth: .infinity).padding(.top, 25).padding(.bottom, 24)
            }
            .padding(.horizontal, 24)
        }
        .scrollIndicators(.hidden)
        .refreshable { await members.load() }
    }
}
