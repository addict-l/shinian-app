import Foundation
import CryptoKit

struct StoredChatPhoto: Codable {
    let id: UUID
    var attachment: ChatAttachment?
}

struct LocalChatDraft: Codable, Identifiable {
    var id: UUID
    var sessionID: UUID?
    let personID: UUID
    let personName: String
    let relationship: String
    var input: String = ""
    var pendingText: String?
    var pendingMessageID: UUID?
    var pendingAttachments: [UUID] = []
    var photos: [StoredChatPhoto] = []
    var snapshot: ChatSnapshot?
    var updatedAt = Date()
}

/// Protected per-server/account files. Metadata is atomic; photo IDs survive restarts.
@MainActor final class ChatDraftStore {
    private let root: URL
    init(root: URL) { self.root = root }

    static func current(previewScreen: String?) -> ChatDraftStore? {
        var scope: String
        #if DEBUG
        if let testScope = ProcessInfo.processInfo.environment["AI_MEMORIES_DRAFT_TEST_SCOPE"] {
            scope = "ui-test:" + testScope
        } else {
            guard previewScreen == nil, let username = BasicCredentialStore.shared.load()?.username else { return nil }
            scope = APIClient.local.baseURL.absoluteString + "\n" + username
        }
        #else
        guard let username = BasicCredentialStore.shared.load()?.username else { return nil }
        scope = APIClient.local.baseURL.absoluteString + "\n" + username
        #endif
        let key = SHA256.hash(data: Data(scope.utf8)).map { String(format: "%02x", $0) }.joined()
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return ChatDraftStore(root: base.appendingPathComponent("PendingStories/" + key))
    }

    func list() throws -> [LocalChatDraft] {
        guard FileManager.default.fileExists(atPath: root.path) else { return [] }
        return try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            .filter { UUID(uuidString: $0.lastPathComponent) != nil }
            .map { try JSONDecoder().decode(LocalChatDraft.self, from: Data(contentsOf: $0.appendingPathComponent("draft.json"))) }
            .sorted { $0.updatedAt > $1.updatedAt }
    }

    func draft(for personID: UUID) throws -> LocalChatDraft? {
        // Retain legacy files. Prefer the member cache, otherwise recover the most
        // recently edited local content belonging to this member only.
        let drafts = try list().filter { $0.personID == personID }
        return drafts.first(where: { $0.id == personID })
            ?? drafts.first(where: { !$0.input.isEmpty || $0.pendingMessageID != nil || !$0.photos.isEmpty })
            ?? drafts.first
    }

    func save(_ draft: LocalChatDraft, photos: [MessagePhoto]) throws {
        var directory = root.appendingPathComponent(draft.id.uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        for photo in photos {
            let path = directory.appendingPathComponent(photo.id.uuidString + ".jpg")
            if !FileManager.default.fileExists(atPath: path.path) {
                try photo.data.write(to: path, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            }
        }
        try JSONEncoder().encode(draft).write(to: directory.appendingPathComponent("draft.json"),
            options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        let retained = Set(draft.photos.map { $0.id.uuidString + ".jpg" })
        // Clean only unreferenced local copies after the new manifest is durable.
        for path in try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            where path.pathExtension == "jpg" && !retained.contains(path.lastPathComponent) {
            try? FileManager.default.removeItem(at: path)
        }
    }

    func photos(for draft: LocalChatDraft) throws -> [MessagePhoto] {
        try draft.photos.map { photo in
            let data = try Data(contentsOf: root.appendingPathComponent(draft.id.uuidString)
                .appendingPathComponent(photo.id.uuidString + ".jpg"))
            return MessagePhoto(id: photo.id, data: data, attachment: photo.attachment)
        }
    }

    func remove(id: UUID) throws {
        let directory = root.appendingPathComponent(id.uuidString)
        if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
    }
}
