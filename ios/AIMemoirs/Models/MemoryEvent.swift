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
    var primaryPersonID: UUID? = nil
    var sourceSessionID: UUID? = nil
    var version: Int = 1
    var information = StoryInformation()
    var mediaAssets: [ChatAttachment] = []
    var hasPhoto: Bool { imageData != nil || imageName != nil || !mediaAssets.isEmpty }
    var dateLabel: String { dateDescription ?? date?.formatted(.dateTime.year().month().day().locale(Locale(identifier: "zh_CN"))) ?? "时间待补充" }

    init(id: UUID = UUID(), personName: String, personIDs: [UUID] = [], date: Date?, content: String,
         title: String, imageName: String? = nil, imageData: Data? = nil, createdAt: Date = Date(), dateDescription: String? = nil, location: String? = nil) {
        self.id = id; self.personName = personName; self.personIDs = personIDs; self.date = date
        self.content = content; self.title = title; self.imageName = imageName
        self.imageData = imageData; self.createdAt = createdAt
        self.dateDescription = dateDescription; self.location = location
    }
    func copy(imageData: Data?) -> MemoryEvent {
        var result = MemoryEvent(id: id, personName: personName, personIDs: personIDs, date: date, content: content,
                    title: title, imageName: imageName, imageData: imageData, createdAt: createdAt, dateDescription: dateDescription, location: location)
        result.primaryPersonID = primaryPersonID; result.sourceSessionID = sourceSessionID; result.version = version; result.information = information; result.mediaAssets = mediaAssets
        return result
    }
    func removing(personID: UUID, remainingMembers: [FamilyMember]) -> MemoryEvent {
        guard personIDs.contains(personID) || primaryPersonID == personID else { return self }
        let ids = personIDs.filter { $0 != personID }
        let names = ids.compactMap { id in remainingMembers.first { $0.id == id }?.name }
        var result = MemoryEvent(id: id, personName: names.isEmpty ? "家庭成员" : names.joined(separator: "、"),
            personIDs: ids, date: date, content: content, title: title, imageName: imageName, imageData: imageData,
            createdAt: createdAt, dateDescription: dateDescription, location: location)
        result.primaryPersonID = primaryPersonID == personID ? nil : primaryPersonID
        result.sourceSessionID = sourceSessionID; result.version = version; result.information = information; result.mediaAssets = mediaAssets
        return result
    }
}
