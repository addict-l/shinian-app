import SwiftUI

/// 我的主页面：展示统计与管理入口，复用全局人物及回忆数据。
struct JournalProfileView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @AppStorage("journal.displayName") private var displayName = "回忆的收藏者"
    private var collection: FamilyMemoryCollection {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents)
    }
    private var ready: Bool { members.hasLoaded && memories.hasLoaded }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                JournalHeader(kicker: "MY MEMORIES", title: "我的", subtitle: "给回忆一个长久安放的地方。")
                HStack(spacing: 16) {
                    Image(systemName: "person").font(.system(size: 32, weight: .light)).foregroundStyle(JournalTheme.accent)
                        .frame(width: 72, height: 72).background(JournalTheme.soft, in: Circle())
                    VStack(alignment: .leading, spacing: 13) {
                        Text(displayName).font(JournalTheme.font(20, medium: true))
                        Text("和家人一起，记住生活。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
                    }
                }.padding(.top, 34)
                HStack(spacing: 0) {
                    statistic(members.hasLoaded ? members.members.count : nil, title: "家庭人物")
                    statistic(ready ? collection.events.count : nil, title: "珍藏回忆")
                    statistic(ready ? collection.participatingPeopleCount : nil, title: "有故事的家人")
                }.frame(height: 103).background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 20)).padding(.top, 32)
                VStack(spacing: 0) {
                    row("管理家庭人物", icon: "person") { navigation.compose(step: .select) }
                    row("我的全部回忆", icon: "book") { navigation.path.append(.memories) }
                    row("隐私与数据", icon: "checkmark.shield") { navigation.path.append(.privacy) }
                    row("设置", icon: "gearshape") { navigation.path.append(.settings) }
                }.padding(.top, 36)
                Text("拾年 · 留住时光").font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                    .frame(maxWidth: .infinity).padding(.top, 45).padding(.bottom, 28)
            }.padding(.horizontal, 24)
        }.scrollIndicators(.hidden).journalPage()
    }
    private func statistic(_ count: Int?, title: String) -> some View {
        VStack(spacing: 13) { Text(count.map(String.init) ?? "—").font(JournalTheme.font(25, medium: true)); Text(title).font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted) }
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(title).accessibilityValue(count.map(String.init) ?? "加载中")
            .accessibilityIdentifier("profile.stat.\(title)")
    }
    private func row(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 17) {
                Image(systemName: icon).font(.system(size: 21, weight: .regular)).foregroundStyle(JournalTheme.accent).frame(width: 24)
                Text(title).font(JournalTheme.font(15)).foregroundStyle(JournalTheme.ink); Spacer()
                Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(JournalTheme.muted)
            }.frame(height: 65).contentShape(Rectangle()).overlay(alignment: .bottom) { JournalTheme.line.frame(height: 1) }
        }.buttonStyle(.plain)
    }
}
