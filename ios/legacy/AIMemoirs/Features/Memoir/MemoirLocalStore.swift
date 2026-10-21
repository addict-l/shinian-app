import Foundation
import CryptoKit

struct MemoirLocalState: Codable {
    var snapshot: MemoirSnapshot
    var settings: MemoirSettings
    var pending: MemoirSaveRequest?
    var dirty = false
}
/// Per-server/account/person protected manifests and durable image copies.
@MainActor final class MemoirLocalStore {
    let root: URL
    init(root: URL) { self.root = root }
    static func current(personID: UUID, preview: String? = nil) -> MemoirLocalStore? {
        let scope: String
        if let preview { scope = "memoir-preview:" + preview }
        else {
            guard let username = BasicCredentialStore.shared.load()?.username else { return nil }
            scope = APIClient.local.baseURL.absoluteString + "\n" + username
        }
        let key = SHA256.hash(data: Data(scope.utf8)).map { String(format: "%02x", $0) }.joined()
        return MemoirLocalStore(root: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Memoirs/\(key)/\(personID.uuidString)"))
    }
    func prepare() throws {
        var directory = root
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
    }
    func load() throws -> MemoirLocalState? {
        let url = root.appendingPathComponent("settings.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        return try JSONDecoder().decode(MemoirLocalState.self, from: Data(contentsOf: url))
    }
    func save(_ value: MemoirLocalState) throws {
        try prepare()
        try JSONEncoder().encode(value).write(to: root.appendingPathComponent("settings.json"),
            options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
    func photoURL(_ id: UUID) -> URL { root.appendingPathComponent(id.uuidString + ".jpg") }
    func savePhoto(_ data: Data, id: UUID) throws -> URL {
        try prepare(); let url = photoURL(id)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]); return url
    }
}
