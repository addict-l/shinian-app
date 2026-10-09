#if DEBUG
import SwiftUI

/// Explicit launch-only fixture. Never selected in normal launches or Release builds.
/// No API calls and no writes to the user's database.
@MainActor final class JournalPreviewAPI: FamilyAPI, ChatAPI, MemoryAPI {
    private var people: [FamilyMember]
    private var events: [MemoryEvent]
    private var activePerson: FamilyMember?
    private let session = UUID()
    private var conversation: [ChatMessage] = []
    private var savedDrafts: Set<UUID> = []
    init(familyFilm: Bool = false, emptyState: String? = nil) {
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
        conversation = [ChatMessage(sender: .ai, text: "想到\(person.relationship)时，最先浮现在你脑海里的，是怎样的一个画面？"), ChatMessage(sender: .user, text: "小时候爷爷教我骑自行车。他扶着后座，后来偷偷松开手，我居然自己骑到了巷口。"), ChatMessage(sender: .ai, text: "你回头看他的时候，还记得他的表情吗？那天的光线、声音，也可以慢慢说给我听。")]
        return ChatSnapshot(sessionID: session, messages: conversation, canGenerate: true)
    }
    func send(sessionID: UUID, text: String, requestID: UUID) async throws -> ChatSnapshot {
        conversation.append(ChatMessage(id: requestID, sender: .user, text: text))
        conversation.append(ChatMessage(sender: .ai, text: "这段记忆很清晰。还想补充什么细节吗？"))
        return ChatSnapshot(sessionID: session, messages: conversation, canGenerate: true)
    }
    func generate(sessionID: UUID) async throws -> GeneratedMemory {
        let event = events[0]
        let person = activePerson ?? people[0]
        let memory = MemoryEvent(personName: person.name, personIDs: [person.id], date: nil, content: event.content, title: event.title, imageName: event.imageName, dateDescription: "2006年夏天", location: "老家")
        return GeneratedMemory(draftID: memory.id, revision: UUID(), memory: memory,
            preview: EventData(person: person.name, date: "2006年夏天", title: memory.title, content: memory.content, location: "老家", participants: [person.name], emotion: ""))
    }
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws { }
    func save(_ draft: GeneratedMemory) async throws -> MemoryEvent {
        if savedDrafts.insert(draft.draftID).inserted { events.insert(draft.memory, at: 0) }
        return draft.memory
    }
}
#endif
