import Foundation

struct ChatSnapshot: Codable {
    var lifeOverview: LifeOverview? = nil
    let sessionID: UUID
    var messages: [ChatMessage]
    let canGenerate: Bool
    var status: String = "active"
    var version: Int = 1
    var information = StoryInformation()
    var readiness: StoryReadiness? = nil
    var generationOffer: GenerationOffer? = nil
    var currentMessageIDs: [UUID]? = nil
    var reviewRequest: GenerationOffer? = nil
}
struct GeneratedMemory {
    let draftID: UUID
    let revision: UUID
    let memory: MemoryEvent
    let preview: EventData
    var manuallyEdited = false
    var timeReviewFrom: InformationDimension? = nil
    var hasNewNarration = false
}
@MainActor protocol FamilyAPI {
    func members() async throws -> [FamilyMember]
    func addMember(_ draft: FamilyMemberDraft) async throws -> FamilyMember
    func deleteMember(id: UUID) async throws
}
@MainActor protocol ChatAPI {
    func lifeAction(sessionID: UUID, command: LifeCommand) async throws -> ChatSnapshot
    func selectInterview(sessionID: UUID, module: String, version: Int) async throws -> ChatSnapshot
    func resume(sessionID: UUID) async throws -> ChatSnapshot

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
    func lifeAction(sessionID: UUID, command: LifeCommand) async throws -> ChatSnapshot { throw APIError.contractUnavailable }
    func selectInterview(sessionID: UUID, module: String, version: Int) async throws -> ChatSnapshot { throw APIError.contractUnavailable }
    func resume(sessionID: UUID) async throws -> ChatSnapshot { try await state(sessionID: sessionID) }
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
    func getMemory(id: UUID) async throws -> MemoryEvent
    func updateMemory(_ memory: MemoryEvent, edit: MemoryEdit) async throws -> MemoryEvent
    func deleteMemory(_ memory: MemoryEvent) async throws
    func uploadMemoryPhoto(id: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment
    func discardMemoryPhoto(id: UUID, photoID: UUID) async throws
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data
    func getDraft(id: UUID) async throws -> GeneratedMemory
    func editDraft(_ draft: GeneratedMemory, title: String, content: String) async throws -> GeneratedMemory
    func editDraft(_ draft: GeneratedMemory, title: String, content: String, time: InformationDimension) async throws -> GeneratedMemory
    func previewDraftTime(_ draft: GeneratedMemory, input: TimePreviewInput) async throws -> TimePreview
    func previewMemoryTime(_ memory: MemoryEvent, input: TimePreviewInput) async throws -> TimePreview
    func regenerateDraft(_ draft: GeneratedMemory) async throws -> GeneratedMemory
}
extension MemoryAPI {
    func getMemory(id: UUID) async throws -> MemoryEvent { throw APIError.contractUnavailable }
    func updateMemory(_ memory: MemoryEvent, edit: MemoryEdit) async throws -> MemoryEvent { throw APIError.contractUnavailable }
    func deleteMemory(_ memory: MemoryEvent) async throws { throw APIError.contractUnavailable }
    func uploadMemoryPhoto(id: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment { throw APIError.contractUnavailable }
    func discardMemoryPhoto(id: UUID, photoID: UUID) async throws { throw APIError.contractUnavailable }
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data { throw APIError.contractUnavailable }
    func getDraft(id: UUID) async throws -> GeneratedMemory { throw APIError.contractUnavailable }
    func editDraft(_ draft: GeneratedMemory, title: String, content: String) async throws -> GeneratedMemory { throw APIError.contractUnavailable }
    func editDraft(_ draft: GeneratedMemory, title: String, content: String, time: InformationDimension) async throws -> GeneratedMemory { throw APIError.contractUnavailable }
    func previewDraftTime(_ draft: GeneratedMemory, input: TimePreviewInput) async throws -> TimePreview { throw APIError.contractUnavailable }
    func previewMemoryTime(_ memory: MemoryEvent, input: TimePreviewInput) async throws -> TimePreview { throw APIError.contractUnavailable }
    func regenerateDraft(_ draft: GeneratedMemory) async throws -> GeneratedMemory { throw APIError.contractUnavailable }
}
struct MemoryEdit: Equatable {
    var title: String
    var content: String
    var time: InformationDimension
    var place: InformationDimension
    var feeling: InformationDimension
    var mediaIDs: [UUID]
    init(_ memory: MemoryEvent) {
        title = memory.title; content = memory.content
        time = memory.information.time; place = memory.information.place; feeling = memory.information.feeling
        if time.status == .missing, let value = memory.dateDescription ?? memory.date.map(APIDate.day) {
            time = InformationDimension(status: memory.date == nil ? .approximate : .known, value: value)
        }
        if place.status == .missing, let value = memory.location { place = InformationDimension(status: .known, value: value) }
        mediaIDs = memory.mediaAssets.map(\.id)
    }
    var isValid: Bool {
        !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && title.count <= 200 &&
        !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && content.count <= 100000 &&
        [time, place, feeling].allSatisfy { $0.status == .missing || !($0.value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }
}
func isVersionConflict(_ error: Error) -> Bool {
    if case APIError.rejected(let status, _) = error { return status == 409 }
    return false
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
