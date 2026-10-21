#if DEBUG
import SwiftUI

/// 离线演示数据源：人物、对话、回忆和回忆录都在本机模拟，不发出网络请求。
@MainActor final class JournalDemoAPI: FamilyAPI, ChatAPI, MemoryAPI, MemoirAPI {
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
    private let scrollFixture: Bool
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
    private var careLife: LifeOverview?
    private var careModule = ""
    private var careCommands: Set<UUID> = []
    init(familyFilm: Bool = false, emptyState: String? = nil) {
        conflictOnce = emptyState == "memory-conflict"
        pendingReply = emptyState == "chat-pending"
        recoveryOffline = emptyState == "chat-offline"
        slowOpening = emptyState == "chat-opening"
        emptyResume = emptyState == "chat-empty-resume"
        slowReply = emptyState == "chat-slow"
        scrollFixture = emptyState == "chat-scroll" || emptyState == "care-life-scroll"
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
        loadDesignMockup(screen: emptyState)
        if let screen = emptyState, screen.hasPrefix("care-life") {
            careLife = careLifeFixture(status: screen == "care-life-topics" ? "confirmed" : screen == "care-life-question" ? "collecting" : "review")
        }
        if scrollFixture {
            conversation = (1...13).map { index in
                ChatMessage(sender: index.isMultiple(of: 2) ? .user : .ai,
                    text: "本地旧记录 \(index)：那年家门口有一棵树。我们在树下说话，记住了生活里的小事。")
            }
            if let previous = careLife {
                careLife = LifeOverview(version: 1, status: "collecting", required: true, paused: false,
                    fields: previous.fields, turns: conversation.map { LifeTurn(id: $0.id, role: $0.sender == .ai ? "assistant" : "user", content: $0.text) },
                    question_id: "home", question: conversation.last?.text, question_number: 1, total_questions: 7,
                    confirmed_version: nil, pending_request_id: nil, pending_action: nil)
            }
        }
        if emptyState == "memoir-fixture" {
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
    private var mockupConversation: [ChatMessage]?
    private var mockupDraft: MemoryEvent?

    /// 设计稿截图用示例数据：人物、照片与 18 段回忆与「拾年 · 温馨版」界面设计一致。
    private func loadDesignMockup(screen: String?) {
        let rows: [(String, String, String, Gender, String?)] = [
            ("陈建国", "爷爷", "1946-03-12", .male, "DesignPhoto-grandpa"), ("李秀英", "外婆", "1949-08-02", .female, "DesignPhoto-grandma"),
            ("王丽华", "妈妈", "1972-11-20", .female, "DesignPhoto-mom"), ("陈志明", "爸爸", "1970-05-06", .male, nil)]
        people = rows.enumerated().map { index, row in
            FamilyMember(id: UUID(uuidString: String(format: "00000000-0000-0000-0000-%012d", index + 1))!, name: row.0, gender: row.3,
                         profileImages: row.4.map { [$0] } ?? [], relationship: row.1, birthDate: APIDate.parseDay(row.2))
        }
        if screen == "home-empty" { people = [] }
        let grandpa = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!, grandma = UUID(uuidString: "00000000-0000-0000-0000-000000000002")!
        let mom = UUID(uuidString: "00000000-0000-0000-0000-000000000003")!, dad = UUID(uuidString: "00000000-0000-0000-0000-000000000004")!
        let names = [grandpa: "陈建国", grandma: "李秀英", mom: "王丽华", dad: "陈志明"]
        var day = 0
        func memory(_ person: UUID, _ title: String, _ when: String?, _ place: String? = nil, photo: String? = nil, date: String? = nil,
                    feeling: String? = nil, _ content: String) -> MemoryEvent {
            day += 1
            var value = MemoryEvent(personName: names[person]!, personIDs: [person], date: date.flatMap(APIDate.parseDay), content: content, title: title,
                                    imageName: photo.map { "DesignPhoto-" + $0 }, createdAt: Date(timeIntervalSince1970: 1_790_000_000 - Double(day) * 86_400),
                                    dateDescription: when, location: place)
            value.primaryPersonID = person
            if let photo, let data = UIImage(named: "DesignPhoto-" + photo)?.jpegData(compressionQuality: 0.85) {
                let id = UUID(); photos[id] = data
                value.mediaAssets = [ChatAttachment(id: id, url: "/api/v1/media/\(id)", position: 0)]
            }
            if let feeling { value.information.feeling = InformationDimension(status: .known, value: feeling) }
            return value
        }
        events = screen == "home-empty" ? [] : [
            memory(grandma, "葡萄架下的那把蒲扇", "2008年夏天", "老家院子", photo: "summer", feeling: "想念",
                   "那年夏天特别热，院子里的葡萄架投下一片斑驳的阴凉。外婆坐在门槛上，一手摇着那把旧蒲扇，一手轻轻拍着我的背。西瓜在井水里冰了一下午，她总把最中间那一块留给我……"),
            memory(dad, "爸爸扶着我学骑车", "1998年秋天", "厂区大道", photo: "bike", "“别回头，往前看。”那条落满银杏叶的路，爸爸扶着后座跑了一路……"),
            memory(grandpa, "除夕夜里的那枚硬币", "2003年除夕", "老家厨房", photo: "dinner", date: "2003-01-31", feeling: "温暖",
                   "每年除夕，爷爷都会早早系上那条洗得发白的围裙，在厨房里擀皮、调馅。他总会趁我们不注意，把一枚擦得锃亮的硬币悄悄包进饺子里。那一年，硬币落在了我的碗里，爷爷笑着说：“来年，咱家的小福星就是你。”"),
            memory(grandpa, "窗台上的那盆茉莉", "1995年春天", photo: "grandpa", "爷爷每天清晨都给窗台上的茉莉浇水，花开的时候，满屋子都是香气。"),
            memory(grandpa, "银杏路上的二八自行车", "1988年秋天", "厂区大道", photo: "bike", "爷爷骑着那辆二八自行车，载着我穿过落满银杏叶的厂区大道。"),
            memory(grandpa, "那年的团圆饭", "2008年除夕", photo: "dinner", "一大家子围坐在圆桌旁，爷爷举起酒杯，说今年最高兴的是人都到齐了。"),
            memory(grandma, "外婆的老花镜", "2001年冬天", photo: "grandma", "外婆戴着老花镜给我缝棉袄，针脚细细密密。"),
            memory(mom, "妈妈的五十岁生日", "2015年", photo: "mom", "那天妈妈穿上了新买的毛衣，笑得像个小姑娘。"),
            memory(mom, "妈妈送我去上学", "1998年秋天", photo: "bike", "妈妈推着自行车送我到校门口，一直看着我走进教室。"),
            memory(mom, "妈妈的拿手红烧肉", "1992年", photo: "dinner", "每到周末，妈妈都会做一锅红烧肉，整栋楼都闻得到香味。"),
            memory(grandpa, "爷爷的收音机", "1982年", "老屋", "爷爷的收音机总是调到戏曲频道，他跟着哼，我在旁边打瞌睡。"),
            memory(grandma, "外婆的桂花糕", "1996年秋天", "老家院子", "桂花开的时候，外婆会把花收起来，做成一笼甜甜的桂花糕。"),
            memory(grandpa, "老屋门前的石榴树", "1979年秋天", "老屋门前", "石榴熟了，爷爷踩着板凳摘下最大的一个，掰开分给我们。"),
            memory(grandma, "井边的西瓜", "1993年夏天", "老家院子", "外婆把西瓜放进井水里，等我们放学回家正好冰凉。"),
            memory(grandpa, "爷爷写给奶奶的信", "1970年", "工厂宿舍", "那些信被奶奶收在铁盒子里，字迹工整，每一封都写着“一切都好”。"),
            memory(grandma, "外婆教我包粽子", "1990年", "老家厨房", "外婆的手很巧，三两下就包好一个，我的总是漏米。"),
            memory(grandpa, "第一次进城", "1965年春天", "县城", "爷爷说，他第一次进城，是挑着两担米走了一整天。"),
            memory(mom, "妈妈的第一份工作", nil, nil, "妈妈说，第一个月的工资，她全都寄回了家。")
        ]
        if let data = UIImage(named: "DesignPhoto-dinner")?.jpegData(compressionQuality: 0.85), let portrait = UIImage(named: "DesignPhoto-grandpa")?.jpegData(compressionQuality: 0.85) {
            let first = UUID(), second = UUID(); photos[first] = data; photos[second] = portrait
            var user = ChatMessage(sender: .user, text: "每年除夕，爷爷都会亲手包饺子，还会偷偷在一个里面放一枚硬币。")
            user.attachments = [ChatAttachment(id: first, url: "/api/v1/media/\(first)", position: 0), ChatAttachment(id: second, url: "/api/v1/media/\(second)", position: 1)]
            mockupConversation = [ChatMessage(sender: .ai, text: "早上好。说起爷爷，你最先想到的是什么画面？是他常坐的那把藤椅，还是他做的某一道菜？"), user,
                                  ChatMessage(sender: .ai, text: "真温暖。那一年是谁吃到了硬币？爷爷当时说了什么？")]
        }
        for person in people {
            guard let name = person.profileImages.first, let data = UIImage(named: name)?.jpegData(compressionQuality: 0.9) else { continue }
            let id = UUID(); photos[id] = data
            var settings = MemoirSettings(title: person.name + "的回忆录")
            settings.subtitle = "愿平凡的日子，被好好记住"
            settings.coverTemplate = .photo
            settings.coverPhotos = [MemoirCoverPhoto(id: id)]
            books[person.id] = MemoirSnapshot(personId: person.id, personName: person.name, version: 0,
                settings: settings, stories: [], contentRevision: "")
        }
        mockupDraft = events.first { $0.title == "除夕夜里的那枚硬币" }
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
        if let activePerson, activePerson.id != person.id {
            conversation = []; session = UUID(); segmentStart = 0; nextSegment = false
            offerMessageID = nil; automaticOfferUsed = false
        }
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
        if person.relationship == "爷爷", let mockupConversation {
            conversation = mockupConversation; offerMessageID = mockupConversation.last?.id
            return try await state(sessionID: session)
        }
        let role = person.relationship.isEmpty ? person.name : person.relationship
        conversation = [ChatMessage(sender: .ai, text: "说起\(role)，你最先想到的是哪一个画面？可以从一件平凡的小事慢慢讲起。")]

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
        if scrollFixture {
            try await Task.sleep(for: .seconds(text == "history reply" ? 8 : 3))
            conversation.append(ChatMessage(sender: .ai, text: scrollReply(to: text)))
            return try await state(sessionID: sessionID)
        }
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
        var snapshot = ChatSnapshot(lifeOverview: careLife, sessionID: session, messages: Array(conversation.suffix(20)), canGenerate: !scrollFixture && current.contains { $0.sender == .user && !$0.text.isEmpty }, generationOffer: offerMessageID.map { GenerationOffer(message_id: $0) }, currentMessageIDs: current.map(\.id))
        if careLife != nil { snapshot.information.guided_interview = .init(module: careModule.isEmpty ? "childhood" : careModule, module_selected: !careModule.isEmpty, topic_index: 0, phase: "topic") }
        return snapshot
    }
    /// 只在显式 Debug 预览入口启用；正式启动仍使用 BackendRepository。
    private let careQuestions = ["您小时候，住在什么样的地方？", "后来在哪里读书或学手艺？", "年轻时做过哪些工作？", "后来工作和生活有哪些变化？", "您最想聊聊哪位家人？", "有没有一次生活变化，您一直记得？", "您现在的日子是怎样的？"]
    private func careLifeFixture(status: String) -> LifeOverview {
        let ids = ["home", "learning", "early_work", "later_work", "family", "changes", "present"]
        let answers = ["小时候住在乡下，和父母一起生活。", "在村里的学校读书。", "年轻时在镇上的工厂工作。", "后来仍在工厂做工。", "我最牵挂的是家人。", "后来搬到了镇上。", "现在喜欢散步、养花。"]
        let turns = status == "collecting" ? [LifeTurn(id: UUID(), role: "assistant", content: careQuestions[0])] :
            ids.indices.flatMap { [LifeTurn(id: UUID(), role: "assistant", content: careQuestions[$0]), LifeTurn(id: UUID(), role: "user", content: answers[$0])] }
        return LifeOverview(version: 1, status: status, required: true, paused: false,
            fields: ids.indices.map { LifeField(topic_id: ids[$0], status: status == "collecting" ? "pending" : "known", evidence: status == "collecting" ? [] : [LifeQuote(message_id: turns[$0 * 2 + 1].id, quote: answers[$0])]) },
            turns: turns, question_id: status == "collecting" ? "home" : nil, question: status == "collecting" ? careQuestions[0] : nil,
            question_number: status == "collecting" ? 1 : 7, total_questions: 7, confirmed_version: status == "confirmed" ? 1 : nil, pending_request_id: nil, pending_action: nil)
    }
    func lifeAction(sessionID: UUID, command: LifeCommand) async throws -> ChatSnapshot {
        guard let previous = careLife else { throw APIError.contractUnavailable }
        if careCommands.contains(command.client_request_id) { return try await state(sessionID: sessionID) }
        guard command.expected_version == previous.version else { throw APIError.rejected(409, "经历已更新，请重新核对。") }
        if scrollFixture && command.action == "answer" {
            try await Task.sleep(for: .seconds(command.text == "history reply" ? 8 : 3))
            let reply = scrollReply(to: command.text)
            careLife = LifeOverview(version: previous.version + 1, status: "collecting", required: true, paused: false,
                fields: previous.fields, turns: previous.turns + [LifeTurn(id: command.client_request_id, role: "user", content: command.text), LifeTurn(id: UUID(), role: "assistant", content: reply)],
                question_id: "home", question: reply, question_number: 1, total_questions: 7,
                confirmed_version: nil, pending_request_id: nil, pending_action: nil)
            careCommands.insert(command.client_request_id)
            return try await state(sessionID: sessionID)
        }
        var status = previous.status; var fields = previous.fields; var turns = previous.turns
        var number = previous.question_number; var paused = previous.paused
        switch command.action {
        case "begin": status = "collecting"; number = 1
        case "confirm": status = "confirmed"
        case "pause": paused = true
        case "answer":
            let index = min(6, max(0, number - 1)); let id = UUID()
            turns.append(LifeTurn(id: id, role: "user", content: command.text))
            fields[index] = LifeField(topic_id: fields[index].topic_id, status: command.text == "跳过" ? "skipped" : "known", evidence: command.text == "跳过" ? [] : [LifeQuote(message_id: id, quote: command.text)])
            if number == 7 { status = "review" } else { number += 1; turns.append(LifeTurn(id: UUID(), role: "assistant", content: careQuestions[number - 1])) }
        case "correct":
            if let index = fields.firstIndex(where: { $0.topic_id == command.topic_id }) {
                let id = UUID(); turns.append(LifeTurn(id: id, role: "user", content: command.text))
                fields[index] = LifeField(topic_id: fields[index].topic_id, status: "known", evidence: [LifeQuote(message_id: id, quote: command.text)]); status = "review"
            }
        default: throw APIError.contractUnavailable
        }
        careCommands.insert(command.client_request_id)
        careLife = LifeOverview(version: previous.version + 1, status: status, required: true, paused: paused, fields: fields, turns: turns,
            question_id: status == "collecting" ? fields[number - 1].topic_id : nil, question: status == "collecting" ? careQuestions[number - 1] : nil,
            question_number: number, total_questions: 7, confirmed_version: status == "confirmed" ? previous.version + 1 : nil, pending_request_id: nil, pending_action: nil)
        return try await state(sessionID: sessionID)
    }
    func selectInterview(sessionID: UUID, module: String, version: Int) async throws -> ChatSnapshot {
        guard careLife?.status == "confirmed" else { throw APIError.contractUnavailable }
        careModule = module; conversation = [ChatMessage(sender: .ai, text: "说起这段日子，您最先想起的是哪一个画面？")]
        return try await state(sessionID: sessionID)
    }
    private func scrollReply(to text: String) -> String {
        if text.contains("长回复") {
            return (1...70).map { "长回复第 \($0) 行：这是完全本地的界面测试内容。" }.joined(separator: "\n") + "\n长回复已经结束。"
        }
        return "本地回复：\(text)"
    }
    func generate(sessionID: UUID) async throws -> GeneratedMemory {
        if ProcessInfo.processInfo.environment["AI_MEMORIES_PREVIEW_DELAY"] == "1" {
            try await Task.sleep(for: .milliseconds(500))
        }
        let source = conversation.dropFirst(segmentStart).map(\.id)
        if draftSources[sessionID] == source, let id = sessionDrafts[sessionID], let value = drafts[id] { return value }
        let person = activePerson ?? people[0]
        let mock = careLife == nil && segmentStart == 0 && person.relationship == "爷爷" ? mockupDraft : nil
        let narration = conversation.dropFirst(segmentStart).filter { $0.sender == .user }.map(\.text).joined(separator: "\n\n")
        var memory = MemoryEvent(personName: person.name, personIDs: [person.id], date: nil,
            content: mock?.content ?? narration, title: mock?.title ?? "关于\(person.relationship.isEmpty ? person.name : person.relationship)的一段回忆",
            imageName: mock?.imageName, dateDescription: mock?.dateDescription, location: mock?.location)
        memory.primaryPersonID = person.id
        if let mock { memory.information = mock.information }
        let value = GeneratedMemory(draftID: memory.id, revision: UUID(), memory: memory,
            preview: EventData(person: person.name, date: memory.dateDescription ?? "", title: memory.title, content: memory.content, location: memory.location ?? "", participants: [person.name], emotion: memory.information.feeling.value ?? ""))
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
            imageName: edit.mediaIDs.isEmpty && !base.mediaAssets.isEmpty ? nil : base.imageName, createdAt: base.createdAt,
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
        try await editDraft(draft, title: title, content: content, time: MemoryEdit(draft.memory).time)
    }
    func editDraft(_ draft: GeneratedMemory, title: String, content: String, time: InformationDimension) async throws -> GeneratedMemory {
        let current = try await getDraft(id: draft.draftID)
        guard current.revision == draft.revision else { throw APIError.rejected(409, "草稿已更新") }
        var edit = MemoryEdit(current.memory); edit.title = title; edit.content = content; edit.time = time
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
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws { if let image { photos[requestID] = image } }
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
