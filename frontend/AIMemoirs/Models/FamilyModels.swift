import Foundation

// MARK: - Family member

enum Gender {
    case male
    case female
    case unspecified
}

/// The member model stays focused on the current product: people, conversations, and memories.
/// Generation, orbital color, and graph links belonged to the removed starry-tree prototype.
struct FamilyMember: Identifiable, Equatable {
    var id = UUID()
    let name: String
    let gender: Gender
    var profileImages: [String] = []
    var memoryCount: Int = 0
    var relationship: String = ""
    var birthDate: Date? = nil

    static func == (lhs: FamilyMember, rhs: FamilyMember) -> Bool { lhs.id == rhs.id }

}
