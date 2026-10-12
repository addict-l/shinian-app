import Foundation

/// 新人物请求草稿。内容变化时更新请求 ID，重试同一份草稿时保持幂等。
struct FamilyMemberDraft {
    var requestID = UUID()
    var realName = "" { didSet { if realName != oldValue { requestID = UUID() } } }
    var relationship = "" { didSet { if relationship != oldValue { requestID = UUID() } } }
    var birthDate: Date? { didSet { if birthDate != oldValue { requestID = UUID() } } }

    /// A person can be submitted only with a name, relationship, and non-future birthday.
    func isValid(today: Date = Date(), calendar: Calendar = .current) -> Bool {
        guard !realName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !relationship.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let birthDate else { return false }
        return calendar.startOfDay(for: birthDate) <= calendar.startOfDay(for: today)
    }
}
