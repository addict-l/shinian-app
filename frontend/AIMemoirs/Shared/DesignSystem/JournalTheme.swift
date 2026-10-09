import SwiftUI

/// 全应用的颜色、字号与间距令牌；组件和页面只引用这里的视觉规则。
enum JournalTheme {
    static let paper = Color("JournalPaper")
    static let surface = Color("JournalSurface")
    static let ink = Color("JournalInk")
    static let muted = Color("JournalMuted")
    static let accent = Color("AccentColor")
    static let lavender = Color(red: 0.55, green: 0.50, blue: 0.66)
    static let soft = Color("JournalSoft")
    static let line = Color("JournalLine")
    static let night = Color("JournalNight")
    static let nightInk = Color("JournalNightInk")
    static let nightMuted = Color("JournalNightMuted")
    static let gutter: CGFloat = 24

    static func font(_ size: CGFloat, medium: Bool = false) -> Font {
        .custom("PingFangSC-Regular", size: size, relativeTo: .body)
    }
    static func story(_ size: CGFloat) -> Font {
        .custom("NotoSerifSC-Regular", size: size, relativeTo: .title2)
    }
}
