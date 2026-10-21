import SwiftUI

/// 回忆列表：管理本页搜索与人物筛选，数据来自根视图注入的共享状态。
struct JournalMemoriesView: View {
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var navigation: JournalNavigation
    @State private var search = ""
    @State private var selectedPerson: UUID?
    private var filtered: [MemoryEvent] {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events.filter { event in
            (selectedPerson == nil || event.personIDs.contains(selectedPerson!)) &&
            (search.isEmpty || "\(event.title) \(event.content) \(event.personName)".localizedStandardContains(search))
        }.sorted { $0.createdAt > $1.createdAt }
    }
    private var months: [String] { Array(Set(filtered.map { JournalFormat.month($0.createdAt) })).sorted(by: >) }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                JournalHeader(kicker: "OUR STORIES", title: "所有回忆", subtitle: "那些平凡日子里的，珍贵片刻。")
                    .padding(.bottom, 10)
                JournalSearch(prompt: "搜索回忆、人物或一句话", text: $search)
                ScrollView(.horizontal) {
                    HStack(spacing: 12) {
                        filter("全部", id: nil)
                        ForEach(members.members) { person in filter(person.relationship.isEmpty ? person.name : person.relationship, id: person.id) }
                    }
                }.scrollIndicators(.hidden)
                if memories.isLoading { ProgressView().frame(maxWidth: .infinity) }
                if let error = memories.errorMessage { JournalError(message: error) { Task { await memories.load() } } }
                if filtered.isEmpty && !memories.isLoading {
                    JournalEmptyState(title: search.isEmpty ? "还没有回忆" : "没有找到相关回忆", message: search.isEmpty ? "从记录一段故事开始。" : "试试其他关键词，或者选择另一位家人。")
                }
                ForEach(months, id: \.self) { month in
                    let events = filtered.filter { JournalFormat.month($0.createdAt) == month }
                    HStack {
                        Text(month).font(JournalTheme.font(13, medium: true)); Spacer()
                        Text("\(events.count) 段回忆").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }.padding(.top, 15)
                    ForEach(events) { event in
                        JournalMemoryCard(memory: event, subtitle: memorySubtitle(event, members: members.members)) { navigation.path.append(.memory(event.id)) }
                    }
                }
            }.padding(.horizontal, 24).padding(.bottom, 24)
        }
        .scrollIndicators(.hidden).refreshable { await memories.load() }.journalPage()
        .navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.hidden, for: .navigationBar)
    }
    private func filter(_ title: String, id: UUID?) -> some View {
        Button { selectedPerson = id } label: {
            Text(title).font(JournalTheme.font(13)).foregroundStyle(selectedPerson == id ? JournalTheme.accent : JournalTheme.muted)
                .padding(.horizontal, 22).frame(height: 34)
                .background(selectedPerson == id ? JournalTheme.soft : .clear, in: Capsule())
        }.buttonStyle(.plain).accessibilityAddTraits(selectedPerson == id ? .isSelected : [])
    }
}
