import Testing
import UIKit
@testable import AIMemoirs

struct JournalDesignTests {
    @Test @MainActor func inspectFontsAndPreviewIsolation() async throws {
        print("JOURNAL_FONTS", UIFont.familyNames.filter { $0.localizedCaseInsensitiveContains("Song") || $0.localizedCaseInsensitiveContains("Hiragino") || $0.localizedCaseInsensitiveContains("PingFang") }.map { [$0: UIFont.fontNames(forFamilyName: $0)] })
        let preview = JournalPreviewAPI()
        let people = try await preview.members()
        let events = try await preview.list()
        #expect(people.count == 4 && events.count == 3)
        #expect(events[0].imageName == "JournalBicycle")
        #expect(events[0].dateLabel == "2006年夏天")
        #expect(Set(events.flatMap(\.personIDs)).count == 2)
    }
    @Test func optionalPresentationMetadataPreservesOldSavedData() throws {
        let event = MemoryEvent(personName: "爷爷", date: nil, content: "原始正文", title: "回忆")
        let encoded = try JSONEncoder().encode(event)
        let decoded = try JSONDecoder().decode(MemoryEvent.self, from: encoded)
        #expect(decoded.dateLabel == "时间待补充")
        #expect(decoded.copy(imageData: Data([1])).content == "原始正文")
    }
}
