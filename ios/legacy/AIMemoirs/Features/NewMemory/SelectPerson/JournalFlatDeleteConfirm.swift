import SwiftUI

/// 人物删除确认层；确认回调由流程容器执行，不在组件内直接请求服务器。
struct JournalFlatDeleteConfirm: View {
    let name: String
    let onConfirm: () -> Void
    let onCancel: () -> Void
    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .bottom) {
                VStack(spacing: 0) {
                    Color.clear.frame(height: geometry.safeAreaInsets.top)
                    Color.black.opacity(0.28)
                        .contentShape(Rectangle())
                        .onTapGesture(perform: onCancel)
                }
                .ignoresSafeArea(edges: .bottom)

                VStack(spacing: 0) {
                    Text("删除「\(name)」？")
                        .font(JournalTheme.font(17, medium: true))
                        .foregroundStyle(JournalTheme.ink)
                        .multilineTextAlignment(.center)
                        .padding(.top, 22).padding(.horizontal, 20)
                    Text("该人物将从列表中移除，仅属于此人的回忆将不再显示。")
                        .font(JournalTheme.font(13))
                        .foregroundStyle(JournalTheme.muted)
                        .multilineTextAlignment(.center)
                        .padding(.top, 8).padding(.horizontal, 20)
                    Button(action: onConfirm) {
                        Text("删除")
                            .font(JournalTheme.font(16, medium: true))
                            .foregroundStyle(.red)
                            .frame(maxWidth: .infinity)
                            .frame(height: 50)
                            .background(Color(red: 0.95, green: 0.95, blue: 0.96), in: RoundedRectangle(cornerRadius: 12))
                            .contentShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 20).padding(.top, 18)
                    Button("取消", action: onCancel)
                        .font(JournalTheme.font(15))
                        .foregroundStyle(JournalTheme.muted)
                        .frame(maxWidth: .infinity)
                        .frame(height: 44)
                        .padding(.bottom, 8)
                }
                .frame(maxWidth: .infinity)
                .background(JournalTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .padding(.horizontal, 16)
                .padding(.bottom, geometry.safeAreaInsets.bottom + 12)
            }
        }
        .ignoresSafeArea()
    }
}
