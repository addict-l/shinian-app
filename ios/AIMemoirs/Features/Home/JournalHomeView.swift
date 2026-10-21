import SwiftUI

/// 首页：展示最近回忆，并提供记录和浏览入口。
struct JournalHomeView: View {
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var navigation: JournalNavigation
    private var events: [MemoryEvent] {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents)
            .events.sorted { $0.createdAt > $1.createdAt }
    }
    private var loadError: String? { members.errorMessage ?? memories.errorMessage }
    private var ready: Bool { members.hasLoaded && memories.hasLoaded }
    private var weekday: String { Date().formatted(.dateTime.weekday(.wide).locale(Locale(identifier: "zh_CN"))) }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    JournalEyebrow(lead: "拾年", trail: weekday, accentLead: true)
                    Spacer()
                    if !events.isEmpty {
                        Button { navigation.tab = .profile } label: { JournalUserAvatar(size: 38) }
                            .buttonStyle(.plain).accessibilityLabel("我的")
                    }
                }.frame(minHeight: events.isEmpty && ready ? 17 : 38)
                JournalTitle("把平凡，\n留成永远。").padding(.top, 14)
                if !events.isEmpty || !ready || loadError != nil {
                    JournalSubtitle("有些瞬间，值得被好好记住。").padding(.top, 6)
                }
                if let first = events.first {
                    invitation.padding(.top, 20)
                    JournalSectionHeader(title: "最近的回忆") {
                        Button("查看全部 ›") { navigation.path.append(.memories) }.font(JournalTheme.font(13))
                            .foregroundStyle(JournalTheme.accentDeep)
                            .accessibilityIdentifier("home.allMemories")
                    }
                    featured(first)
                } else if loadError != nil {
                    JournalEmptyState(title: "暂时没能打开回忆", message: "故事还在，稍后再试一次。")
                } else if !ready {
                    ProgressView("正在打开回忆…").frame(maxWidth: .infinity).padding(.vertical, 100)
                } else {
                    JournalHomeEmptyView(hasPeople: !members.members.isEmpty) {
                        navigation.compose(step: members.members.isEmpty ? .add : .select)
                    }
                }
                if let error = loadError {
                    JournalError(message: error) { Task { await members.load(); await memories.load() } }.padding(.top, 16)
                }
                Color.clear.frame(height: 24)
            }.padding(.horizontal, JournalTheme.gutter).padding(.top, 6)
        }
        .scrollIndicators(.hidden).refreshable { await members.load(); await memories.load() }.journalPage()
    }

    private func featured(_ memory: MemoryEvent) -> some View {
        Button { navigation.path.append(.memory(memory.id)) } label: {
            VStack(alignment: .leading, spacing: 0) {
                if memory.imageData != nil || memory.imageName != nil { JournalPhoto(memory: memory, height: 150, radius: 16) }
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 8) {
                        JournalChip(text: memoryAbout(memory, members: members.members), style: .rose, compact: true)
                        Text(memoryWhenWhere(memory)).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineLimit(1)
                    }
                    Text(memory.title).font(JournalTheme.story(18)).foregroundStyle(JournalTheme.ink)
                        .fixedSize(horizontal: false, vertical: true).padding(.top, 8)
                    Text(JournalDemo.isPreview && memory.title == "葡萄架下的那把蒲扇" ? "那年夏天特别热，外婆总是一边摇着蒲扇，一边给我讲她小时候的故事……" : memory.content).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2).lineSpacing(4)
                        .lineLimit(2).padding(.top, 4)
                }.padding(.horizontal, 6).padding(.top, 12).padding(.bottom, 4)
            }
            .padding(10).frame(maxWidth: .infinity, alignment: .leading).journalCard()
        }.buttonStyle(.plain).accessibilityIdentifier("home.featured")
    }

    /// 杏色邀请卡：把“记录一段回忆”放在首屏最显眼的位置。
    private var invitation: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("今天，想起了谁？").font(JournalTheme.font(13)).foregroundStyle(.white.opacity(0.85))
            Text("和 AI 聊一聊，\n把记忆慢慢说出来").font(JournalTheme.story(21)).foregroundStyle(.white).lineSpacing(0)
                .padding(.top, 6).fixedSize(horizontal: false, vertical: true)
            Button { navigation.compose() } label: {
                HStack(spacing: 6) {
                    DesignIcon("plus", size: 18)
                    Text("记录一段回忆").font(JournalTheme.font(14.5, medium: true))
                }.foregroundStyle(JournalTheme.accentDeep)
                    .padding(.horizontal, 18).frame(height: 40)
                    .background(.white, in: Capsule())
                    .contentShape(Capsule())
            }.buttonStyle(.plain).padding(.top, 16).accessibilityIdentifier("home.newMemory")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20).padding(.top, 20).padding(.bottom, 18)
        .background(alignment: .topTrailing) {
            ZStack(alignment: .topTrailing) {
                Circle().fill(.white.opacity(0.12)).frame(width: 150, height: 150).offset(x: 30, y: -30)
                Circle().fill(Color(red: 1, green: 236 / 255, blue: 200 / 255).opacity(0.18)).frame(width: 110, height: 110)
                    .frame(maxHeight: .infinity, alignment: .bottom).offset(x: -30, y: 50)
            }
        }
        .background(LinearGradient(stops: [.init(color: JournalTheme.accentGlow, location: 0), .init(color: Color(hex: 0xD0754C), location: 0.6),
                                           .init(color: JournalTheme.accentDark, location: 1)], startPoint: .topLeading, endPoint: .bottomTrailing))
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .shadow(color: Color(hex: 0xD0754C).opacity(0.32), radius: 15, x: 0, y: 16)
    }
}
