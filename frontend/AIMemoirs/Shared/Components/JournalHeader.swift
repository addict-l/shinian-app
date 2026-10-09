import SwiftUI

/// 主页面共用标题布局。
struct JournalHeader: View {
    let kicker: String
    let title: String
    let subtitle: String
    var dark = false
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(kicker).font(JournalTheme.font(11)).tracking(1)
                .foregroundStyle(dark ? JournalTheme.nightMuted : JournalTheme.muted)
                .frame(minHeight: 17, alignment: .leading)
            Text(title).font(JournalTheme.font(28, medium: true))
                .foregroundStyle(dark ? JournalTheme.nightInk : JournalTheme.ink)
                .padding(.top, 12).frame(minHeight: 42, alignment: .leading)
            Text(subtitle).font(JournalTheme.font(13))
                .foregroundStyle(dark ? JournalTheme.nightMuted : JournalTheme.muted)
                .padding(.top, 2).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 16)
    }
}
