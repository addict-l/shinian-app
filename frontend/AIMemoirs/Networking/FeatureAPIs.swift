import Foundation

struct ChatSnapshot {
    let sessionID: UUID
    let messages: [ChatMessage]
    let canGenerate: Bool
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
    func generate(sessionID: UUID) async throws -> GeneratedMemory
    func upload(sessionID: UUID, image: Data?, requestID: UUID) async throws
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
