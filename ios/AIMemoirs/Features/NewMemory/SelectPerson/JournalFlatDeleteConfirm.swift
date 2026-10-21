import SwiftUI

/// 人物删除确认层；确认回调由流程容器执行，不在组件内直接请求服务器。
struct JournalFlatDeleteConfirm: View {
    let name: String
    let onConfirm: () -> Void
    let onCancel: () -> Void
    var body: some View {
        JournalActionSheet(title: "删除「\(name)」？", message: "该人物将从列表中移除，仅属于此人的回忆将不再显示。", onCancel: onCancel) {
            JournalActionSheetRow(title: "删除", icon: "trash", destructive: true, action: onConfirm)
        }
    }
}

/// 设计稿中的底部操作层：暖白圆角面板 + 独立的“取消”按钮，背景为暖棕半透明遮罩。
struct JournalActionSheet<Rows: View>: View {
    let title: String
    var message: String? = nil
    let onCancel: () -> Void
    @ViewBuilder var rows: () -> Rows
    var body: some View {
        ZStack(alignment: .bottom) {
            Color(hex: 0x3D2E24, opacity: 0.28).ignoresSafeArea()
                .contentShape(Rectangle()).onTapGesture(perform: onCancel)
                .accessibilityHidden(true)
            VStack(spacing: 10) {
                VStack(spacing: 0) {
                    VStack(spacing: 6) {
                        Text(title).font(JournalTheme.font(message == nil ? 12 : 15, medium: message != nil))
                            .foregroundStyle(message == nil ? JournalTheme.muted : JournalTheme.ink)
                        if let message {
                            Text(message).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        }
                    }
                    .multilineTextAlignment(.center).padding(.horizontal, 20).padding(.top, 16).padding(.bottom, 10)
                    rows()
                }
                .padding(.bottom, 8)
                .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
                .journalLiftedShadow()
                Button(action: onCancel) {
                    Text("取消").font(JournalTheme.font(16, medium: true)).foregroundStyle(JournalTheme.accentDeep)
                        .frame(maxWidth: .infinity).frame(height: 54)
                        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                        .contentShape(Rectangle())
                }.buttonStyle(.plain)
            }
            .padding(.horizontal, 12).padding(.bottom, 4)
        }
    }
}

struct JournalActionSheetRow: View {
    let title: String
    let icon: String
    var destructive = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                DesignIcon(icon).foregroundStyle(destructive ? JournalTheme.danger : JournalTheme.accent)
                Text(title).font(JournalTheme.font(16)).foregroundStyle(destructive ? JournalTheme.danger : JournalTheme.ink)
                Spacer()
            }
            .padding(.horizontal, 22).frame(height: 52)
            .overlay(alignment: .top) { JournalTheme.line.frame(height: 1) }
            .contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
}
