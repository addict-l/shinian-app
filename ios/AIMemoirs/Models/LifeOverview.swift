import Foundation

struct LifeQuote: Codable, Equatable { let message_id: UUID; let quote: String }
struct LifeField: Codable, Equatable, Identifiable {
    let topic_id: String
    let status: String
    let evidence: [LifeQuote]
    var id: String { topic_id }
    var title: String { Self.titles[topic_id] ?? topic_id }
    var content: String {
        if !evidence.isEmpty { return evidence.map(\.quote).joined(separator: "\n") }
        return ["pending": "待补充", "skipped": "暂时跳过", "unknown": "记不清", "declined": "暂时不想讲"][status] ?? "待补充"
    }
    static let titles = ["home": "成长的地方", "learning": "读书或学艺", "early_work": "年轻时的工作与生活", "later_work": "后来的工作与生活", "family": "重要家人", "changes": "记得的生活变化", "present": "如今的生活", "SK01": "出生时间", "SK01b": "出生地点", "SK01c": "记忆中的家乡", "SK02": "名字与期许", "SK03": "小时候和谁生活", "SK03b": "家庭生活来源", "SK03c": "兄弟姐妹", "SK03d": "家人的相处", "SK04": "家教与影响", "SK05": "性格底色", "SK06": "人生关键词"]
}
struct LifeTurn: Codable, Identifiable { let id: UUID; let role: String; let content: String }
struct LifeCommand: Codable {
    let action: String
    let expected_version: Int
    let client_request_id: UUID
    var text: String = ""
    var topic_id: String? = nil
}
struct LifeOverview: Codable {
    let version: Int
    let status: String
    let required: Bool
    let paused: Bool
    let fields: [LifeField]
    let turns: [LifeTurn]
    let question_id: String?
    let question: String?
    let question_number: Int
    let total_questions: Int
    let confirmed_version: Int?
    let pending_request_id: UUID?
    let pending_action: LifeCommand?
}
struct GuidedInterviewProgress: Codable, Equatable {
    let module: String
    let module_selected: Bool
    let topic_index: Int
    let phase: String
}
