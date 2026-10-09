import Foundation

/// 每位已创建家人拥有一条胶卷；每条胶卷只包含这个人物实际参与的回忆。
/// 同一段共同回忆可出现在多人的胶卷里，未知故事时间不以创建时间冒充。
struct FamilyFilmTimeline {
    struct Moment: Identifiable {
        let memory: MemoryEvent
        let year: Int?
        var id: UUID { memory.id }
        var yearLabel: String { year.map(String.init) ?? "时间待补充" }
    }
    struct Lane: Identifiable {
        let person: FamilyMember
        let moments: [Moment]
        var id: String { person.id.uuidString }
    }
    let moments: [Moment]
    let lanes: [Lane]

    init(members: [FamilyMember], memories: [MemoryEvent], calendar: Calendar = .current) {
        moments = memories.map { Moment(memory: $0, year: Self.year(for: $0, calendar: calendar)) }.sorted {
            if $0.year != $1.year { return ($0.year ?? Int.max) < ($1.year ?? Int.max) }
            if let left = $0.memory.date, let right = $1.memory.date, left != right { return left < right }
            if $0.memory.createdAt != $1.memory.createdAt { return $0.memory.createdAt < $1.memory.createdAt }
            return $0.id.uuidString < $1.id.uuidString
        }
        let ordered = moments
        lanes = members.map { person in
            Lane(person: person, moments: ordered.filter { $0.memory.personIDs.contains(person.id) })
        }
    }
    func contains(_ moment: Moment, in lane: Lane) -> Bool {
        moment.memory.personIDs.contains(lane.person.id)
    }
    func participants(of moment: Moment) -> [FamilyMember] {
        lanes.map(\.person).filter { moment.memory.personIDs.contains($0.id) }
    }
    static func year(for memory: MemoryEvent, calendar: Calendar = .current) -> Int? {
        if let date = memory.date { return calendar.component(.year, from: date) }
        // Accept a stated year/season, but not an ambiguous range or arbitrary prose.
        guard let label = memory.dateDescription?.trimmingCharacters(in: .whitespacesAndNewlines),
              let range = label.range(of: #"^([1-9][0-9]{3})年(?:春天|夏天|秋天|冬天|春|夏|秋|冬|初|末)?$"#, options: .regularExpression),
              range.lowerBound == label.startIndex else { return nil }
        return Int(label.prefix(4))
    }
}
