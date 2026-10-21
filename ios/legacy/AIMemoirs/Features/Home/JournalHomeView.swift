import SwiftUI

/// 首页：展示最近回忆，并提供记录和浏览入口。
struct JournalHomeView: View {
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var navigation: JournalNavigation
    @State private var viewportHeight: CGFloat = 0
    @State private var headerHeight: CGFloat = 0
    private var events: [MemoryEvent] {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents)
            .events.sorted { $0.createdAt > $1.createdAt }
    }
    private var loadError: String? { members.errorMessage ?? memories.errorMessage }
    private var ready: Bool { members.hasLoaded && memories.hasLoaded }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                JournalHeader(kicker: "拾年     /     \(Date().formatted(.dateTime.weekday(.wide).locale(Locale(identifier: "zh_CN"))))", title: "把平凡，留成永远。", subtitle: "有些瞬间，值得被好好记住。")
                    .padding(.bottom, 28)
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { headerHeight = $0 }
                if let first = events.first {
                    Button { navigation.path.append(.memory(first.id)) } label: {
                        VStack(alignment: .leading, spacing: 0) {
                            JournalPhoto(memory: first, height: 255, radius: 20)
                            Text(first.title).font(JournalTheme.story(23)).foregroundStyle(JournalTheme.ink)
                                .padding(.top, 22).fixedSize(horizontal: false, vertical: true)
                            Text(memorySubtitle(first, members: members.members)).font(JournalTheme.font(12))
                                .foregroundStyle(JournalTheme.muted).padding(.top, 7)
                        }
                    }.buttonStyle(.plain).accessibilityIdentifier("home.featured")
                    JournalTheme.line.frame(height: 1).padding(.top, 23).padding(.bottom, 24)
                    HStack {
                        Text("最近的回忆").font(JournalTheme.font(17, medium: true))
                        Spacer()
                        Button("查看全部  ›") { navigation.path.append(.memories) }.font(JournalTheme.font(12))
                            .foregroundStyle(JournalTheme.accent)
                            .accessibilityIdentifier("home.allMemories")
                    }.padding(.bottom, 16)
                    if let recent = events.dropFirst().first {
                        Button { navigation.path.append(.memory(recent.id)) } label: {
                            VStack(alignment: .leading, spacing: 7) {
                                Text(recent.title).font(JournalTheme.font(16, medium: true)).foregroundStyle(JournalTheme.ink).lineLimit(2)
                                Text(memorySubtitle(recent, members: members.members)).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                                .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                        }.buttonStyle(.plain)
                    }
                } else if loadError != nil {
                    JournalEmptyState(title: "暂时没能打开回忆", message: "故事还在，稍后再试一次。")
                } else if !ready {
                    ProgressView("正在打开回忆…").frame(maxWidth: .infinity).padding(.vertical, 100)
                } else {
                    JournalHomeEmptyView(hasPeople: !members.members.isEmpty,
                        minimumHeight: max(0, viewportHeight - headerHeight - 24)) {
                        navigation.compose(step: members.members.isEmpty ? .add : .select)
                    }
                }
                if let error = loadError {
                    JournalError(message: error) { Task { await members.load(); await memories.load() } }.padding(.top, 16)
                }
                if !events.isEmpty {
                    JournalButton(title: "＋  记录一段回忆") { navigation.compose() }
                        .padding(.top, 30).padding(.bottom, 40).accessibilityIdentifier("home.newMemory")
                }
            }.padding(.horizontal, JournalTheme.gutter)
        }
        .scrollIndicators(.hidden).refreshable { await members.load(); await memories.load() }.journalPage()
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { viewportHeight = $0 }
    }
}
