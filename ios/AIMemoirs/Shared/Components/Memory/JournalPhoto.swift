import SwiftUI

private struct JournalPhotoAPIKey: EnvironmentKey {
    static let defaultValue: (any MemoryAPI)? = nil
}
extension EnvironmentValues {
    var journalPhotoAPI: (any MemoryAPI)? {
        get { self[JournalPhotoAPIKey.self] }
        set { self[JournalPhotoAPIKey.self] = newValue }
    }
}

@MainActor final class JournalPhotoLoader: ObservableObject {
    @Published private(set) var data: Data?
    @Published private(set) var failed = false
    private var generation = UUID()

    func load(memory: MemoryEvent, api: (any MemoryAPI)?) async {
        let request = UUID()
        generation = request; data = nil; failed = false
        guard memory.imageData == nil, memory.imageName == nil,
              let attachment = memory.mediaAssets.first, let api else { return }
        do {
            let value = try await api.loadPhoto(attachment)
            try Task.checkCancellation()
            guard generation == request else { return }
            data = value
        } catch is CancellationError {
        } catch { if generation == request { failed = true } }
    }
}

/// 回忆图片展示与缺省占位，统一裁切和无障碍描述。
struct JournalPhoto: View {
    let memory: MemoryEvent
    let height: CGFloat
    var radius: CGFloat = 18
    var api: (any MemoryAPI)? = nil
    @Environment(\.journalPhotoAPI) private var inheritedAPI
    @StateObject private var loader = JournalPhotoLoader()
    var body: some View {
        GeometryReader { proxy in
            Group {
                if let data = memory.imageData ?? loader.data, let image = UIImage(data: data) {
                    Image(uiImage: image).resizable().scaledToFill()
                } else if let name = memory.imageName, UIImage(named: name) != nil {
                    Image(name).resizable().scaledToFill()
                } else {
                    ZStack {
                        JournalTheme.soft
                        if loader.failed {
                            Button("重试照片") { Task { await load() } }.foregroundStyle(JournalTheme.accentDeep)
                        } else {
                            Image(systemName: "book.closed").font(.system(size: 36, weight: .light))
                                .foregroundStyle(JournalTheme.accent.opacity(0.65))
                        }
                    }
                }
            }
            .frame(width: proxy.size.width, height: height).clipped()
        }
        .frame(height: height)
        .contentShape(RoundedRectangle(cornerRadius: radius))
        .clipShape(RoundedRectangle(cornerRadius: radius))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("回忆照片：\(memory.title)")
        .accessibilityValue((memory.imageData ?? loader.data).flatMap(UIImage.init(data:)) != nil || memory.imageName != nil ? "照片已加载" : loader.failed ? "照片读取失败" : "正在读取照片")
        .accessibilityIdentifier("memory.photo.\(memory.id)")
        .task(id: memory.mediaAssets.first?.id) { await load() }
    }
    private func load() async {
        await loader.load(memory: memory, api: api ?? inheritedAPI)
    }
}
