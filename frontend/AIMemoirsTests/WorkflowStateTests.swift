import Foundation
import Testing
@testable import AIMemoirs

@MainActor private final class MemberStub: FamilyAPI {
    var fail = true
    var requests: [UUID] = []
    var person: FamilyMember
    init(person: FamilyMember) { self.person = person }
    func members() async throws -> [FamilyMember] { [person] }
    func addMember(_ draft: FamilyMemberDraft) async throws -> FamilyMember {
        requests.append(draft.requestID)
        if fail { throw APIError.network }
        return person
    }
    func deleteMember(id: UUID) async throws {
        if fail { throw APIError.network }
    }
}
@MainActor private final class ChatStub: ChatAPI {
    let sessionID = UUID()
    var fail = true
    var requestIDs: [UUID] = []
    func start(person: FamilyMember, requestID: UUID) async throws -> ChatSnapshot {
        ChatSnapshot(sessionID: sessionID, messages: [], canGenerate: false)
    }
    func send(sessionID: UUID, text: String, requestID: UUID) async throws -> ChatSnapshot {
        requestIDs.append(requestID)
        if fail { throw APIError.timeout }
        return ChatSnapshot(sessionID: sessionID, messages: [ChatMessage(id: requestID, sender: .user, text: text)], canGenerate: true)
    }
    func generate(sessionID: UUID) async throws -> GeneratedMemory { throw APIError.network }
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws { }
}
@MainActor private struct MemoryStub: MemoryAPI {
    let events: [MemoryEvent]
    let fails: Bool
    func list() async throws -> [MemoryEvent] { events }
    func save(_ draft: GeneratedMemory) async throws -> MemoryEvent {
        if fails { throw APIError.network }
        return draft.memory
    }
}
struct WorkflowStateTests {
    @MainActor private func person(id: UUID = UUID()) -> FamilyMember {
        FamilyMember(id: id, name: "张建国", gender: .unspecified, relationship: "爷爷")
    }
    @Test @MainActor func memberFailureAndRetryKeepIdentity() async {
        let member = person()
        let stub = MemberStub(person: member)
        let store = FamilyMemberStore(api: stub)
        let draft = FamilyMemberDraft(realName: "张建国", relationship: "爷爷", birthDate: APIDate.parseDay("1940-05-12"))
        #expect(await store.add(draft) == nil)
        #expect(store.members.isEmpty && store.errorMessage != nil && !store.isSaving)
        stub.fail = false
        _ = await store.add(draft)
        _ = await store.add(draft)
        #expect(store.members.map(\.id) == [member.id])
        #expect(Set(stub.requests).count == 1)
    }
    @Test @MainActor func deleteRemovesMemberFromStore() async {
        let member = person()
        let stub = MemberStub(person: member)
        stub.fail = false
        let store = FamilyMemberStore(api: stub)
        let draft = FamilyMemberDraft(realName: "张建国", relationship: "爷爷", birthDate: APIDate.parseDay("1940-05-12"))
        _ = await store.add(draft)
        #expect(store.members.map(\.id) == [member.id])
        #expect(await store.delete(member))
        #expect(store.members.isEmpty && store.errorMessage == nil)
    }
    @Test @MainActor func messageTimeoutRetainsRequestIDForRetry() async {
        let stub = ChatStub()
        let model = ChatViewModel(api: stub)
        let member = person()
        #expect(await model.send(text: "爷爷教我骑车", person: member) == nil)
        #expect(!model.canGenerate && model.errorMessage != nil && !model.isLoading)
        stub.fail = false
        let snapshot = await model.send(text: "爷爷教我骑车", person: member)
        #expect(snapshot?.messages.count == 1 && model.canGenerate)
        #expect(stub.requestIDs.count == 2 && Set(stub.requestIDs).count == 1)
    }
    @Test @MainActor func sameNamePeopleAreFilteredByID() async {
        let first = UUID(), second = UUID()
        let event = MemoryEvent(personName: "张建国", personIDs: [first], date: nil, content: "真实内容", title: "爷爷")
        let model = MemoryListViewModel(api: MemoryStub(events: [event], fails: false))
        await model.load()
        #expect(model.getMemoryEvents(for: first).count == 1)
        #expect(model.getMemoryEvents(for: second).isEmpty)
        #expect(event.date == nil && event.dateLabel == "时间待补充")
    }
    @Test @MainActor func failedSaveCannotReportSuccess() async {
        let event = MemoryEvent(personName: "张建国", date: nil, content: "真实内容", title: "爷爷")
        let draft = GeneratedMemory(draftID: UUID(), revision: UUID(), memory: event,
            preview: EventData(person: "张建国", date: "时间待补充", title: "爷爷", content: "真实内容", location: "未提及", participants: [], emotion: ""))
        let model = MemorySaveViewModel(api: MemoryStub(events: [], fails: true))
        #expect(await model.save(draft) == false)
        #expect(model.errorMessage != nil && !model.isSaving)
    }
    @Test func calendarDayAndUTCTimestampAreDistinct() {
        let birthday = APIDate.parseDay("1940-05-12")!
        #expect(APIDate.day(birthday) == "1940-05-12")
        #expect(APIDate.timestamp("2026-09-08T11:30:00.123456") == APIDate.timestamp("2026-09-08T11:30:00.123456Z"))
        #expect(APIDate.parseDay(nil) == nil)
        var draft = FamilyMemberDraft(realName: "张建国", relationship: "爷爷", birthDate: birthday)
        let originalID = draft.requestID
        draft.realName = "张建华"
        #expect(draft.requestID != originalID)
    }
}
