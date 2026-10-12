import SwiftUI

/// 引导型空状态：水彩插画、文案和紧凑操作组成一组；表单的通栏提交按钮不受影响。
struct JournalWelcomeEmptyView: View {
    let symbol: String
    let title: String
    let message: String
    let actionTitle: String
    let actionID: String
    var minimumHeight: CGFloat = 0
    let onAction: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .bottomTrailing) {
                Image("JournalWelcome").resizable().scaledToFill()
                    .frame(width: 210, height: 210).clipShape(Circle())
                    .overlay { Circle().stroke(JournalTheme.surface, lineWidth: 6) }
                    .shadow(color: JournalTheme.shadow.opacity(0.14), radius: 16, x: 0, y: 8)
                Image(systemName: symbol).font(.system(size: 20, weight: .regular))
                    .foregroundStyle(JournalTheme.accent)
                    .frame(width: 52, height: 52).background(JournalTheme.surface, in: Circle())
                    .shadow(color: JournalTheme.shadow.opacity(0.12), radius: 6, x: 0, y: 3)
                    .offset(x: -6, y: -6)
            }.accessibilityHidden(true).padding(.bottom, 28)
            Text(title).font(JournalTheme.story(23)).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Text(message).font(JournalTheme.font(14)).foregroundStyle(JournalTheme.muted)
                .lineSpacing(6).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true).padding(.top, 12)
            Button(action: onAction) {
                HStack(spacing: 8) {
                    Image(systemName: "plus").font(.system(size: 13, weight: .semibold))
                    Text(actionTitle).font(.custom("PingFangSC-Medium", size: 15, relativeTo: .body))
                        .multilineTextAlignment(.center)
                }.foregroundStyle(JournalTheme.surface)
                    .padding(.horizontal, 26).padding(.vertical, 12).frame(minHeight: 48)
                    .background(LinearGradient(colors: [JournalTheme.accentGlow, JournalTheme.accent], startPoint: .topLeading, endPoint: .bottomTrailing), in: Capsule())
                    .shadow(color: JournalTheme.accent.opacity(0.28), radius: 10, x: 0, y: 6)
                    .contentShape(Capsule())
            }.buttonStyle(.plain).padding(.top, 28).accessibilityIdentifier(actionID)
        }
        .frame(maxWidth: .infinity).padding(.horizontal, 12).padding(.vertical, 24)
        // 用当前可用区域居中整组内容，平分上下留白；小屏或大字号时仍按自然高度滚动。
        .frame(minHeight: minimumHeight, alignment: .center)
    }
}
