import Foundation

struct MemoryEvent: Identifiable, Codable {
    let id: UUID
    let personName: String
    let personIDs: [UUID]
    let date: Date?
    let content: String
    let title: String
    let imageName: String?
    let imageData: Data?
    let createdAt: Date
    let dateDescription: String?
    let location: String?
    var dateLabel: String { dateDescription ?? date?.formatted(.dateTime.year().month().day().locale(Locale(identifier: "zh_CN"))) ?? "时间待补充" }

    init(id: UUID = UUID(), personName: String, personIDs: [UUID] = [], date: Date?, content: String,
         title: String, imageName: String? = nil, imageData: Data? = nil, createdAt: Date = Date(), dateDescription: String? = nil, location: String? = nil) {
        self.id = id; self.personName = personName; self.personIDs = personIDs; self.date = date
        self.content = content; self.title = title; self.imageName = imageName
        self.imageData = imageData; self.createdAt = createdAt
        self.dateDescription = dateDescription; self.location = location
    }
    func copy(imageData: Data?) -> MemoryEvent {
        MemoryEvent(id: id, personName: personName, personIDs: personIDs, date: date, content: content,
                    title: title, imageName: imageName, imageData: imageData, createdAt: createdAt, dateDescription: dateDescription, location: location)
    }
}
