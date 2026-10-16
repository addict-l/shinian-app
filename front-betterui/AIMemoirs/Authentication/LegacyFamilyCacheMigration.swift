import Foundation
import CryptoKit

/// Only an authenticated, operator-migrated account may inherit the original family's local files.
@MainActor enum LegacyFamilyCacheMigration {
    static func migrate(_ session: StoredFamilySession, applicationSupport: URL? = nil,
                        documentDirectory: URL? = nil, defaults: UserDefaults = .standard) throws {
        guard session.legacy,
              session.familyID.uuidString.lowercased() == "60d34ec1-aa9d-5d17-8e5e-cdf5831747ba" else { return }
        let marker = "family-auth.migrated." + session.scopeKey
        guard !defaults.bool(forKey: marker) else { return }
        let fm = FileManager.default
        let support = applicationSupport ?? fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let documents = documentDirectory ?? fm.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let oldScope = session.server + "\n" + session.username
        let oldKey = SHA256.hash(data: Data(oldScope.utf8)).map { String(format: "%02x", $0) }.joined()
        for folder in ["PendingStories", "Memoirs"] {
            try copyIfNeeded(support.appendingPathComponent(folder + "/" + oldKey),
                             support.appendingPathComponent(folder + "/" + session.scopeKey))
        }
        let destination = documents.appendingPathComponent("Accounts/" + session.scopeKey)
        try copyIfNeeded(documents.appendingPathComponent("ProfileAvatar.jpg"), destination.appendingPathComponent("ProfileAvatar.jpg"))
        try copyIfNeeded(documents.appendingPathComponent("FamilyPortraits"), destination.appendingPathComponent("FamilyPortraits"))
        if let name = defaults.string(forKey: "journal.displayName"),
           defaults.string(forKey: "journal.displayName." + session.scopeKey) == nil {
            defaults.set(name, forKey: "journal.displayName." + session.scopeKey)
        }
        for (key, value) in defaults.dictionaryRepresentation() where key.hasPrefix("life-outline-input-") || key.hasPrefix("life-outline-request-") {
            let scoped = session.scopeKey + "." + key
            if defaults.object(forKey: scoped) == nil { defaults.set(value, forKey: scoped) }
        }
        defaults.set(true, forKey: marker)
    }
    private static func copyIfNeeded(_ source: URL, _ destination: URL) throws {
        let fm = FileManager.default
        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: source.path, isDirectory: &isDirectory) else { return }
        if isDirectory.boolValue {
            // A previous interrupted copy may have created only part of this directory.
            try fm.createDirectory(at: destination, withIntermediateDirectories: true)
            for child in try fm.contentsOfDirectory(at: source, includingPropertiesForKeys: nil) {
                try copyIfNeeded(child, destination.appendingPathComponent(child.lastPathComponent))
            }
            return
        }
        guard !fm.fileExists(atPath: destination.path) else { return }
        try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fm.copyItem(at: source, to: destination)
    }
}
