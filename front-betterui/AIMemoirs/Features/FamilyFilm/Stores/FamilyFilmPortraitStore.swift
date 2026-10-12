import SwiftUI

/// User-chosen portraits are local presentation assets, keyed by server person ID.
@MainActor final class FamilyFilmPortraitStore: ObservableObject {
    @Published private(set) var images: [UUID: UIImage] = [:]
    @Published var errorMessage: String?
    private let directory: URL
    init(directory: URL? = nil) {
        self.directory = directory ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("FamilyPortraits", isDirectory: true)
    }
    func load(_ ids: [UUID]) {
        for id in ids where images[id] == nil {
            if let data = try? Data(contentsOf: url(id)), let image = UIImage(data: data) { images[id] = image }
        }
    }
    func save(_ data: Data, for id: UUID) throws {
        guard let decoded = UIImage(data: data) else { throw APIError.server("这张照片无法读取，请重新选择。") }
        let size = decoded.size
        guard size.width > 0, size.height > 0 else { throw APIError.server("照片尺寸无效。") }
        let scale = min(1, 600 / max(size.width, size.height))
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let image = UIGraphicsImageRenderer(size: CGSize(width: size.width * scale, height: size.height * scale), format: format).image { _ in
            decoded.draw(in: CGRect(origin: .zero, size: CGSize(width: size.width * scale, height: size.height * scale)))
        }
        guard let jpeg = image.jpegData(compressionQuality: 0.85) else { throw APIError.server("照片保存失败。") }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try jpeg.write(to: url(id), options: .atomic)
        images[id] = image
    }
    private func url(_ id: UUID) -> URL { directory.appendingPathComponent(id.uuidString).appendingPathExtension("jpg") }
}
