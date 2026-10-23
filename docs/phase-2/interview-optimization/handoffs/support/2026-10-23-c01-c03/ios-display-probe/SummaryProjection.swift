import SwiftUI

struct CareLifeSummaryLine: Identifiable {
    let id: String
    let text: String
    let subdued: Bool
}

struct CareLifeSummaryGroup: Identifiable {
    let title: String
    let symbol: String
    let tone: CareTone
    let fieldIDs: [String]
    let lines: [CareLifeSummaryLine]
    var id: String { title }
    var text: String { lines.isEmpty ? "之后可以慢慢补充。" : lines.map(\.text).joined(separator: "\n") }
}

/// Keep the original words visible for both interview catalogs, including fields
/// added by a future catalog that this version of the app does not recognize.
enum CareLifeSummaryGroups {
    private static let legacy: [(String, [String], String, CareTone)] = [
        ("小时候", ["home"], "house", .butter),
        ("读书工作", ["learning", "early_work", "later_work"], "book", .sage),
        ("家人近况", ["family", "changes", "present"], "person.2", .rose)
    ]
    private static let skeleton: [(String, [String], String, CareTone)] = [
        ("出生与家乡", ["SK01", "SK01b", "SK01c", "SK02"], "house", .butter),
        ("小时候的家", ["SK03", "SK03b", "SK03c", "SK03d", "SK04"], "person.2", .sage),
        ("性格与一生", ["SK05", "SK06"], "sun.max", .rose)
    ]

    static func make(fields: [LifeField]) -> [CareLifeSummaryGroup] {
        let definitions = fields.contains { $0.topic_id.hasPrefix("SK") } ? skeleton : legacy
        let groupedIDs = Set(definitions.flatMap { $0.1 })
        var result = definitions.map { title, ids, symbol, tone in
            group(title: title, symbol: symbol, tone: tone, fields: fields.filter { ids.contains($0.topic_id) })
        }
        let remaining = fields.filter { !groupedIDs.contains($0.topic_id) }
        if !remaining.isEmpty {
            result.append(group(title: "其他", symbol: "text.book.closed", tone: .apricot, fields: remaining))
        }
        return result
    }

    private static func group(title: String, symbol: String, tone: CareTone, fields: [LifeField]) -> CareLifeSummaryGroup {
        let lines = fields.compactMap { field -> CareLifeSummaryLine? in
            guard field.status != "pending" else { return nil }
            let quotes = field.evidence.map(\.quote).filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            if !quotes.isEmpty {
                return CareLifeSummaryLine(id: field.id, text: quotes.joined(separator: "\n"), subdued: false)
            }
            let status = ["skipped": "暂时跳过", "unknown": "记不清", "declined": "暂时不想讲"][field.status] ?? "待补充"
            return CareLifeSummaryLine(id: field.id, text: field.title + "：" + status, subdued: true)
        }
        return CareLifeSummaryGroup(title: title, symbol: symbol, tone: tone, fieldIDs: fields.map(\.id), lines: lines)
    }
}


enum CareTone { case apricot, sage, butter, rose }
