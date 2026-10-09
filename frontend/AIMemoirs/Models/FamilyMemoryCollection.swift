import Foundation

/// 当前家庭的展示集合。删除人物后留下的历史正文不参与当前家庭的列表和统计。
/// 多人共同回忆只要还有一位现有参与者就保留，身份匹配使用 UUID 而不是姓名。
struct FamilyMemoryCollection {
    let events: [MemoryEvent]
    let participatingPeopleCount: Int

    init(members: [FamilyMember], memories: [MemoryEvent]) {
        let people = Set(members.map(\.id))
        events = memories.filter { !people.isDisjoint(with: $0.personIDs) }
        participatingPeopleCount = Set(events.flatMap(\.personIDs)).intersection(people).count
    }
}
