import SwiftUI

/// 回忆副标题的统一展示规则，供首页和回忆列表复用。
func memorySubtitle(_ event: MemoryEvent, members: [FamilyMember]) -> String {
    "\(memoryRoles(event, members: members)) · \(event.dateLabel)"
}

/// 回忆所属人物的称呼：优先主人物，否则列出全部参与者。
func memoryRoles(_ event: MemoryEvent, members: [FamilyMember]) -> String {
    let ids = event.primaryPersonID.map { [$0] } ?? event.personIDs
    let roles = ids.compactMap { id in members.first { $0.id == id } }.map { $0.relationship.isEmpty ? $0.name : $0.relationship }
    return roles.isEmpty ? event.personName : roles.joined(separator: "、")
}

/// “关于外婆”
func memoryAbout(_ event: MemoryEvent, members: [FamilyMember]) -> String { "关于" + memoryRoles(event, members: members) }

/// “2008年夏天 · 老家院子”，缺失的时间和地点不显示。
func memoryWhenWhere(_ event: MemoryEvent) -> String {
    [event.dateDescription ?? event.date.map { _ in event.dateLabel }, event.location]
        .compactMap { $0 }.filter { !$0.isEmpty && $0 != "未提及" && $0 != "待补充" }.joined(separator: " · ")
}

/// 复用胶片的故事时间规则，年份区间和不明确的日期不强行推断。
func memoryYear(_ event: MemoryEvent) -> Int? {
    FamilyFilmTimeline.year(for: event)
}
