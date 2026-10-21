import SwiftUI

/// 四个入口共用透明底的线性图标；选中状态只通过杏色和文字字重表达。
struct JournalTabBar: View {
    @Binding var selection: JournalTab

    var body: some View {
        HStack(spacing: 0) {
            ForEach(JournalTab.allCases) { tab in
                let selected = selection == tab
                Button { selection = tab } label: {
                    VStack(spacing: 5) {
                        DesignIcon(tab.designIcon, size: 23)
                            .frame(width: 32, height: 28)
                        Text(tab.title)
                            .font(JournalTheme.font(11, medium: selected))
                            .lineLimit(1).minimumScaleFactor(0.8)
                    }
                    .foregroundStyle(selected ? JournalTheme.accentDeep : JournalTheme.ink2)
                    .frame(maxWidth: .infinity).frame(height: 66)
                    .contentShape(Rectangle())
                }
                .buttonStyle(JournalTabButtonStyle())
                .accessibilityLabel(tab.title)
                .accessibilityIdentifier("tab.\(tab.rawValue)")
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
        .padding(.horizontal, 8)
        .background(JournalTheme.surface, in: Capsule())
        .overlay { Capsule().stroke(JournalTheme.line, lineWidth: 1) }
        .shadow(color: JournalTheme.shadow.opacity(0.10), radius: 10, x: 0, y: 5)
        .padding(.horizontal, 16)
        .accessibilityElement(children: .contain).accessibilityLabel("主导航")
    }
}

private struct JournalTabButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.65 : 1)
    }
}

/// 导航栏后方的纸色渐隐，100pt 高，从透明过渡到纸色。
struct JournalTabBarFade: View {
    var body: some View {
        LinearGradient(stops: [.init(color: JournalTheme.paper.opacity(0), location: 0), .init(color: JournalTheme.paper, location: 0.55)],
                       startPoint: .top, endPoint: .bottom)
            .frame(height: 100).allowsHitTesting(false).accessibilityHidden(true)
    }
}
