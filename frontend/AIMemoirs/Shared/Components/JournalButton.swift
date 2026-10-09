import SwiftUI

/// 通用操作按钮，统一加载、禁用和按压效果。
struct JournalButton: View {
    let title: String
    var secondary = false
    var loading = false
    var disabled = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if loading { ProgressView().tint(secondary ? JournalTheme.accent : JournalTheme.surface) }
                Text(title).font(.custom("PingFangSC-Medium", size: 16, relativeTo: .body))
            }
            .frame(maxWidth: .infinity).frame(minHeight: 54)
            .foregroundStyle(secondary ? JournalTheme.accent : JournalTheme.surface)
            .background(secondary ? JournalTheme.soft : JournalTheme.accent.opacity(disabled ? 0.72 : 1), in: RoundedRectangle(cornerRadius: 16))
            .contentShape(RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(JournalActionButtonStyle()).disabled(disabled || loading)
    }
}

/// Keep disabled labels opaque; the fill alone communicates availability.
private struct JournalActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.88 : 1)
    }
}
