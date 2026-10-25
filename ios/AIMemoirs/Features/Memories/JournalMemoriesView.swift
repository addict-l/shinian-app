import SwiftUI

/// 回忆列表：管理本页搜索与人物筛选，数据来自根视图注入的共享状态。
struct JournalMemoriesView: View {
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var navigation: JournalNavigation
    @State private var search = ""
    @State private var selectedPerson: UUID?
    private var all: [MemoryEvent] { FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events }
    private var filtered: [MemoryEvent] {
        all.filter { event in
            (selectedPerson == nil || event.personIDs.contains(selectedPerson!)) &&
            (search.isEmpty || "\(event.title) \(event.content) \(event.personName)".localizedStandardContains(search))
        }.sorted { $0.createdAt > $1.createdAt }
    }
    /// 按故事年份从近到远分组，时间未知的放在最后。
    private var groups: [(year: Int?, events: [MemoryEvent])] {
        if JournalDemo.isPreview && selectedPerson == nil && search.isEmpty {
            let featured = ["葡萄架下的那把蒲扇", "那年的团圆饭", "爸爸扶着我学骑车", "妈妈的第一份工作"]
            let first = filtered.filter { featured.prefix(2).contains($0.title) }
            let second = filtered.filter { featured.suffix(2).contains($0.title) }
            let rest = filtered.filter { !featured.contains($0.title) }
            let grouped = Dictionary(grouping: rest, by: memoryYear)
            return [(2008, first), (1998, second)] + grouped.keys.sorted { ($0 ?? Int.min) > ($1 ?? Int.min) }.map { ($0, grouped[$0]!) }
        }
        let grouped = Dictionary(grouping: filtered, by: memoryYear)
        return grouped.keys.sorted { ($0 ?? Int.min) > ($1 ?? Int.min) }.map { ($0, grouped[$0]!) }
    }
    var body: some View {
        VStack(spacing: 0) {
            JournalBackBar()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    JournalTitle("所有回忆")
                    HStack(spacing: 0) {
                        Text("那些平凡日子里的，珍贵片刻。").foregroundStyle(JournalTheme.ink2)
                        if memories.hasLoaded { Text("　\(all.count) 段回忆").foregroundStyle(JournalTheme.accentDeep) }
                    }.font(JournalTheme.font(14)).padding(.top, 2)
                    JournalSearch(prompt: "搜索回忆、人物或一句话", text: $search).padding(.top, 14)
                    ScrollView(.horizontal) {
                        HStack(spacing: 8) {
                            filter("全部", id: nil)
                            ForEach(members.members) { person in filter(person.relationship.isEmpty ? person.name : person.relationship, id: person.id) }
                        }.padding(.vertical, 1)
                    }.scrollIndicators(.hidden).padding(.top, 12)
                    if memories.isLoading { ProgressView().frame(maxWidth: .infinity).padding(.top, 20) }
                    if let error = memories.errorMessage { JournalError(message: error) { Task { await memories.load() } }.padding(.top, 16) }
                    if filtered.isEmpty && !memories.isLoading {
                        JournalEmptyState(title: search.isEmpty ? "还没有回忆" : "没有找到相关回忆", message: search.isEmpty ? "从记录一段故事开始。" : "试试其他关键词，或者选择另一位家人。")
                    }
                    ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                        Text(group.year.map { "— " + String($0) + " 年" } ?? "— 时间待补充").font(JournalTheme.font(12)).tracking(1.2)
                            .foregroundStyle(JournalTheme.muted).padding(.horizontal, 4).padding(.top, 18).padding(.bottom, 10)
                        groupBody(group.events)
                    }
                }.padding(.horizontal, JournalTheme.gutter).padding(.bottom, 24)
            }
            .scrollIndicators(.hidden).refreshable { await memories.load() }
        }
        .journalPage()
    }

    @ViewBuilder private func groupBody(_ events: [MemoryEvent]) -> some View {
        let photos = events.filter { $0.hasPhoto }
        let paired = photos.count >= 2 ? Array(photos.prefix(photos.count / 2 * 2)) : []
        let single = photos.filter { item in !paired.contains { $0.id == item.id } }
        let quotes = events.filter { !$0.hasPhoto }
        VStack(spacing: 10) {
            if !paired.isEmpty {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
                    ForEach(paired) { gridCard($0) }
                }
            }
            ForEach(single) { rowCard($0) }
            ForEach(quotes) { quoteCard($0) }
        }
    }

    private func open(_ event: MemoryEvent) { navigation.path.append(.memory(event.id)) }

    /// “外婆 · 夏天”：分组已显示年份，副标题去掉年份前缀。
    private func seasonSubtitle(_ event: MemoryEvent) -> String {
        var label = event.dateLabel
        if let year = memoryYear(event), label.hasPrefix("\(year)年") { label = String(label.dropFirst("\(year)年".count)) }
        return [memoryRoles(event, members: members.members), label].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func gridCard(_ event: MemoryEvent) -> some View {
        Button { open(event) } label: {
            VStack(alignment: .leading, spacing: 0) {
                JournalPhoto(memory: event, height: 120, radius: 14)
                Text(JournalDemo.isPreview && event.title == "葡萄架下的那把蒲扇" ? "葡萄架下的蒲扇" : event.title).font(JournalTheme.story(15)).foregroundStyle(JournalTheme.ink).lineLimit(1)
                    .padding(.horizontal, 4).padding(.top, 10).padding(.bottom, 2)
                Text(seasonSubtitle(event)).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineLimit(1)
                    .padding(.horizontal, 4).padding(.bottom, 4)
            }.padding(8).frame(maxWidth: .infinity, alignment: .leading).journalCard()
        }.buttonStyle(.plain).accessibilityIdentifier("memory.card.\(event.id)")
    }

    private func rowCard(_ event: MemoryEvent) -> some View {
        Button { open(event) } label: {
            HStack(spacing: 12) {
                JournalPhoto(memory: event, height: 70, radius: 14).frame(width: 70)
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.title).font(JournalTheme.story(16)).foregroundStyle(JournalTheme.ink).lineLimit(1)
                    Text(event.content).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineSpacing(3).lineLimit(2)
                }
                Spacer(minLength: 0)
            }.padding(10).frame(maxWidth: .infinity, alignment: .leading).journalCard()
        }.buttonStyle(.plain).accessibilityIdentifier("memory.card.\(event.id)")
    }

    private func quoteCard(_ event: MemoryEvent) -> some View {
        Button { open(event) } label: {
            HStack(spacing: 12) {
                JournalIconTile(icon: "quote", fill: JournalTheme.sageSoft, ink: JournalTheme.sageInk, size: 44, radius: 14)
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.title).font(JournalTheme.story(16)).foregroundStyle(JournalTheme.ink).lineLimit(1)
                    Text(memorySubtitle(event, members: members.members)).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineLimit(1)
                }
                Spacer(minLength: 0)
            }.padding(14).frame(maxWidth: .infinity, alignment: .leading).journalCard()
        }.buttonStyle(.plain).accessibilityIdentifier("memory.card.\(event.id)")
    }

    private func filter(_ title: String, id: UUID?) -> some View {
        let selected = selectedPerson == id
        return Button { selectedPerson = id } label: {
            HStack(spacing: 5) {
                if let id, let person = members.members.first(where: { $0.id == id }) { JournalAvatar(person: person, size: 24) }
                Text(title).font(JournalTheme.font(13))
            }
            .foregroundStyle(selected ? .white : JournalTheme.ink2)
            .padding(.leading, id == nil ? 14 : 4).padding(.trailing, 14).frame(height: 32)
            .background(selected ? JournalTheme.accent : JournalTheme.surface, in: Capsule())
            .overlay { Capsule().stroke(selected ? JournalTheme.accent : JournalTheme.line, lineWidth: 1) }
        }.buttonStyle(.plain).accessibilityAddTraits(selected ? .isSelected : [])
    }
}
