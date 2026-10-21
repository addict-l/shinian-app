import SwiftUI

// Wire fields follow contracts/openapi.json. IDs always come from the server.
private struct FamilyDTO: Decodable { let id: UUID }
private struct MemberDTO: Decodable {
    let id: UUID
    let name: String
    let relationship: String
    let birth_date: String?
    var opening_message: MessageDTO?
    var has_chat_history: Bool?
}
private struct SessionDTO: Decodable { let id: UUID; var version: Int?; var information: StoryInformation?; var status: String? }
private struct MessageDTO: Decodable { let id: UUID; let role: String; let content: String; var attachments: [ChatAttachment]? }
private struct ChatDTO: Decodable {
    let session: SessionDTO
    let messages: [MessageDTO]
    let can_generate: Bool
    var generation_offer: GenerationOffer?
    var current_message_ids: [UUID]?
    var readiness: StoryReadiness?
    var snapshot: ChatSnapshot {
        ChatSnapshot(sessionID: session.id, messages: messages.filter { ["user", "assistant"].contains($0.role) }
            .map { ChatMessage(id: $0.id, sender: $0.role == "user" ? .user : .ai, text: $0.content, attachments: $0.attachments ?? []) }, canGenerate: can_generate,
            status: session.status ?? "active", version: session.version ?? 1, information: session.information ?? StoryInformation(), readiness: readiness, generationOffer: generation_offer, currentMessageIDs: current_message_ids)
    }
}
private struct MemoryDTO: Decodable {
    var id: UUID?
    let person_ids: [UUID]
    let title: String
    let raw_content: String
    let summary: String?
    let memory_date: String?
    let location: String?
    var created_at: String?
    var media_urls: [String]?
    var media_assets: [ChatAttachment]?
    var primary_person_id: UUID?
    var source_session_id: UUID?
    var version: Int?
    var information: StoryInformation?
}
private struct DraftDTO: Decodable { let id: UUID; let revision: UUID; let memory: MemoryDTO; var manually_edited: Bool? }

enum APIDate {
    static func day(_ value: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: value)
    }
    static func parseDay(_ value: String?) -> Date? {
        guard let value else { return nil }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)
    }
    static func timestamp(_ value: String?) -> Date? {
        guard var value else { return nil }
        // MySQL stores these server timestamps in UTC without an offset.
        if !value.hasSuffix("Z") && !value.contains("+") { value += "Z" }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }
}

@MainActor final class BackendRepository: FamilyAPI, ChatAPI, MemoryAPI, MemoirAPI {
    static let shared = BackendRepository()
    private let client: APIClient
    private var familyID: UUID?
    private var knownMembers: [MemberDTO] = []
    init(client: APIClient = .local) { self.client = client }
    private func json(_ values: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: values) }
    private func bootstrap() async throws -> UUID {
        if let familyID { return familyID }
        let family = try await client.send(path: "api/v1/local/bootstrap", method: "POST", as: FamilyDTO.self)
        familyID = family.id
        return family.id
    }
    private func member(_ value: MemberDTO, count: Int = 0) -> FamilyMember {
        let date = APIDate.parseDay(value.birth_date)
        return FamilyMember(id: value.id, name: value.name, gender: .unspecified,
                            profileImages: ["person.fill"], memoryCount: count,
                            relationship: value.relationship, birthDate: date,
                            openingMessage: value.opening_message.map { ChatMessage(id: $0.id, sender: .ai, text: $0.content) },
                            hasChatHistory: value.has_chat_history)
    }
    private func memory(_ value: MemoryDTO, draftID: UUID? = nil, image: Data? = nil) throws -> MemoryEvent {
        guard let id = value.id ?? draftID else { throw APIError.decoding }
        let names = value.person_ids.map { id in knownMembers.first { $0.id == id }?.name ?? "家庭成员" }
        var result = MemoryEvent(id: id, personName: names.joined(separator: "、"), personIDs: value.person_ids,
                           date: APIDate.parseDay(value.memory_date), content: value.summary ?? value.raw_content,
                           title: value.title, imageData: image,
                           createdAt: APIDate.timestamp(value.created_at) ?? .distantPast,
                           dateDescription: value.information?.time.value, location: value.information?.place.value ?? value.location)
        result.primaryPersonID = value.primary_person_id; result.sourceSessionID = value.source_session_id; result.version = value.version ?? 1
        result.information = value.information ?? StoryInformation(); result.mediaAssets = value.media_assets ?? []
        return result
    }
    func members() async throws -> [FamilyMember] {
        let id = try await bootstrap()
        knownMembers = try await client.send(path: "api/v1/family-members/", method: "GET",
                                            query: [.init(name: "family_id", value: id.uuidString)], as: [MemberDTO].self)
        let memories: [MemoryDTO] = try await client.send(path: "api/v1/memories/", method: "GET",
            query: [.init(name: "family_id", value: id.uuidString)], as: [MemoryDTO].self)
        return knownMembers.enumerated().map { index, value in
            member(value, count: memories.filter { $0.person_ids.contains(value.id) }.count)
        }
    }
    func addMember(_ draft: FamilyMemberDraft) async throws -> FamilyMember {
        let family = try await bootstrap()
        guard draft.isValid(), let date = draft.birthDate else { throw APIError.server("请完整填写人物信息。") }
        let result = try await client.send(path: "api/v1/family-members/", method: "POST", body: json([
            "family_id": family.uuidString, "client_request_id": draft.requestID.uuidString,
            "name": draft.realName.trimmingCharacters(in: .whitespacesAndNewlines),
            "relationship": draft.relationship.trimmingCharacters(in: .whitespacesAndNewlines), "birth_date": APIDate.day(date)
        ]), as: MemberDTO.self)
        knownMembers.removeAll { $0.id == result.id }; knownMembers.append(result)
        return member(result)
    }
    func deleteMember(id: UUID) async throws {
        _ = try await client.request(path: "api/v1/family-members/\(id.uuidString)", method: "DELETE")
        knownMembers.removeAll { $0.id == id }
    }
    func start(person: FamilyMember, requestID: UUID) async throws -> ChatSnapshot {
        let family = try await bootstrap()
        return try await client.send(path: "api/v1/chat/members/\(person.id)/conversation", method: "POST",
            query: [.init(name: "family_id", value: family.uuidString)], as: ChatDTO.self).snapshot
    }

    func send(sessionID: UUID, text: String, requestID: UUID) async throws -> ChatSnapshot {
        try await send(sessionID: sessionID, text: text, attachmentIDs: [], requestID: requestID)
    }
    func send(sessionID: UUID, text: String, attachmentIDs: [UUID], requestID: UUID) async throws -> ChatSnapshot {
        try await client.send(path: "api/v1/chat/sessions/\(sessionID)/conversation/messages", method: "POST",
            body: json(["content": text, "attachment_ids": attachmentIDs.map(\.uuidString), "client_request_id": requestID.uuidString]), as: ChatDTO.self).snapshot
    }
    func resume(sessionID: UUID) async throws -> ChatSnapshot {
        try await state(sessionID: sessionID)
    }
    func state(sessionID: UUID) async throws -> ChatSnapshot {
        try await client.send(path: "api/v1/chat/sessions/\(sessionID)/conversation", method: "GET", as: ChatDTO.self).snapshot
    }
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data {
        guard attachment.url == "/api/v1/media/\(attachment.id.uuidString.lowercased())" || attachment.url == "/api/v1/media/\(attachment.id.uuidString)" else { throw APIError.invalidResponse }
        return try await client.request(path: String(attachment.url.dropFirst()), method: "GET")
    }
    func removePhoto(sessionID: UUID, id: UUID) async throws {
        _ = try await client.request(path: "api/v1/chat/sessions/\(sessionID)/media/\(id)", method: "DELETE")
    }
    func generate(sessionID: UUID) async throws -> GeneratedMemory {
        let draft = try await client.send(path: "api/v1/chat/sessions/\(sessionID)/draft", method: "POST", as: DraftDTO.self)
        return try generated(draft)
    }
    private func generated(_ draft: DraftDTO) throws -> GeneratedMemory {
        let value = try memory(draft.memory, draftID: draft.id)
        return GeneratedMemory(draftID: draft.id, revision: draft.revision, memory: value,
            preview: EventData(person: value.personName, date: value.dateLabel, title: value.title,
                               content: value.content, location: draft.memory.information?.place.value ?? draft.memory.location ?? "待补充",
                               participants: draft.memory.person_ids.compactMap { id in knownMembers.first { $0.id == id }?.name },
                               emotion: draft.memory.information?.feeling.value ?? "待补充"), manuallyEdited: draft.manually_edited ?? false)
    }
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws {
        guard let image else {
            _ = try await client.request(path: "api/v1/chat/sessions/\(sessionID)/media", method: "DELETE")
            return
        }
        _ = try await uploadPhoto(sessionID: sessionID, image: PhotoCompression.compress(image), requestID: requestID)
    }
    func uploadPhoto(sessionID: UUID, image: Data, requestID: UUID) async throws -> ChatAttachment {
        guard image.count <= 8 * 1024 * 1024 else { throw APIError.server("图片超过 8 MB，请选择较小的图片。") }
        let boundary = "AI-Memories-\(requestID)"
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"memory.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
        body.append(image); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let data = try await client.request(path: "api/v1/chat/sessions/\(sessionID)/media", method: "POST", body: body,
            query: [.init(name: "client_request_id", value: requestID.uuidString)], contentType: "multipart/form-data; boundary=\(boundary)")
        guard let result = try? JSONDecoder().decode(ChatAttachment.self, from: data), result.id == requestID else { throw APIError.invalidResponse }
        return result
    }
    func save(_ draft: GeneratedMemory) async throws -> MemoryEvent {
        let result = try await client.send(path: "api/v1/memory-drafts/\(draft.draftID)/confirm", method: "POST",
            body: json(["revision": draft.revision.uuidString]), as: MemoryDTO.self)
        return try memory(result)
    }
    func list() async throws -> [MemoryEvent] {
        _ = try await members()
        let id = try await bootstrap()
        let values = try await client.send(path: "api/v1/memories/", method: "GET",
            query: [.init(name: "family_id", value: id.uuidString)], as: [MemoryDTO].self)
        var result: [MemoryEvent] = []
        for value in values {
            var image: Data?
            if let path = value.media_urls?.first {
                // Only server-relative media paths are accepted; no arbitrary remote fetches.
                if path.hasPrefix("/api/v1/media/") {
                    image = try? await client.request(path: String(path.dropFirst()), method: "GET")
                }
            }
            result.append(try memory(value, image: image))
        }
        return result
    }
    func getMemory(id: UUID) async throws -> MemoryEvent {
        let value = try await client.send(path: "api/v1/memories/\(id)", method: "GET", as: MemoryDTO.self)
        var cover: Data?
        if let attachment = value.media_assets?.first { cover = try? await loadPhoto(attachment) }
        return try memory(value, image: cover)
    }
    func updateMemory(_ memory: MemoryEvent, edit: MemoryEdit) async throws -> MemoryEvent {
        guard edit.isValid else { throw APIError.server("请检查标题、正文和信息说明。") }
        let family = try await bootstrap()
        func dimension(_ value: InformationDimension) throws -> Any {
            try JSONSerialization.jsonObject(with: JSONEncoder().encode(value))
        }
        let parsed = edit.time.status == .known ? APIDate.parseDay(edit.time.value) : nil
        let exactDate = parsed.flatMap { APIDate.day($0) == edit.time.value ? $0 : nil }
        let result = try await client.send(path: "api/v1/memories/\(memory.id)", method: "PATCH", body: json([
            "family_id": family.uuidString, "version": memory.version, "title": edit.title, "summary": edit.content,
            "time": try dimension(edit.time), "place": try dimension(edit.place), "feeling": try dimension(edit.feeling),
            "memory_date": exactDate.map(APIDate.day) as Any? ?? NSNull(), "media_ids": edit.mediaIDs.map(\.uuidString)
        ]), as: MemoryDTO.self)
        var cover: Data?
        if let attachment = result.media_assets?.first { cover = try? await loadPhoto(attachment) }
        return try self.memory(result, image: cover)
    }
    func deleteMemory(_ memory: MemoryEvent) async throws {
        let family = try await bootstrap()
        _ = try await client.request(path: "api/v1/memories/\(memory.id)", method: "DELETE", query: [
            .init(name: "family_id", value: family.uuidString), .init(name: "version", value: String(memory.version))])
    }
    func uploadMemoryPhoto(id: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment {
        let family = try await bootstrap()
        let boundary = "Memory-\(requestID)"
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"memory.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
        body.append(data); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let response = try await client.request(path: "api/v1/memories/\(id)/media", method: "POST", body: body,
            query: [.init(name: "family_id", value: family.uuidString), .init(name: "client_request_id", value: requestID.uuidString)],
            contentType: "multipart/form-data; boundary=\(boundary)")
        let attachment = try JSONDecoder().decode(ChatAttachment.self, from: response)
        guard attachment.id == requestID else { throw APIError.invalidResponse }
        return attachment
    }
    func discardMemoryPhoto(id: UUID, photoID: UUID) async throws {
        let family = try await bootstrap()
        _ = try await client.request(path: "api/v1/memories/\(id)/media/\(photoID)", method: "DELETE",
            query: [.init(name: "family_id", value: family.uuidString)])
    }
    func getDraft(id: UUID) async throws -> GeneratedMemory {
        try generated(await client.send(path: "api/v1/memory-drafts/\(id)", method: "GET", as: DraftDTO.self))
    }
    func editDraft(_ draft: GeneratedMemory, title: String, content: String) async throws -> GeneratedMemory {
        try generated(await client.send(path: "api/v1/memory-drafts/\(draft.draftID)", method: "PATCH",
            body: json(["revision": draft.revision.uuidString, "title": title, "summary": content]), as: DraftDTO.self))
    }
    func regenerateDraft(_ draft: GeneratedMemory) async throws -> GeneratedMemory {
        try generated(await client.send(path: "api/v1/memory-drafts/\(draft.draftID)/regenerate", method: "POST",
            body: json(["revision": draft.revision.uuidString, "replace_confirmed": true]), as: DraftDTO.self))
    }
    func checkHealth() async throws {
        struct Health: Decodable { let status: String }
        let result = try await client.send(path: "health", method: "GET", as: Health.self)
        guard result.status == "ok" else { throw APIError.invalidResponse }
    }

    private struct BookDTO: Decodable {
        var personId: UUID; var personName: String; var version: Int
        var settings: MemoirSettings; var stories: [MemoryDTO]; var contentRevision: String
    }
    private func book(_ dto: BookDTO) throws -> MemoirSnapshot {
        MemoirSnapshot(personId: dto.personId, personName: dto.personName, version: dto.version,
            settings: dto.settings, stories: try dto.stories.map { try memory($0) }, contentRevision: dto.contentRevision)
    }
    private func bookPath(_ personID: UUID) async throws -> String {
        let family = try await bootstrap()
        return "api/v1/families/\(family)/members/\(personID)/memoir"
    }
    func memoir(personID: UUID) async throws -> MemoirSnapshot {
        try book(await client.send(path: bookPath(personID), method: "GET", as: BookDTO.self))
    }
    func saveMemoir(personID: UUID, request: MemoirSaveRequest) async throws -> MemoirSnapshot {
        try book(await client.send(path: bookPath(personID), method: "PUT", body: JSONEncoder().encode(request), as: BookDTO.self))
    }
    func uploadMemoirCover(personID: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment {
        let path = try await bookPath(personID)
        let boundary = "Cover-\(requestID)"
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cover.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
        body.append(data); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let result = try await client.request(path: path + "/photos", method: "POST", body: body,
            query: [.init(name: "client_request_id", value: requestID.uuidString)], contentType: "multipart/form-data; boundary=\(boundary)")
        let photo = try JSONDecoder().decode(ChatAttachment.self, from: result)
        guard photo.id == requestID else { throw APIError.invalidResponse }; return photo
    }
}
