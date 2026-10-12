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
    var conflicts: [InformationConflict]? = nil
    var analyzed_message_ids: [UUID]? = nil
}

struct InformationConflict: Codable, Equatable {
    let dimension: String
    let alternatives: [InformationDimension]
}

struct StoryReadiness: Codable, Equatable {
    let ready: Bool
    let missing_dimensions: [String]
    let conflicting_dimensions: [String]
    let needs_analysis: Bool
    let message: String
}

struct ChatAttachment: Identifiable, Codable, Equatable {
    let id: UUID
    let url: String
    var position: Int = 0
}


struct GenerationOffer: Codable, Equatable {
    let message_id: UUID
}
