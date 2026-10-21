import SwiftUI

/// 主页面共用标题布局：杏色小字引导，宋体大标题讲故事。
struct JournalHeader: View {
    let kicker: String
    let title: String
    let subtitle: String
    var dark = false
    var secondaryColor = JournalTheme.muted
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(kicker).font(JournalTheme.font(11, medium: true)).tracking(1.6)
                .foregroundStyle(dark ? JournalTheme.nightMuted : JournalTheme.accent)
                .frame(minHeight: 17, alignment: .leading)
            Text(title).font(JournalTheme.story(29))
                .foregroundStyle(dark ? JournalTheme.nightInk : JournalTheme.ink)
                .padding(.top, 10).frame(minHeight: 42, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
            Text(subtitle).font(JournalTheme.font(14))
                .foregroundStyle(dark ? JournalTheme.nightMuted : secondaryColor)
                .padding(.top, 4).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 16)
    }
}
