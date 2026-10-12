import SwiftUI

/// 人物身份的 UI 展示规则，与传输模型及网络请求分离。
extension FamilyMember {
    var journalIdentity: String {
        [relationship, birthDate.map { JournalFormat.birthday($0) } ?? "生日待补充"].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}
