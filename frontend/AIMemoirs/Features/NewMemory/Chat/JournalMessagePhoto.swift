import SwiftUI

/// Photo requests use the same authenticated API boundary as conversation requests.
struct JournalMessagePhoto: View {
    let attachment: ChatAttachment
    let api: any ChatAPI
    let height: CGFloat
    var fit = false
    @State private var image: UIImage?
    @State private var failure: String?
    @State private var loading = false

    var body: some View {
        Group {
            if let image {
                if fit { Image(uiImage: image).resizable().scaledToFit() }
                else { Image(uiImage: image).resizable().scaledToFill() }
            } else if let failure {
                VStack(spacing: 4) {
                    Text(failure).font(JournalTheme.font(12)).multilineTextAlignment(.center)
                    Button("重新加载") { Task { await load() } }.frame(minHeight: 44)
                }
            } else { ProgressView("照片加载中") }
        }.frame(maxWidth: .infinity).frame(height: height).clipped()
            .background(JournalTheme.surface).clipShape(RoundedRectangle(cornerRadius: 10))
            .accessibilityLabel("讲述附件照片")
            .task(id: attachment.id) { await load() }
    }
    @MainActor private func load() async {
        guard !loading, image == nil else { return }
        loading = true; failure = nil
        defer { loading = false }
        do {
            let data = try await api.loadPhoto(attachment)
            guard let decoded = PhotoCompression.thumbnail(data, maxPixelSize: fit ? 2048 : 400) else { throw APIError.invalidResponse }
            image = decoded
        } catch is CancellationError { }
        catch { failure = error.localizedDescription }
    }
}
