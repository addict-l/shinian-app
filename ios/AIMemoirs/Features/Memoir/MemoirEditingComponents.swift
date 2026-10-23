import SwiftUI

enum MemoirEditorPanel: String, Identifiable {
    case style, name, reading
    var id: String { rawValue }
    var title: String { switch self { case .style: "封面样式"; case .name: "书名与副标题"; case .reading: "阅读设置" } }
}
extension MemoirCover {
    var editorTitle: String { switch self { case .photo: "暖纸"; case .collage: "拼贴"; case .text: "素雅" } }
}
struct MemoirSettingRow: View {
    let icon: String
    let title: String
    var detail: String? = nil
    var value: String? = nil
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                DesignIcon(icon, size: 20).foregroundStyle(JournalTheme.ink2).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 6) {
                    Text(title).font(JournalTheme.font(14, medium: true)).foregroundStyle(JournalTheme.ink)
                    if let detail { Text(detail).font(JournalTheme.font(11.5)).foregroundStyle(JournalTheme.ink2).lineLimit(2) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                if let value { Text(value).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2) }
                DesignIcon("chev", size: 16).foregroundStyle(JournalTheme.ink2).accessibilityHidden(true)
            }.padding(.horizontal, 18).padding(.vertical, 16).frame(minHeight: 65).contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
}

struct MemoirActionButton: View {
    let title: String
    var secondary = false
    var loading = false
    var disabled = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading { ProgressView().tint(secondary ? JournalTheme.accentDeep : .white) }
                Text(title).font(JournalTheme.font(16, medium: true)).multilineTextAlignment(.center)
            }.frame(maxWidth: .infinity).padding(.horizontal, 12).padding(.vertical, 14).frame(minHeight: 54)
                .foregroundStyle(secondary ? JournalTheme.accentDeep : .white)
                .background(secondary ? JournalTheme.surface : JournalTheme.accentDeep, in: RoundedRectangle(cornerRadius: 16))
                .overlay { if secondary { RoundedRectangle(cornerRadius: 16).stroke(JournalTheme.line, lineWidth: 1) } }
                .opacity(disabled ? 0.5 : 1).contentShape(RoundedRectangle(cornerRadius: 16))
        }.buttonStyle(JournalActionButtonStyle()).disabled(disabled || loading)
    }
}
