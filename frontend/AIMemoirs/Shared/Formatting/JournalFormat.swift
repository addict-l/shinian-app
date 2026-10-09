import SwiftUI

/// 中文日期的统一展示格式。
enum JournalFormat {
    static func birthday(_ date: Date) -> String {
        let format = DateFormatter(); format.locale = Locale(identifier: "zh_CN"); format.dateFormat = "yyyy年M月d日"
        return format.string(from: date)
    }
    static func month(_ date: Date) -> String {
        let format = DateFormatter(); format.locale = Locale(identifier: "zh_CN"); format.dateFormat = "yyyy年 · M月"
        return format.string(from: date)
    }
}
