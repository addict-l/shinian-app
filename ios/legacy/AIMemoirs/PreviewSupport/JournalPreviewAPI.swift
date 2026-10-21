#if DEBUG
import SwiftUI

/// Explicit launch-only fixture. Never selected in normal launches or Release builds.
/// No API calls and no writes to the user's database.
@MainActor final class JournalPreviewAPI: FamilyAPI, ChatAPI, MemoryAPI, MemoirAPI {
    private var books: [UUID: MemoirSnapshot] = [:]
    private var conflictOnce: Bool
    private var drafts: [UUID: GeneratedMemory] = [:]
    private var sessionDrafts: [UUID: UUID] = [:]
    private var draftSources: [UUID: [UUID]] = [:]
    private let pendingReply: Bool
    private let recoveryOffline: Bool
    private let slowOpening: Bool
    private let emptyResume: Bool
    private let slowReply: Bool
    private var people: [FamilyMember]
    private var events: [MemoryEvent]
    private var activePerson: FamilyMember?
    private var session = UUID()
    private var nextSegment = false
    private var segmentStart = 0
    private var conversation: [ChatMessage] = []
    private var offerMessageID: UUID?
    private var automaticOfferUsed = false
    private var photos: [UUID: Data] = [:]
    private var savedDrafts: Set<UUID> = []
    init(familyFilm: Bool = false, emptyState: String? = nil) {
        conflictOnce = emptyState == "memory-conflict"
        pendingReply = emptyState == "chat-pending"
        recoveryOffline = emptyState == "chat-offline"
        slowOpening = emptyState == "chat-opening"
        emptyResume = emptyState == "chat-empty-resume"
        slowReply = emptyState == "chat-slow"
        let values = [("陈建国", "爷爷", "1948-05-16", Gender.male), ("林秀兰", "奶奶", "1950-02-09", Gender.female), ("陈明远", "爸爸", "1976-09-22", Gender.male), ("周静", "妈妈", "1978-03-18", Gender.female)]
        people = values.enumerated().map { index, row in
            FamilyMember(id: UUID(uuidString: String(format: "00000000-0000-0000-0000-%012d", index + 1))!, name: row.0, gender: row.3,
                         memoryCount: index == 0 ? 2 : index == 1 ? 1 : 0,
                         relationship: row.1, birthDate: APIDate.parseDay(row.2))
        }
        events = [
            MemoryEvent(personName: "陈建国", personIDs: [people[0].id], date: nil,
                content: "夕阳把巷子照得很长。爷爷扶着自行车的后座，一遍遍叮嘱我看前面。我用力踩着踏板，总觉得他在身后，就不会摔倒。\n\n骑到巷口，我才发现他早就松开了手。回过头，他站在夕阳里笑着朝我挥手。那是我第一次，一个人骑过那条长巷。",
                title: "那年夏天，爷爷松开了手", imageName: "JournalBicycle", createdAt: APIDate.parseDay("2026-09-11")!, dateDescription: "2006年夏天", location: "老家"),
            MemoryEvent(personName: "林秀兰", personIDs: [people[1].id], date: nil, content: "每次回家，先迎接我的总是那碗热汤。", title: "奶奶厨房里的第一缕香气", createdAt: APIDate.parseDay("2026-09-08")!),
            MemoryEvent(personName: "陈建国", personIDs: [people[0].id], date: nil, content: "爷爷坐在院子里，给我讲他小时候的故事。", title: "院子里的一把旧藤椅", createdAt: APIDate.parseDay("2026-09-01")!)
        ]
        if familyFilm {
            events.append(MemoryEvent(personName: "陈建国、陈明远、周静", personIDs: [people[0].id, people[2].id, people[3].id], date: APIDate.parseDay("2017-01-28"), content: "那一年，我们一起回老家过年。门前还是熟悉的小路，一家人围着桌子，聊到很晚。", title: "一起回老家过年", createdAt: APIDate.parseDay("2026-09-10")!))
            events.append(MemoryEvent(personName: "陈明远", personIDs: [people[2].id], date: APIDate.parseDay("2012-08-01"), content: "爸爸牵着我走过车站，带我去看第一次见到的大海。", title: "爸爸带我去看海", createdAt: APIDate.parseDay("2026-09-09")!))
            // 示例固定排序便于截图和测试；正式数据沿用人物接口返回的顺序。
            people = [people[0], people[2], people[3], people[1]]
        }
        // 空状态仅用于离线 UI 回归，不改动本机服务器数据。
        if emptyState == "home-empty" { people = []; events = [] }
        if emptyState == "home-orphaned" { people = [] }
        if emptyState == "home-people-only" { events = [] }
        if slowOpening {
            people[0].openingMessage = ChatMessage(sender: .ai, text: "爷爷，您想从哪件记得的事开始讲？")
            people[0].hasChatHistory = false
        }
        if emptyResume {
            people[0].hasChatHistory = false
            people[0].memoryCount = 0
            events.removeAll { $0.personIDs.contains(people[0].id) }
        }
        if emptyState == "memoir" {
            for index in events.indices { events[index].primaryPersonID = events[index].personIDs.first }
            let data = UIImage(named: "mock_photo")?.jpegData(compressionQuality: 0.8)
            if let data {
                for index in [0, 2] {
                    for position in 0..<3 {
                        let id = UUID(); photos[id] = data
                        events[index].mediaAssets.append(ChatAttachment(id: id, url: "/api/v1/media/\(id)", position: position))
                    }
                }
            }
            var long = MemoryEvent(personName: people[0].name, personIDs: [people[0].id], date: APIDate.parseDay("1982-06-01"),
                content: Array(repeating: "那天我沿着熟悉的小路回家，路边的树影落在肩上。到了家门口，家里人已经摆好了桌子。我们坐下来慢慢说话，讲起这些年的工作，也讲起小时候的事情。\n\n", count: 28).joined(),
                title: "回家路上的树影，和一顿慢慢吃完的晚饭", createdAt: APIDate.parseDay("2026-09-12")!, location: "老家的院子")
            long.primaryPersonID = people[0].id; events.append(long)
        }

    }
    func members() async throws -> [FamilyMember] { people }
    func addMember(_ draft: FamilyMemberDraft) async throws -> FamilyMember {
        guard draft.isValid() else { throw APIError.server("请填写完整") }
        let person = FamilyMember(name: draft.realName, gender: .unspecified,
                                  relationship: draft.relationship, birthDate: draft.birthDate)
        people.append(person); return person
    }
    func deleteMember(id: UUID) async throws {
        people.removeAll { $0.id == id }
    }
    func list() async throws -> [MemoryEvent] { events }
    func start(person: FamilyMember, requestID: UUID) async throws -> ChatSnapshot {
        activePerson = person
        if nextSegment {
            nextSegment = false; session = UUID(); segmentStart = conversation.count
            offerMessageID = nil; automaticOfferUsed = false
            return try await state(sessionID: session)
        }
        if !conversation.isEmpty { return try await state(sessionID: session) }
        if emptyResume {
            try await Task.sleep(for: .seconds(2))
            conversation = [ChatMessage(sender: .ai, text: "爷爷，您想从哪件记得的事慢慢讲起？")]
            return try await state(sessionID: session)
        }
        if slowOpening {
            try await Task.sleep(for: .seconds(8))
            conversation = person.openingMessage.map { [$0] } ?? []
            return try await state(sessionID: session)
        }
        conversation = [ChatMessage(sender: .ai, text: "您想从哪件记得的事开始讲？"), ChatMessage(sender: .user, text: "小时候我教孙子骑自行车。我扶着后座，后来松开手，他自己骑到了巷口。"), ChatMessage(sender: .ai, text: "您扶着他骑，后来他自己骑到了巷口。您还记得他回头看您时，说了什么吗？")]
        if ProcessInfo.processInfo.environment["AI_MEMORIES_PREVIEW_DELAY"] == "1",
           let data = UIImage(named: "mock_photo")?.jpegData(compressionQuality: 0.8) {
            let id = UUID(); photos[id] = data
            conversation[1].attachments = [ChatAttachment(id: id, url: "/api/v1/media/\(id)")]
        }
        return try await state(sessionID: session)
    }
    func send(sessionID: UUID, text: String, requestID: UUID) async throws -> ChatSnapshot {
        try await send(sessionID: sessionID, text: text, attachmentIDs: [], requestID: requestID)
    }
    func send(sessionID: UUID, text: String, attachmentIDs: [UUID], requestID: UUID) async throws -> ChatSnapshot {
        if conversation.contains(where: { $0.id == requestID }) { return try await state(sessionID: sessionID) }
        let attachments = attachmentIDs.enumerated().map { position, id in ChatAttachment(id: id, url: "/api/v1/media/\(id)", position: position) }
        conversation.append(ChatMessage(id: requestID, sender: .user, text: text, attachments: attachments))
        if pendingReply { throw APIError.timeout }
        if slowReply { try await Task.sleep(for: .seconds(8)) }
        offerMessageID = nil
        let explicit = text.contains("保存") || text.contains("整理")
        let automatic = text.contains("讲完") && !automaticOfferUsed
        let reply = ChatMessage(sender: .ai, text: text.isEmpty ? "照片已保存，您可以继续讲讲与这些照片有关的故事。" : explicit || automatic ? "好的，我们可以先把您讲过的内容整理成草稿，您看过、确认后再保存。" : "您可以慢慢讲，我在听。")
        conversation.append(reply)
        if !text.isEmpty && (explicit || automatic) { offerMessageID = reply.id; automaticOfferUsed = true }
        return try await state(sessionID: sessionID)
    }
    func uploadPhoto(sessionID: UUID, image: Data, requestID: UUID) async throws -> ChatAttachment {
        photos[requestID] = image
        return ChatAttachment(id: requestID, url: "/api/v1/media/\(requestID)")
    }
    func removePhoto(sessionID: UUID, id: UUID) async throws { photos[id] = nil }
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data {
        if ProcessInfo.processInfo.environment["AI_MEMORIES_PREVIEW_DELAY"] == "1" {
            try await Task.sleep(for: .milliseconds(500))
        }
        guard let data = photos[attachment.id] else { throw APIError.httpStatus(404) }
        return data
    }
    func resume(sessionID: UUID) async throws -> ChatSnapshot {
        if recoveryOffline { throw APIError.network }
        return try await state(sessionID: sessionID)
    }
    func state(sessionID: UUID) async throws -> ChatSnapshot {
        if recoveryOffline { throw APIError.network }
        let current = Array(conversation.dropFirst(segmentStart))
        return ChatSnapshot(sessionID: session, messages: Array(conversation.suffix(20)), canGenerate: current.contains { $0.sender == .user && !$0.text.isEmpty }, generationOffer: offerMessageID.map { GenerationOffer(message_id: $0) }, currentMessageIDs: current.map(\.id))
    }
    func generate(sessionID: UUID) async throws -> GeneratedMemory {
        if ProcessInfo.processInfo.environment["AI_MEMORIES_PREVIEW_DELAY"] == "1" {
            try await Task.sleep(for: .milliseconds(500))
        }
        let source = conversation.dropFirst(segmentStart).map(\.id)
        if draftSources[sessionID] == source, let id = sessionDrafts[sessionID], let value = drafts[id] { return value }
        let event = segmentStart == 0 ? events[0] : MemoryEvent(personName: activePerson?.name ?? people[0].name,
            date: nil, content: conversation.dropFirst(segmentStart).filter { $0.sender == .user }.map(\.text).joined(separator: "\n"),
            title: "另一段回忆")
        let person = activePerson ?? people[0]
        let memory = MemoryEvent(personName: person.name, personIDs: [person.id], date: nil, content: event.content, title: event.title, imageName: event.imageName, dateDescription: "2006年夏天", location: "老家")
        let value = GeneratedMemory(draftID: memory.id, revision: UUID(), memory: memory,
            preview: EventData(person: person.name, date: "2006年夏天", title: memory.title, content: memory.content, location: "老家", participants: [person.name], emotion: ""))
        drafts[value.draftID] = value
        sessionDrafts[sessionID] = value.draftID; draftSources[sessionID] = source
        return value
    }
    func getMemory(id: UUID) async throws -> MemoryEvent {
        guard let value = events.first(where: { $0.id == id }) else { throw APIError.httpStatus(404) }
        return value
    }
    private func edited(_ base: MemoryEvent, _ edit: MemoryEdit) -> MemoryEvent {
        var result = MemoryEvent(id: base.id, personName: base.personName, personIDs: base.personIDs,
            date: edit.time.status == .known ? APIDate.parseDay(edit.time.value) : nil, content: edit.content, title: edit.title,
            imageName: edit.mediaIDs.isEmpty ? nil : base.imageName, createdAt: base.createdAt,
            dateDescription: edit.time.value, location: edit.place.value)
        result.primaryPersonID = base.primaryPersonID; result.version = base.version + 1; result.information = base.information
        result.information.time = edit.time; result.information.place = edit.place; result.information.feeling = edit.feeling
        result.mediaAssets = edit.mediaIDs.enumerated().map { ChatAttachment(id: $0.element, url: "/api/v1/media/\($0.element)", position: $0.offset) }
        if let id = edit.mediaIDs.first { result = result.copy(imageData: photos[id]) }
        return result
    }
    func updateMemory(_ memory: MemoryEvent, edit: MemoryEdit) async throws -> MemoryEvent {
        guard let index = events.firstIndex(where: { $0.id == memory.id }) else { throw APIError.httpStatus(404) }
        if conflictOnce {
            conflictOnce = false
            var other = MemoryEdit(events[index]); other.title = "另一台设备修改的标题"
            events[index] = edited(events[index], other)
        }
        guard events[index].version == memory.version else { throw APIError.rejected(409, "回忆已在其他设备更新，本机修改仍保留。") }
        let result = edited(events[index], edit); events[index] = result; return result
    }
    func deleteMemory(_ memory: MemoryEvent) async throws {
        let current = try await getMemory(id: memory.id)
        guard current.version == memory.version else { throw APIError.rejected(409, "请核对最新回忆") }
        events.removeAll { $0.id == memory.id }
    }
    func uploadMemoryPhoto(id: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment {
        photos[requestID] = data; return ChatAttachment(id: requestID, url: "/api/v1/media/\(requestID)")
    }
    func discardMemoryPhoto(id: UUID, photoID: UUID) async throws { photos[photoID] = nil }
    func getDraft(id: UUID) async throws -> GeneratedMemory {
        guard let value = drafts[id] else { throw APIError.httpStatus(404) }; return value
    }
    func editDraft(_ draft: GeneratedMemory, title: String, content: String) async throws -> GeneratedMemory {
        let current = try await getDraft(id: draft.draftID)
        guard current.revision == draft.revision else { throw APIError.rejected(409, "草稿已更新") }
        var edit = MemoryEdit(current.memory); edit.title = title; edit.content = content
        let memory = edited(current.memory, edit)
        let result = GeneratedMemory(draftID: draft.draftID, revision: UUID(), memory: memory,
            preview: EventData(person: memory.personName, date: memory.dateLabel, title: title, content: content, location: memory.location ?? "待补充", participants: [memory.personName], emotion: memory.information.feeling.value ?? ""), manuallyEdited: true)
        drafts[draft.draftID] = result; return result
    }
    func regenerateDraft(_ draft: GeneratedMemory) async throws -> GeneratedMemory {
        let current = try await getDraft(id: draft.draftID)
        guard current.revision == draft.revision else { throw APIError.rejected(409, "草稿已更新") }
        draftSources[session] = nil
        let generated = try await generate(sessionID: session)
        let result = GeneratedMemory(draftID: draft.draftID, revision: UUID(), memory: generated.memory, preview: generated.preview)
        drafts[draft.draftID] = result; sessionDrafts[session] = draft.draftID; return result
    }
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws { }
    func memoir(personID: UUID) async throws -> MemoirSnapshot {
        let person = people.first { $0.id == personID }!
        var value = books[personID] ?? MemoirSnapshot(personId: personID, personName: person.name, version: 0,
            settings: MemoirSettings(title: person.name + "的回忆录"), stories: [], contentRevision: "")
        value.stories = events.filter { $0.primaryPersonID == personID }
        value.contentRevision = "\(value.version)-" + value.stories.map { "\($0.id):\($0.version)" }.joined(separator: ",")
        return value
    }
    func saveMemoir(personID: UUID, request: MemoirSaveRequest) async throws -> MemoirSnapshot {
        var value = try await memoir(personID: personID)
        if value.version == request.version + 1, value.settings == request.settings { return value }
        guard value.version == request.version else { throw APIError.rejected(409, "另一设备已调整回忆录") }
        value.version += 1; value.settings = request.settings; books[personID] = value
        return try await memoir(personID: personID)
    }
    func uploadMemoirCover(personID: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment {
        photos[requestID] = data; return ChatAttachment(id: requestID, url: "/api/v1/media/\(requestID)")
    }
    func save(_ draft: GeneratedMemory) async throws -> MemoryEvent {
        if savedDrafts.insert(draft.draftID).inserted {
            events.insert(draft.memory, at: 0)
            conversation.append(ChatMessage(sender: .ai, text: "《\(draft.memory.title)》已经保存好啦。您还有别的事情想分享吗？"))
        }
        nextSegment = true
        return draft.memory
    }
}
#endif
