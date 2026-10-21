import SwiftUI

/// 通用操作按钮：54pt 杏色胶囊；secondary 为暖白描边胶囊，soft 为浅杏底。
struct JournalButton: View {
    let title: String
    var icon: String? = nil
    var secondary = false
    var soft = false
    var loading = false
    var disabled = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading { ProgressView().tint(filled ? .white : JournalTheme.accentDeep) }
                else if let icon { DesignIcon(icon, size: 22) }
                Text(title).font(JournalTheme.font(16, medium: true)).tracking(0.96)
            }
            .frame(maxWidth: .infinity).frame(minHeight: 54)
            .foregroundStyle(filled ? .white : JournalTheme.accentDeep)
            .background {
                if secondary {
                    Capsule().fill(JournalTheme.surface).overlay { Capsule().stroke(JournalTheme.soft, lineWidth: 1.5) }
                } else if soft {
                    Capsule().fill(JournalTheme.soft)
                } else {
                    Capsule().fill(JournalTheme.accent).opacity(disabled ? 0.5 : 1)
                        .shadow(color: JournalTheme.accent.opacity(disabled ? 0 : 0.30), radius: 11, x: 0, y: 10)
                }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(JournalActionButtonStyle()).disabled(disabled || loading)
    }
    private var filled: Bool { !secondary && !soft }
}

/// 按压时轻微缩放；禁用状态只通过底色表达。
struct JournalActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.88 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}
