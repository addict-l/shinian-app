import Testing
import UIKit
@testable import AIMemoirs

struct FamilyFilmTests {
    @Test @MainActor func chronologyUsesStoryTimeAndKeepsUnknownDatesHonest() async throws {
        let api = JournalPreviewAPI(familyFilm: true)
        let people = try await api.members(), memories = try await api.list()
        let timeline = FamilyFilmTimeline(members: people, memories: memories)
        #expect(timeline.moments.map(\.year) == [2006, 2012, 2017, nil, nil])
        let first = memories[0]
        #expect(first.date == nil && FamilyFilmTimeline.year(for: first) == 2006)
        let ambiguous = MemoryEvent(personName: "爷爷", date: nil, content: "", title: "", dateDescription: "2006年到2010年")
        #expect(FamilyFilmTimeline.year(for: ambiguous) == nil)
        let unknown = MemoryEvent(personName: "爷爷", date: nil, content: "", title: "", createdAt: .now)
        #expect(FamilyFilmTimeline.year(for: unknown) == nil)
    }
    @Test @MainActor func oneSharedMomentAppearsOnAllAndOnlyItsParticipantTracks() async throws {
        let api = JournalPreviewAPI(familyFilm: true)
        let timeline = FamilyFilmTimeline(members: try await api.members(), memories: try await api.list())
        let shared = try #require(timeline.moments.first { $0.year == 2017 })
        #expect(timeline.moments.filter { $0.id == shared.id }.count == 1)
        #expect(timeline.lanes.filter { timeline.contains(shared, in: $0) }.count == 3)
        #expect(Set(timeline.participants(of: shared).map(\.id)) == Set(shared.memory.personIDs))
    }
    @Test @MainActor func missingPeopleNeverCreateExtraFilmRolls() async throws {
        let event = MemoryEvent(personName: "尚未标注", personIDs: [UUID()], date: nil, content: "", title: "老照片")
        let timeline = FamilyFilmTimeline(members: [], memories: [event])
        #expect(timeline.lanes.isEmpty)
        // 不删除原始回忆，它仍可通过「全部回忆」查看；只是不虚构一个人物胶卷。
        #expect(timeline.moments.count == 1)
        let empty = FamilyFilmTimeline(members: [], memories: [])
        #expect(empty.moments.isEmpty && empty.lanes.isEmpty)
    }
    @Test func everyCreatedPersonHasExactlyTheirOwnFrames() throws {
        let people = (0..<24).map { FamilyMember(name: "家人\($0)", gender: .unspecified) }
        let first = MemoryEvent(personName: people[0].name, personIDs: [people[0].id], date: nil, content: "", title: "第一段")
        let shared = MemoryEvent(personName: "共同回忆", personIDs: [people[0].id, people[23].id], date: nil, content: "", title: "团聚")
        let orphan = MemoryEvent(personName: "旧人物", personIDs: [UUID()], date: nil, content: "", title: "旧回忆")
        let timeline = FamilyFilmTimeline(members: people, memories: [first, shared, orphan])
        #expect(timeline.lanes.map(\.person.id) == people.map(\.id))
        #expect(Set(timeline.lanes[0].moments.map(\.id)) == [first.id, shared.id])
        #expect(timeline.lanes[23].moments.map(\.id) == [shared.id])
        #expect(timeline.lanes[1].moments.isEmpty)
        #expect(timeline.lanes.reduce(0) { $0 + $1.moments.count } == 3)
        let afterAdding = FamilyFilmTimeline(members: people, memories: [first, shared, orphan,
            MemoryEvent(personName: people[1].name, personIDs: [people[1].id], date: nil, content: "", title: "新回忆")])
        #expect(afterAdding.lanes[1].moments.count == 1)
        let afterDeleting = FamilyFilmTimeline(members: Array(people.dropFirst()), memories: [first, shared])
        #expect(afterDeleting.lanes.count == 23)
        #expect(afterDeleting.lanes.last?.moments.map(\.id) == [shared.id])
    }
    @Test @MainActor func portraitsPersistByIdentityWithoutNetwork() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let image = UIGraphicsImageRenderer(size: CGSize(width: 30, height: 20)).image { context in
            UIColor.brown.setFill(); context.fill(CGRect(x: 0, y: 0, width: 30, height: 20))
        }
        let id = UUID(), other = UUID()
        let first = FamilyFilmPortraitStore(directory: directory)
        try first.save(try #require(image.pngData()), for: id)
        let second = FamilyFilmPortraitStore(directory: directory); second.load([id, other])
        #expect(second.images[id] != nil && second.images[other] == nil)
    }
}
