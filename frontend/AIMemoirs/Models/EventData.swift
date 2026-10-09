import Foundation

// Presentation data mapped by the backend adapter; no client-side AI text parsing.
struct EventData {
    let person: String
    let date: String
    let title: String
    let content: String
    let location: String
    let participants: [String]
    let emotion: String
}
