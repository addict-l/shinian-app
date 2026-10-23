import XCTest
import CryptoKit
import UIKit
@testable import AIMemoirs

/// Explicitly staged synthetic-family verification in a separate simulator App.
/// No credentials are passed to XCTest arguments, logs, assertions or attachments.
final class LiveCrossPlatformBackendTests: XCTestCase {
    private struct Fixture: Decodable {
        let verification_owner: String
        let base_url: String
        let username: String
        let password: String
        let account_id: UUID
        let family_id: UUID
        let person_id: UUID
        let session_id: UUID
        let memory_ids: [UUID]
    }

    private func sha(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    @MainActor func testOwnedSyntheticFamilyRealLoginRestoreAndBusinessReads() async throws {
        guard Bundle.main.bundleIdentifier == "com.shinian.validation.crossplatform" else {
            throw XCTSkip("Explicit separate simulator verification bundle only")
        }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let input = documents.appendingPathComponent("crossplatform-live-validation.private.json")
        guard FileManager.default.fileExists(atPath: input.path) else {
            throw XCTSkip("Requires the explicitly staged private synthetic-family fixture")
        }
        defer { try? FileManager.default.removeItem(at: input) }
        let permissions = try FileManager.default.attributesOfItem(atPath: input.path)[.posixPermissions] as? NSNumber
        guard let permissions, permissions.intValue & 0o077 == 0 else {
            XCTFail("Private fixture permissions are invalid"); return
        }
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: input))
        guard fixture.verification_owner == "shinian-android-20261021",
              fixture.base_url == "https://aimemory.47-82-83-74.nip.io",
              APIClient.local.baseURL.absoluteString == fixture.base_url,
              fixture.memory_ids.count == 3, !JournalDemo.isPreview else {
            XCTFail("Verification owner, server, expected scope or normal launch gate failed"); return
        }

        do {
            let login = AuthenticationStore()
            await login.login(username: fixture.username, password: fixture.password)
            guard login.isAuthenticated, let session = login.session,
                  session.accountID == fixture.account_id, session.familyID == fixture.family_id else {
                XCTFail("Real login did not return the explicitly owned synthetic family"); return
            }
            let restored = AuthenticationStore()
            await restored.restore()
            guard restored.isAuthenticated, restored.session?.accountID == fixture.account_id,
                  restored.session?.familyID == fixture.family_id else {
                XCTFail("Normal persisted-session restore failed"); return
            }
            let api = BackendRepository()
            try await api.checkHealth()
            let people = try await api.members()
            guard let person = people.first(where: { $0.id == fixture.person_id }), people.count == 1 else {
                XCTFail("Known synthetic person scope changed"); return
            }
            let memories = try await api.list()
            guard Set(memories.map(\.id)) == Set(fixture.memory_ids) else {
                XCTFail("Known synthetic story scope changed"); return
            }
            let rawBytes = try await APIClient.local.request(path: "api/v1/memories/", method: "GET",
                query: [.init(name: "family_id", value: fixture.family_id.uuidString)])
            guard let rawMemories = try JSONSerialization.jsonObject(with: rawBytes) as? [[String: Any]] else {
                XCTFail("Real story response shape changed"); return
            }
            var rawByID: [String: String] = [:]
            for value in rawMemories {
                guard let id = value["id"] as? String, let rawContent = value["raw_content"] as? String else {
                    XCTFail("Real story identity or raw content is absent"); return
                }
                rawByID[id.lowercased()] = rawContent
            }
            guard Set(rawByID.keys) == Set(fixture.memory_ids.map { $0.uuidString.lowercased() }) else {
                XCTFail("Real raw story scope changed"); return
            }
            let book = try await api.memoir(personID: person.id)
            guard Set(book.stories.map(\.id)) == Set(fixture.memory_ids) else {
                XCTFail("Cloud memoir does not contain the known synthetic stories"); return
            }
            let conversation = try await api.state(sessionID: fixture.session_id)
            var photoReports: [[String: Any]] = []
            var inspected = Set<UUID>()
            let lastDualPhoto = conversation.messages.last(where: { $0.attachments.count >= 2 })
            let attachments = memories.flatMap(\.mediaAssets) + (lastDualPhoto?.attachments ?? [])
            for photo in attachments where inspected.insert(photo.id).inserted {
                let bytes = try await api.loadPhoto(photo)
                guard let image = UIImage(data: bytes), image.size.width > 0, image.size.height > 0 else {
                    XCTFail("Authenticated private photo did not decode"); return
                }
                photoReports.append(["id": photo.id.uuidString.lowercased(), "sha256": sha(bytes),
                    "bytes": bytes.count, "width": image.size.width, "height": image.size.height])
            }
            guard memories.allSatisfy({ !$0.mediaAssets.isEmpty && $0.imageData != nil }),
                  !photoReports.isEmpty else {
                XCTFail("Known synthetic stories did not load their authenticated photos"); return
            }
            let report: [String: Any] = [
                "completed": true, "platform": "ios", "verification_owner": fixture.verification_owner,
                "base_url": fixture.base_url, "bundle_id": Bundle.main.bundleIdentifier!,
                "account_id": fixture.account_id.uuidString.lowercased(),
                "family_id": fixture.family_id.uuidString.lowercased(),
                "person_id": person.id.uuidString.lowercased(),
                "person_name_sha256": sha(Data(person.name.utf8)),
                "real_authentication_login": true, "persisted_session_restore": true,
                "normal_launch": !JournalDemo.isPreview, "business_write_count": 0,
                "memories": memories.sorted { $0.id.uuidString < $1.id.uuidString }.map { memory in
                    ["id": memory.id.uuidString.lowercased(), "version": memory.version,
                     "title_sha256": sha(Data(memory.title.utf8)), "content_sha256": sha(Data(memory.content.utf8)),
                     "raw_content_sha256": sha(Data(rawByID[memory.id.uuidString.lowercased()]!.utf8)),
                     "media_ids": memory.mediaAssets.map { $0.id.uuidString.lowercased() }] as [String: Any]
                },
                "memoir_version": book.version, "memoir_content_revision": book.contentRevision,
                "memoir_story_ids": book.stories.map { $0.id.uuidString.lowercased() },
                "session_id": fixture.session_id.uuidString.lowercased(),
                "conversation_message_count": conversation.messages.count,
                "last_dual_photo_message_id": lastDualPhoto?.id.uuidString.lowercased() as Any? ?? NSNull(),
                "last_dual_photo_ids": lastDualPhoto?.attachments.map { $0.id.uuidString.lowercased() } ?? [],
                "photos": photoReports, "recorded_at": ISO8601DateFormatter().string(from: Date())
            ]
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys, .prettyPrinted])
            try data.write(to: documents.appendingPathComponent("crossplatform-live-report.json"), options: .atomic)
            XCTAssertTrue(restored.isAuthenticated)
        } catch {
            // Server error bodies and decoding payloads may contain private data.
            XCTFail("Live verification failed with error category " + String(describing: type(of: error)))
        }
    }
}
