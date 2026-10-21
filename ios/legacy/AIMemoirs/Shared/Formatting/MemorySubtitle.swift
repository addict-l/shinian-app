import SwiftUI

/// 回忆副标题的统一展示规则，供首页和回忆列表复用。
func memorySubtitle(_ event: MemoryEvent, members: [FamilyMember]) -> String {
    let roles = event.personIDs.compactMap { id in members.first { $0.id == id }?.relationship }.filter { !$0.isEmpty }
    return "\(roles.isEmpty ? event.personName : roles.joined(separator: "、")) · \(event.dateLabel)"
}
