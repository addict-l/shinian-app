import Foundation

enum MemoirCover: String, Codable, CaseIterable { case text, photo, collage
    var title: String { switch self { case .text: "纯文字"; case .photo: "单照片"; case .collage: "照片拼贴" } }
    var limit: Int { switch self { case .text: 0; case .photo: 1; case .collage: 3 } }
}
struct MemoirCoverPhoto: Codable, Equatable, Identifiable {
    var id: UUID
    var sourceMemoryId: UUID? = nil
    var x: Double = 0
    var y: Double = 0
    var zoom: Double = 1
}
struct MemoirSettings: Codable, Equatable {
    var title: String
    var subtitle = ""
    var coverTemplate: MemoirCover = .text
    var coverPhotos: [MemoirCoverPhoto] = []
    var ordering = "time"
    var storyOrder: [UUID] = []
    var photoOrders: [String: [UUID]] = [:]
    var excludedPhotoIds: [UUID] = []
    var textSize = 16
    var valid: Bool { !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && title.count <= 200 && subtitle.count <= 300 }

    func ordered(_ stories: [MemoryEvent]) -> [MemoryEvent] {
        let saved = stories.sorted { ($0.createdAt, $0.id.uuidString) < ($1.createdAt, $1.id.uuidString) }
        if ordering == "manual" {
            let byID = Dictionary(uniqueKeysWithValues: saved.map { ($0.id, $0) })
            return storyOrder.compactMap { byID[$0] } + saved.filter { !storyOrder.contains($0.id) }
        }
        // Stable ties use save order. Never substitute createdAt for an event date.
        return saved.enumerated().sorted { a, b in
            let x = Self.timeKey(a.element), y = Self.timeKey(b.element)
            if x == y { return a.offset < b.offset }
            if x == nil { return false }; if y == nil { return true }
            return x! < y!
        }.map(\.element)
    }
    static func timeKey(_ story: MemoryEvent) -> String? {
        if let date = story.date { return APIDate.day(date) }
        guard story.information.time.status != .unknown && story.information.time.status != .withheld else { return nil }
        guard let value = story.dateDescription ?? story.information.time.value else { return nil }
        // Accept determinate year/month/day and a season; do not infer life stages or ranges.
        let pattern = #"^(\d{4})(?:年(?:(\d{1,2})月(?:(\d{1,2})[日号])?|春天|夏天|秋天|冬天|春季|夏季|秋季|冬季)?|-(\d{2})(?:-(\d{2}))?)?$"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)) else { return nil }
        func number(_ index: Int) -> Int? { Range(match.range(at: index), in: value).flatMap { Int(value[$0]) } }
        guard let year = number(1), year > 0 else { return nil }
        let month = number(2) ?? number(4) ?? 1, day = number(3) ?? number(5) ?? 1
        let key = String(format: "%04d-%02d-%02d", year, month, day)
        guard let date = APIDate.parseDay(key), APIDate.day(date) == key else { return nil }
        return key
    }
    func photos(_ story: MemoryEvent) -> [ChatAttachment] {
        let saved = story.mediaAssets
        let ids = photoOrders[story.id.uuidString.lowercased()] ?? []
        let map = Dictionary(uniqueKeysWithValues: saved.map { ($0.id, $0) })
        return (ids.compactMap { map[$0] } + saved.filter { !ids.contains($0.id) })
    }
    func selectedPhotos(_ story: MemoryEvent) -> [ChatAttachment] { photos(story).filter { !excludedPhotoIds.contains($0.id) } }
}
struct MemoirSnapshot: Codable {
    var personId: UUID
    var personName: String
    var version: Int
    var settings: MemoirSettings
    var stories: [MemoryEvent]
    var contentRevision: String
}
struct MemoirSaveRequest: Codable {
    var version: Int
    var requestId: UUID = UUID()
    var settings: MemoirSettings
}
@MainActor protocol MemoirAPI {
    func memoir(personID: UUID) async throws -> MemoirSnapshot
    func saveMemoir(personID: UUID, request: MemoirSaveRequest) async throws -> MemoirSnapshot
    func uploadMemoirCover(personID: UUID, data: Data, requestID: UUID) async throws -> ChatAttachment
    func loadPhoto(_ attachment: ChatAttachment) async throws -> Data
}
