import SwiftUI

/// 全应用的颜色、字号与间距令牌；数值与「拾年 · 温馨版」设计稿一一对应。
enum JournalTheme {
    static let paper = Color(hex: 0xFBF5EC)
    static let paper2 = Color(hex: 0xF6EDE0)
    static let surface = Color(hex: 0xFFFDF9)
    static let ink = Color(hex: 0x3D2E24)
    static let ink2 = Color(hex: 0x6B5848)
    static let muted = Color(hex: 0xA08C7B)
    static let placeholder = Color(hex: 0xC3B09F)
    static let secondaryInk = ink2
    static let line = Color(hex: 0xEEE2D3)
    static let cardBorder = Color(red: 232 / 255, green: 215 / 255, blue: 196 / 255).opacity(0.55)

    static let accent = Color(hex: 0xD47B52)
    static let accentDeep = Color(hex: 0xB9623D)
    static let soft = Color(hex: 0xF8E3D5)
    static let accentSoft = soft
    static let accentFaint = Color(hex: 0xFCF1E9)
    static let accentGlow = Color(hex: 0xE39468)
    static let accentDark = Color(hex: 0xC2683F)

    static let sage = Color(hex: 0x8EA27C)
    static let sageSoft = Color(hex: 0xE6ECDD)
    static let sageInk = Color(hex: 0x5E7350)
    static let butter = Color(hex: 0xF1C36C)
    static let butterSoft = Color(hex: 0xFBEFD3)
    static let butterInk = Color(hex: 0xB07D20)
    static let butterChipInk = Color(hex: 0x9A6D1C)
    static let rose = Color(hex: 0xD99A96)
    static let roseSoft = Color(hex: 0xF7E4E1)
    static let roseInk = Color(hex: 0xA35A55)
    static let danger = Color(hex: 0xC0574A)
    static let swipeDelete = Color(hex: 0xE9A08F)
    static let storyInk = Color(hex: 0x4A392D)
    static let film = Color(hex: 0x4A3A30)

    static let lavender = sageInk
    static let userMessageSurface = soft
    static let userMessageInk = Color(hex: 0x6E3D25)
    static let userMessageBorder = soft
    static let night = Color("JournalNight")
    static let nightInk = Color("JournalNightInk")
    static let nightMuted = Color("JournalNightMuted")
    static let shadow = Color(red: 150 / 255, green: 98 / 255, blue: 58 / 255)
    static let gutter: CGFloat = 22
    static let cardRadius: CGFloat = 22

    static func font(_ size: CGFloat, medium: Bool = false) -> Font {
        .custom(medium ? "PingFangSC-Medium" : "PingFangSC-Regular", size: size, relativeTo: .body)
    }
    static func story(_ size: CGFloat) -> Font {
        .custom("NotoSerifSC-Regular", size: size, relativeTo: .title2)
    }

    /// 无照片人物的头像底色，按人物稳定取色，同一家人在各页面颜色一致。
    static func avatarTint(for id: UUID) -> (fill: Color, ink: Color) {
        let palette: [(Color, Color)] = [(sage, .white), (accentGlow, .white), (butter, .white), (rose, .white)]
        let index = id.uuid.15 == 4 ? 0 : Int(id.uuid.0 ^ id.uuid.15) % palette.count
        return palette[index]
    }

    /// 时间线圆点、色块的轮换配色：杏色、鼠尾草绿、奶油黄。
    static func rotating(_ index: Int) -> (dot: Color, ring: Color) {
        [(accent, soft), (sage, sageSoft), (butter, butterSoft)][index % 3]
    }
}

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: opacity)
    }
}

extension View {
    /// 暖白卡片：22pt 圆角、浅描边与柔和投影。
    func journalCard(radius: CGFloat = JournalTheme.cardRadius, fill: Color = JournalTheme.surface) -> some View {
        background(fill, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: radius, style: .continuous).stroke(JournalTheme.cardBorder, lineWidth: 1) }
            .shadow(color: JournalTheme.shadow.opacity(0.08), radius: 7, x: 0, y: 4)
    }
    /// 大投影，用于草稿信纸、浮层和输入框。
    func journalLiftedShadow() -> some View {
        shadow(color: JournalTheme.shadow.opacity(0.10), radius: 15, x: 0, y: 10)
            .shadow(color: JournalTheme.shadow.opacity(0.06), radius: 3, x: 0, y: 2)
    }
}
