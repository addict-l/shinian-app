import SwiftUI
import PhotosUI

struct JournalProfileView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @AppStorage("journal.displayName") private var displayName = "回忆的收藏者"

    @State private var avatarPhoto: PhotosPickerItem?
    @State private var avatarError: String?
    private var collection: FamilyMemoryCollection {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                JournalTitle("我的")
                profileCard.padding(.top, 14)
                VStack(spacing: 0) {
                    row("我的全部回忆", icon: "heart", fill: JournalTheme.soft, ink: JournalTheme.accentDeep) { navigation.path.append(.memories) }
                    divider
                    row("管理家庭人物", icon: "users", fill: JournalTheme.sageSoft, ink: JournalTheme.sageInk) { navigation.compose(step: .select) }
                }.padding(.vertical, 4).journalCard().padding(.top, 16)
                VStack(spacing: 0) {
                    row("设置", icon: "gear", fill: JournalTheme.butterSoft, ink: JournalTheme.butterInk) { navigation.path.append(.settings) }
                    divider
                    row("隐私与数据", icon: "shield", fill: JournalTheme.roseSoft, ink: JournalTheme.roseInk) { navigation.path.append(.privacy) }
                }.padding(.vertical, 4).journalCard().padding(.top, 12)
                VStack(spacing: 4) {
                    Text("拾年 · 留住时光").font(JournalTheme.story(14)).foregroundStyle(JournalTheme.ink2)
                    Text("给回忆一个长久安放的地方。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                }.frame(maxWidth: .infinity).padding(.top, 20)
            }.padding(.horizontal, JournalTheme.gutter).padding(.top, 6).padding(.bottom, 24)
        }.scrollIndicators(.hidden).journalPage()
            .onChange(of: avatarPhoto) { _, photo in
                Task {
                    defer { avatarPhoto = nil }
                    do {
                        guard let photo, let data = try await photo.loadTransferable(type: Data.self) else { return }
                        try JournalProfileAvatarStore.shared.save(data)
                    } catch { avatarError = error.localizedDescription }
                }
            }
            .alert("头像未保存", isPresented: Binding(get: { avatarError != nil }, set: { if !$0 { avatarError = nil } })) {
                Button("知道了", role: .cancel) { avatarError = nil }
            } message: { Text(avatarError ?? "") }
    }
    private var profileCard: some View {
        VStack(spacing: 18) {
            HStack(spacing: 14) {
                PhotosPicker(selection: $avatarPhoto, matching: .images) { JournalUserAvatar(size: 66) }
                    .buttonStyle(.plain).accessibilityLabel("更换我的头像")
                VStack(alignment: .leading, spacing: 4) {
                    Text(displayName).font(JournalTheme.story(21))
                    Text("和家人一起，记住生活。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 0) {
                statistic(members.hasLoaded ? members.members.count : nil, title: "家庭人物")
                JournalTheme.line.frame(width: 1, height: 38)
                statistic(memories.hasLoaded && members.hasLoaded ? collection.events.count : nil, title: "珍藏回忆")
                JournalTheme.line.frame(width: 1, height: 38)
                statistic(memories.hasLoaded && members.hasLoaded ? collection.participatingPeopleCount : nil, title: "有故事的家人")
            }.padding(.vertical, 12).background(JournalTheme.surface.opacity(0.75), in: RoundedRectangle(cornerRadius: 18))
        }.padding(20)
            .background(alignment: .topTrailing) {
                Circle().fill(.white.opacity(0.4)).frame(width: 140, height: 140).offset(x: 20, y: -30)
            }
            .background(LinearGradient(colors: [Color(hex: 0xE8EEDD), Color(hex: 0xF6EBD9)], startPoint: .topLeading, endPoint: .bottomTrailing))
            .clipShape(RoundedRectangle(cornerRadius: 28))
    }
    private var divider: some View { JournalTheme.line.frame(height: 1).padding(.leading, 66) }
    private func statistic(_ count: Int?, title: String) -> some View {
        VStack(spacing: 0) {
            Text(count.map(String.init) ?? "—").font(JournalTheme.story(22)).foregroundStyle(JournalTheme.accentDeep)
            Text(title).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
        }.frame(maxWidth: .infinity).accessibilityElement(children: .combine).accessibilityIdentifier("profile.stat.\(title)")
    }
    private func row(_ title: String, icon: String, fill: Color, ink: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                JournalIconTile(icon: icon, fill: fill, ink: ink)
                Text(title).font(JournalTheme.font(15.5)).foregroundStyle(JournalTheme.ink)
                Spacer()
                DesignIcon("chev").foregroundStyle(JournalTheme.muted)
            }.padding(.horizontal, 16).padding(.vertical, 14).contentShape(Rectangle())
        }.buttonStyle(JournalActionButtonStyle())
    }
}
