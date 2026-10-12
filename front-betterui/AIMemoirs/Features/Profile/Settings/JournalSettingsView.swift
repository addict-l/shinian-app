import SwiftUI

struct JournalSettingsView: View {
    @AppStorage("journal.displayName") private var name = "回忆的收藏者"
    @EnvironmentObject private var authentication: AuthenticationStore
    @FocusState private var editingName: Bool

    var body: some View {
        VStack(spacing: 0) {
            JournalBackBar(title: "设置")
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    label("个人展示", top: 0)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("显示名称").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        HStack {
                            TextField("显示名称", text: $name).font(JournalTheme.font(16)).focused($editingName)
                                .submitLabel(.done).onSubmit { editingName = false }
                            Button { editingName = true } label: { DesignIcon("edit", size: 18).frame(width: 44, height: 28) }
                                .buttonStyle(.plain).foregroundStyle(JournalTheme.accent).accessibilityLabel("修改显示名称")
                        }
                    }.padding(.horizontal, 16).padding(.vertical, 14).journalCard()
                    label("家庭胶片")
                    HStack(alignment: .top, spacing: 12) {
                        JournalIconTile(icon: "film")
                        Text("每位家人拥有自己的胶卷，左右滑动翻阅回忆。点击“查看全部家人”可搜索和浏览所有胶卷，长按人物头像可以更换照片。")
                            .font(JournalTheme.font(13.5)).foregroundStyle(JournalTheme.ink2).lineSpacing(7)
                            .fixedSize(horizontal: false, vertical: true)
                    }.padding(16).journalCard()
                    label("关于")
                    HStack(spacing: 12) {
                        Text("拾").font(JournalTheme.story(22)).foregroundStyle(.white).frame(width: 54, height: 54)
                            .background(LinearGradient(colors: [JournalTheme.accentGlow, JournalTheme.accentDark], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 16))
                        VStack(alignment: .leading, spacing: 3) {
                            Text("拾年 · 留住时光").font(JournalTheme.story(16))
                            Text("界面版本 V1").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        }
                        Spacer()
                    }.padding(16).journalCard()
                    Button { authentication.logout() } label: {
                        HStack(spacing: 6) {
                            DesignIcon("logout", size: 19)
                            Text("退出家庭账号").font(JournalTheme.font(15.5))
                        }.foregroundStyle(JournalTheme.danger).frame(maxWidth: .infinity).frame(height: 52)
                            .background(JournalTheme.surface, in: Capsule())
                            .overlay { Capsule().stroke(Color(hex: 0xF0D3CC), lineWidth: 1) }
                    }.buttonStyle(JournalActionButtonStyle()).padding(.top, 34)
                }.padding(.horizontal, JournalTheme.gutter).padding(.top, 8).padding(.bottom, 24)
            }.scrollIndicators(.hidden)
        }.journalPage()
    }
    private func label(_ text: String, top: CGFloat = 22) -> some View {
        Text(text).font(JournalTheme.font(12)).tracking(1.2).foregroundStyle(JournalTheme.muted)
            .padding(.horizontal, 6).padding(.top, top).padding(.bottom, 8)
    }
}
