import SwiftUI

// Wire fields follow contracts/openapi.json. IDs always come from the server.
private struct FamilyDTO: Decodable { let id: UUID }
private struct MemberDTO: Decodable {
    let id: UUID
    let name: String
    let relationship: String
    let birth_date: String?
}
private struct SessionDTO: Decodable { let id: UUID; var version: Int?; var information: StoryInformation? }
private struct MessageDTO: Decodable { let id: UUID; let role: String; let content: String; var attachments: [ChatAttachment]? }
private struct ChatDTO: Decodable {
    let session: SessionDTO
    let messages: [MessageDTO]
    let can_generate: Bool
    var snapshot: ChatSnapshot {
        ChatSnapshot(sessionID: session.id, messages: messages.filter { ["user", "assistant"].contains($0.role) }
            .map { ChatMessage(id: $0.id, sender: $0.role == "user" ? .user : .ai, text: $0.content, attachments: $0.attachments ?? []) }, canGenerate: can_generate,
            version: session.version ?? 1, information: session.information ?? StoryInformation())
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
    var primary_person_id: UUID?
    var version: Int?
    var information: StoryInformation?
}
private struct DraftDTO: Decodable { let id: UUID; let revision: UUID; let memory: MemoryDTO }

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

@MainActor final class BackendRepository: FamilyAPI, ChatAPI, MemoryAPI {
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
                            relationship: value.relationship, birthDate: date)
    }
    private func memory(_ value: MemoryDTO, draftID: UUID? = nil, image: Data? = nil) throws -> MemoryEvent {
        guard let id = value.id ?? draftID else { throw APIError.decoding }
        let names = value.person_ids.map { id in knownMembers.first { $0.id == id }?.name ?? "家庭成员" }
        var result = MemoryEvent(id: id, personName: names.joined(separator: "、"), personIDs: value.person_ids,
                           date: APIDate.parseDay(value.memory_date), content: value.summary ?? value.raw_content,
                           title: value.title, imageData: image,
                           createdAt: APIDate.timestamp(value.created_at) ?? .distantPast,
                           dateDescription: value.information?.time.value, location: value.information?.place.value ?? value.location)
        result.primaryPersonID = value.primary_person_id; result.version = value.version ?? 1
        result.information = value.information ?? StoryInformation()
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
        let session = try await client.send(path: "api/v1/chat/sessions", method: "POST", body: json([
            "family_id": family.uuidString, "primary_person_id": person.id.uuidString,
            "title": "与\(person.name)的回忆", "client_request_id": requestID.uuidString
        ]), as: SessionDTO.self)
        return try await client.send(path: "api/v1/chat/sessions/\(session.id)/start", method: "POST", as: ChatDTO.self).snapshot
    }
    func send(sessionID: UUID, text: String, requestID: UUID) async throws -> ChatSnapshot {
        try await client.send(path: "api/v1/chat/sessions/\(sessionID)/messages", method: "POST",
            body: json(["content": text, "client_request_id": requestID.uuidString]), as: ChatDTO.self).snapshot
    }
    func generate(sessionID: UUID) async throws -> GeneratedMemory {
        let draft = try await client.send(path: "api/v1/chat/sessions/\(sessionID)/draft", method: "POST", as: DraftDTO.self)
        let value = try memory(draft.memory, draftID: draft.id)
        return GeneratedMemory(draftID: draft.id, revision: draft.revision, memory: value,
            preview: EventData(person: value.personName, date: value.dateLabel, title: value.title,
                               content: value.content, location: draft.memory.location ?? "未提及",
                               participants: draft.memory.person_ids.compactMap { id in knownMembers.first { $0.id == id }?.name }, emotion: ""))
    }
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws {
        guard let image else {
            _ = try await client.request(path: "api/v1/chat/sessions/\(sessionID)/media", method: "DELETE")
            return
        }
        guard let decoded = UIImage(data: image), let jpeg = decoded.jpegData(compressionQuality: 0.8) else {
            throw APIError.server("图片无法读取，请重新选择。")
        }
        guard jpeg.count <= 8 * 1024 * 1024 else { throw APIError.server("图片超过 8 MB，请选择较小的图片。") }
        let boundary = "AI-Memories-\(requestID)"
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"memory.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
        body.append(jpeg); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        _ = try await client.request(path: "api/v1/chat/sessions/\(sessionID)/media", method: "POST", body: body,
            query: [.init(name: "client_request_id", value: requestID.uuidString)], contentType: "multipart/form-data; boundary=\(boundary)")
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
    func checkHealth() async throws {
        struct Health: Decodable { let status: String }
        let result = try await client.send(path: "health", method: "GET", as: Health.self)
        guard result.status == "ok" else { throw APIError.invalidResponse }
    }
}
