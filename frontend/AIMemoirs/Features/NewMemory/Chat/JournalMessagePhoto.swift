import SwiftUI

/// The parent sets the aspect ratio; image pixels never determine a grid cell's width.
/// Photo requests use the same authenticated API boundary as conversation requests.
struct JournalMessagePhoto: View {
    let attachment: ChatAttachment
    let api: any ChatAPI
    var fit = false
    var thumbnailMaxPixelSize = 400
    var label = "讲述附件照片"
    var onOpen: (() -> Void)?
    @State private var image: UIImage?
    @State private var failure: String?
    @State private var loading = false

    var body: some View {
        GeometryReader { geometry in
            Group {
                if let failure {
                    Button { Task { await load() } } label: {
                        VStack(spacing: 6) {
                            Image(systemName: "arrow.clockwise")
                            Text(fit ? failure : "加载失败").font(JournalTheme.font(12))
                                .multilineTextAlignment(.center)
                            if fit { Text("轻点重新加载").font(JournalTheme.font(13)) }
                        }.padding(8).frame(width: geometry.size.width, height: geometry.size.height)
                    }
                    .accessibilityLabel("重新加载\(label)").accessibilityHint(failure)
                } else if let onOpen {
                    Button(action: onOpen) { photo(size: geometry.size) }
                        .accessibilityLabel(label).accessibilityHint("查看大图")
                } else {
                    photo(size: geometry.size).accessibilityLabel(label)
                }
            }
            .buttonStyle(.plain)
            .frame(width: geometry.size.width, height: geometry.size.height)
            .background(JournalTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .accessibilityIdentifier("chat.photo.\(attachment.id)")
        }
        .task(id: attachment.id) { await load() }
    }

    private func photo(size: CGSize) -> some View {
        Group {
            if let image {
                if fit { Image(uiImage: image).resizable().scaledToFit() }
                else { Image(uiImage: image).resizable().scaledToFill() }
            } else { ProgressView().accessibilityLabel("照片加载中") }
        }
        .frame(width: size.width, height: size.height).clipped().contentShape(Rectangle())
    }
    @MainActor private func load() async {
        guard !loading, image == nil else { return }
        loading = true; failure = nil
        defer { loading = false }
        do {
            let data = try await api.loadPhoto(attachment)
            guard let decoded = PhotoCompression.thumbnail(data, maxPixelSize: fit ? 2048 : thumbnailMaxPixelSize) else { throw APIError.invalidResponse }
            image = decoded
        } catch is CancellationError { }
        catch { failure = error.localizedDescription }
    }
}
