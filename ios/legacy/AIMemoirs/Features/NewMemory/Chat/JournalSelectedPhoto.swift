import SwiftUI

/// Removal has a 44pt target; normal selected photos need no repeated status caption.
struct JournalSelectedPhoto: View {
    let photo: MessagePhoto
    let index: Int
    let disabled: Bool
    let onRemove: () -> Void

    var body: some View {
        VStack(spacing: 4) {
            ZStack(alignment: .topTrailing) {
                Group {
                    if let image = photo.thumbnail {
                        Image(uiImage: image).resizable().scaledToFill()
                    } else {
                        Image(systemName: "photo").foregroundStyle(JournalTheme.muted)
                    }
                }
                .frame(width: 72, height: 72).clipped()
                .background(JournalTheme.soft)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .frame(width: 84, height: 84, alignment: .bottomLeading)
                .accessibilityLabel("待发送照片 \(index + 1)")

                if photo.status == .uploading {
                    ProgressView().padding(6).background(JournalTheme.surface, in: Circle())
                        .frame(width: 72, height: 72).padding(.top, 12).padding(.trailing, 12)
                        .accessibilityLabel("照片 \(index + 1) 上传中")
                }

                Button(action: onRemove) {
                    Image(systemName: "xmark").font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(JournalTheme.ink)
                        .frame(width: 24, height: 24)
                        .background(JournalTheme.surface, in: Circle())
                        .overlay(Circle().stroke(JournalTheme.line, lineWidth: 1))
                        .frame(width: 44, height: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain).disabled(disabled)
                .accessibilityLabel("移除照片 \(index + 1)")
                .accessibilityIdentifier("chat.removePhoto.\(photo.id)")
            }
            if photo.status == .failed {
                Label("上传失败", systemImage: "exclamationmark.circle")
                    .font(JournalTheme.font(11)).foregroundStyle(JournalTheme.accent)
            }
        }
    }
}
