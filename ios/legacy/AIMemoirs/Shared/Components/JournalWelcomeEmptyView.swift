import SwiftUI

/// 引导型空状态：插图、文案和紧凑操作组成一组；表单的通栏提交按钮不受影响。
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
            ZStack {
                Circle().fill(JournalTheme.soft.opacity(0.42)).frame(width: 156, height: 156)
                RoundedRectangle(cornerRadius: 16).fill(JournalTheme.soft)
                    .frame(width: 94, height: 116).rotationEffect(.degrees(-12)).offset(x: -10, y: 1)
                VStack(spacing: 12) {
                    Image(systemName: symbol).font(.system(size: 32, weight: .ultraLight))
                        .foregroundStyle(JournalTheme.accent)
                    Capsule().fill(JournalTheme.soft).frame(width: 30, height: 2)
                }.frame(width: 94, height: 116)
                    .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                    .overlay { RoundedRectangle(cornerRadius: 16).stroke(JournalTheme.line.opacity(0.65), lineWidth: 0.5) }
                    .rotationEffect(.degrees(8)).offset(x: 7, y: -1)
            }.accessibilityHidden(true).padding(.bottom, 28)
            Text(title).font(JournalTheme.story(22)).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Text(message).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
                .lineSpacing(6).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true).padding(.top, 12)
            Button(action: onAction) {
                HStack(spacing: 8) {
                    Image(systemName: "plus").font(.system(size: 12, weight: .medium))
                    Text(actionTitle).font(.custom("PingFangSC-Medium", size: 14, relativeTo: .body))
                        .multilineTextAlignment(.center)
                }.foregroundStyle(JournalTheme.surface)
                    .padding(.horizontal, 24).padding(.vertical, 12).frame(minHeight: 46)
                    .background(JournalTheme.accent, in: Capsule())
                    .contentShape(Capsule())
            }.buttonStyle(.plain).padding(.top, 28).accessibilityIdentifier(actionID)
        }
        .frame(maxWidth: .infinity).padding(.horizontal, 12).padding(.vertical, 24)
        // 用当前可用区域居中整组内容，平分上下留白；小屏或大字号时仍按自然高度滚动。
        .frame(minHeight: minimumHeight, alignment: .center)
    }
}
