import Foundation

enum InformationStatus: String, Codable {
    case missing, known, approximate, unknown, withheld
}

struct InformationDimension: Codable, Equatable {
    var status: InformationStatus = .missing
    var value: String? = nil
    var source_message_ids: [UUID] = []
}

struct StoryInformation: Codable, Equatable {
    var people = InformationDimension()
    var event = InformationDimension()
    var time = InformationDimension()
    var place = InformationDimension()
    var feeling = InformationDimension()
    var detail = InformationDimension()
}

struct ChatAttachment: Identifiable, Codable, Equatable {
    let id: UUID
    let url: String
    var position: Int = 0
}
