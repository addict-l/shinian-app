import SwiftUI

/// 人物头像：优先使用家庭胶片中为该人物选择的本机照片，否则显示暖色身份文字头像。
struct JournalAvatar: View {
    let person: FamilyMember
    var size: CGFloat = 48
    var body: some View {
        let tint = JournalTheme.avatarTint(for: person.id)
        JournalAvatarFrame(size: size) {
            if let image = JournalPortraitCache.image(for: person.id) {
                Image(uiImage: image).resizable().scaledToFill()
            } else if let name = person.profileImages.first(where: { UIImage(named: $0) != nil }) {
                Image(name).resizable().scaledToFill()
            } else {
                Text(Self.initial(for: person))
                    .font(JournalTheme.story(size * 0.36)).foregroundStyle(tint.ink)
                    .frame(maxWidth: .infinity, maxHeight: .infinity).background(tint.fill)
            }
        }
    }
    static func initial(for person: FamilyMember) -> String {
        let roles = ["爸爸": "父", "妈妈": "母"]
        if let mapped = roles[person.relationship] { return mapped }
        return String((person.relationship.isEmpty ? person.name : person.relationship).prefix(1))
    }
}

/// 圆形头像外框：白色描边与暖色投影。
struct JournalAvatarFrame<Content: View>: View {
    let size: CGFloat
    @ViewBuilder var content: () -> Content
    var body: some View {
        content()
            .frame(width: size, height: size).clipShape(Circle())
            .overlay { Circle().stroke(.white, lineWidth: borderWidth) }
            .shadow(color: Color(red: 140 / 255, green: 90 / 255, blue: 50 / 255).opacity(0.15), radius: 5, x: 0, y: 3)
            .accessibilityHidden(true)
    }
    private var borderWidth: CGFloat {
        if size >= 80 { return 4 }
        if size <= 26 { return 1.5 }
        if size <= 34 { return 2 }
        return 2.5
    }
}

/// 使用者本人的头像，保存在本机，不上传。
struct JournalUserAvatar: View {
    var size: CGFloat = 38
    @ObservedObject private var store = JournalProfileAvatarStore.shared
    var body: some View {
        JournalAvatarFrame(size: size) {
            if let image = store.image {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                DesignIcon("person", size: size * 0.46).foregroundStyle(JournalTheme.accent)
                    .frame(maxWidth: .infinity, maxHeight: .infinity).background(JournalTheme.soft)
            }
        }
    }
}

@MainActor final class JournalProfileAvatarStore: ObservableObject {
    static let shared = JournalProfileAvatarStore()
    @Published private(set) var image: UIImage?
    private var url: URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Accounts/" + FamilySessionRegistry.scopeKey + "/ProfileAvatar.jpg") }
    private init() { reload() }
    func reload() {
        image = JournalDemo.isPreview ? UIImage(named: "DesignPhoto-mom") : nil
        if let data = try? Data(contentsOf: url) { image = UIImage(data: data) }
    }
    func save(_ data: Data) throws {
        guard let decoded = UIImage(data: data), decoded.size.width > 0, decoded.size.height > 0 else {
            throw APIError.server("这张照片无法读取，请重新选择。")
        }
        let scale = min(1, 600 / max(decoded.size.width, decoded.size.height))
        let size = CGSize(width: decoded.size.width * scale, height: decoded.size.height * scale)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let resized = UIGraphicsImageRenderer(size: size, format: format).image { _ in decoded.draw(in: CGRect(origin: .zero, size: size)) }
        guard let jpeg = resized.jpegData(compressionQuality: 0.85) else { throw APIError.server("照片保存失败。") }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try jpeg.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        image = resized
    }
}

/// 只读访问家庭胶片保存的本机头像（Documents/FamilyPortraits），按文件修改时间失效缓存。
enum JournalPortraitCache {
    private static var directory: URL { FamilySessionRegistry.portraitsDirectory }
    private static let cache = NSCache<NSString, Entry>()
    private final class Entry { let date: Date; let image: UIImage; init(date: Date, image: UIImage) { self.date = date; self.image = image } }

    static func image(for id: UUID) -> UIImage? {
        let url = directory.appendingPathComponent(id.uuidString).appendingPathExtension("jpg")
        guard let date = (try? FileManager.default.attributesOfItem(atPath: url.path))?[.modificationDate] as? Date else { return nil }
        let key = (FamilySessionRegistry.scopeKey + id.uuidString) as NSString
        if let entry = cache.object(forKey: key), entry.date == date { return entry.image }
        guard let image = UIImage(contentsOfFile: url.path) else { return nil }
        cache.setObject(Entry(date: date, image: image), forKey: key)
        return image
    }
}
