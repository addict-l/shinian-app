import Foundation

struct ChatSnapshot {
    let sessionID: UUID
    let messages: [ChatMessage]
    let canGenerate: Bool
    var version: Int = 1
    var information = StoryInformation()
}
struct GeneratedMemory {
    let draftID: UUID
    let revision: UUID
    let memory: MemoryEvent
    let preview: EventData
}
@MainActor protocol FamilyAPI {
    func members() async throws -> [FamilyMember]
    func addMember(_ draft: FamilyMemberDraft) async throws -> FamilyMember
    func deleteMember(id: UUID) async throws
}
@MainActor protocol ChatAPI {
    func start(person: FamilyMember, requestID: UUID) async throws -> ChatSnapshot
    func send(sessionID: UUID, text: String, requestID: UUID) async throws -> ChatSnapshot
    func send(sessionID: UUID, text: String, attachmentIDs: [UUID], requestID: UUID) async throws -> ChatSnapshot
    func uploadPhoto(sessionID: UUID, image: Data, requestID: UUID) async throws -> ChatAttachment
    func removePhoto(sessionID: UUID, id: UUID) async throws
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data
    func state(sessionID: UUID) async throws -> ChatSnapshot
    func generate(sessionID: UUID) async throws -> GeneratedMemory
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws
}
extension ChatAPI {
    func send(sessionID: UUID, text: String, attachmentIDs: [UUID], requestID: UUID) async throws -> ChatSnapshot {
        guard attachmentIDs.isEmpty else { throw APIError.contractUnavailable }
        return try await send(sessionID: sessionID, text: text, requestID: requestID)
    }
    func uploadPhoto(sessionID: UUID, image: Data, requestID: UUID) async throws -> ChatAttachment { throw APIError.contractUnavailable }
    func removePhoto(sessionID: UUID, id: UUID) async throws { throw APIError.contractUnavailable }
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data { throw APIError.contractUnavailable }
    func state(sessionID: UUID) async throws -> ChatSnapshot { throw APIError.contractUnavailable }
}
@MainActor protocol MemoryAPI {
    func list() async throws -> [MemoryEvent]
    func save(_ draft: GeneratedMemory) async throws -> MemoryEvent
}
protocol ProfileCapabilities {
    func backup() async throws
    func exportData() async throws -> URL
    func shareTree(format: String) async throws -> URL
}
struct UnavailableBackend: ProfileCapabilities {
    func backup() async throws { throw APIError.contractUnavailable }
    func exportData() async throws -> URL { throw APIError.contractUnavailable }
    func shareTree(format: String) async throws -> URL { throw APIError.contractUnavailable }
}
