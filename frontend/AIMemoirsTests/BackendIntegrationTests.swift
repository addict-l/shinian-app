import Foundation
import UIKit
import Testing
@testable import AIMemoirs

/// Explicitly selected live test; requires the local backend and real AI credentials.
struct BackendIntegrationTests {
    @Test @MainActor func realAdapterUploadsAndReloadsPhoto() async throws {
        guard ProcessInfo.processInfo.environment["AI_MEMORIES_LIVE_TESTS"] == "1" else { return }
        let repository = BackendRepository()
        let person = try await repository.addMember(FamilyMemberDraft(
            realName: "附件联调" + String(Int(Date().timeIntervalSince1970)), relationship: "爷爷",
            birthDate: APIDate.parseDay("1940-05-12")))
        let opening = try await repository.start(person: person, requestID: UUID())
        #expect(!opening.messages.isEmpty)
        let reply = try await repository.send(sessionID: opening.sessionID,
            text: "爷爷教我骑自行车，确切日期已经记不清了。我想把这份回忆珍藏起来。", requestID: UUID())
        #expect(reply.canGenerate)
        let image = UIGraphicsImageRenderer(size: CGSize(width: 48, height: 48)).image { context in
            UIColor.systemBlue.setFill(); context.fill(CGRect(x: 0, y: 0, width: 48, height: 48))
        }.jpegData(compressionQuality: 0.8)!
        try await repository.upload(sessionID: opening.sessionID, image: image, requestID: UUID())
        let draft = try await repository.generate(sessionID: opening.sessionID)
        #expect(draft.memory.date == nil)
        let saved = try await repository.save(draft)
        let repeated = try await repository.save(draft)
        #expect(saved.id == repeated.id)
        // A new adapter has no in-memory member/image cache.
        let reloaded = try await BackendRepository().list()
        let event = try #require(reloaded.first { $0.id == saved.id })
        #expect(event.personIDs.contains(person.id) && event.date == nil)
        #expect(event.imageData.flatMap(UIImage.init(data:)) != nil)
    }
}
