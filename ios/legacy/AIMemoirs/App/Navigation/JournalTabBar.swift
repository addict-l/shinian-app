import SwiftUI

/// 主导航栏只负责标签切换；由根视图预留真实高度，避免遮挡聊天输入框。
struct JournalTabBar: View {
    @Binding var selection: JournalTab
    let dark: Bool
    var body: some View {
        HStack(spacing: 0) {
            ForEach(JournalTab.allCases) { tab in
                Button { selection = tab } label: {
                    VStack(spacing: 3) {
                        JournalIcon(name: tab.designIcon)
                            .frame(width: 52, height: 29)
                            .background(selection == tab ? (dark ? Color(red: 0.145, green: 0.192, blue: 0.294) : JournalTheme.soft) : .clear, in: Capsule())
                        Text(tab.title).font(JournalTheme.font(10))
                    }
                    .foregroundStyle(selection == tab ? (dark ? JournalTheme.nightInk : JournalTheme.accent) : (dark ? JournalTheme.nightMuted : JournalTheme.muted))
                    .frame(maxWidth: .infinity).frame(height: 48).contentShape(Rectangle())
                }
                .buttonStyle(.plain).accessibilityIdentifier("tab.\(tab.rawValue)")
                .accessibilityAddTraits(selection == tab ? .isSelected : [])
            }
        }
        .padding(.top, 0)
        .background((dark ? JournalTheme.night : JournalTheme.paper).ignoresSafeArea(edges: .bottom))
        .accessibilityElement(children: .contain).accessibilityLabel("主导航")
    }
}
