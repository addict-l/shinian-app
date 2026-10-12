import SwiftUI

/// 选择人物页面只维护列表展示；添加、选择和删除意图通过回调交给流程容器处理。
struct JournalPersonSelectionView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @Binding var search: String
    let onSelect: (FamilyMember) -> Void
    let onDelete: (FamilyMember) -> Void
    let onAdd: () -> Void
    private var filteredPeople: [FamilyMember] {
        members.members.filter { search.isEmpty || "\($0.name) \($0.relationship)".localizedStandardContains(search) }
    }
    private var collection: [MemoryEvent] { FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                JournalEyebrow(lead: "新的回忆", trail: "02 选择人物")
                JournalTitle("今天，想起了谁？").padding(.top, 10)
                JournalSubtitle("选择一位家人，聊聊你们的故事。").padding(.top, 4)
                JournalSearch(prompt: "搜索姓名或家庭身份", text: $search).padding(.top, 16)
                if !members.members.isEmpty {
                    HStack(spacing: 6) {
                        DesignIcon("spark", size: 14).foregroundStyle(JournalTheme.accent)
                        Text("点击人物，即可开始 AI 对话。")
                    }.font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        .padding(.horizontal, 4).padding(.top, 14).padding(.bottom, 8)
                }
                LazyVStack(spacing: 10) {
                    ForEach(filteredPeople) { person in
                        JournalPersonRow(person: person, memoryCount: memories.hasLoaded ? collection.filter { $0.personIDs.contains(person.id) }.count : nil)
                            .journalSwipeDelete(
                                initiallyRevealed: JournalDemo.screen == "select" && person.relationship == "爸爸",
                                onSelect: { onSelect(person) },
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
                Button(action: onAdd) {
                    HStack(spacing: 6) {
                        DesignIcon("plus", size: 18)
                        Text("添加新的家庭人物").font(JournalTheme.font(15))
                    }
                    .foregroundStyle(JournalTheme.accentDeep)
                    .frame(maxWidth: .infinity).frame(height: 52)
                    .overlay { Capsule().strokeBorder(Color(hex: 0xE3C3AD), style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])) }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain).padding(.top, 12).padding(.bottom, 24)
                .accessibilityIdentifier("members.addAnother")
            }
            .padding(.horizontal, JournalTheme.gutter).padding(.top, 6)
        }
        .scrollIndicators(.hidden)
        .refreshable { await members.load() }
    }
}
