import Testing
@testable import AIMemoirs

struct FamilyMemoryCollectionTests {
    @Test func orphanedMemoriesDoNotAppearInCurrentFamily() {
        let removed = FamilyMember(name: "爷爷", gender: .male)
        let active = FamilyMember(name: "爷爷", gender: .male)
        let old = MemoryEvent(personName: removed.name, personIDs: [removed.id], date: nil, content: "旧正文", title: "旧回忆")
        let shared = MemoryEvent(personName: "家人", personIDs: [removed.id, active.id], date: nil, content: "共同正文", title: "共同回忆")
        let noPeople = FamilyMemoryCollection(members: [], memories: [old, shared])
        #expect(noPeople.events.isEmpty && noPeople.participatingPeopleCount == 0)
        let remaining = FamilyMemoryCollection(members: [active], memories: [old, shared])
        #expect(remaining.events.map(\.id) == [shared.id])
        #expect(remaining.participatingPeopleCount == 1)
        #expect(FamilyMemoryCollection(members: [active], memories: []).events.isEmpty)
    }
}
