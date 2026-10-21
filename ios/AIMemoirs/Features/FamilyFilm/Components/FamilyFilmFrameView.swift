import SwiftUI

/// 紧凑胶片画格：保留照片、左上角年份和底部标题。
struct FamilyFilmFrameView: View {
    enum Layout {
        static let width: CGFloat = 101
        static let height: CGFloat = 82
        static let radius: CGFloat = 7
    }
    let moment: FamilyFilmTimeline.Moment
    let onOpen: () -> Void
    @ScaledMetric(relativeTo: .body) private var width = Layout.width
    @ScaledMetric(relativeTo: .body) private var height = Layout.height
    private var hasPhoto: Bool { moment.memory.imageData != nil || moment.memory.imageName != nil }

    var body: some View {
        Button(action: onOpen) {
            ZStack(alignment: .bottomLeading) {
                if hasPhoto {
                    JournalPhoto(memory: moment.memory, height: height, radius: Layout.radius)
                    LinearGradient(stops: [
                        .init(color: .clear, location: 0),
                        .init(color: JournalTheme.film.opacity(0.08), location: 0.36),
                        .init(color: JournalTheme.film.opacity(0.88), location: 0.65),
                        .init(color: JournalTheme.film, location: 1)
                    ], startPoint: .top, endPoint: .bottom)
                } else {
                    JournalTheme.paper2
                }
                Text(moment.memory.title)
                    .font(JournalTheme.font(11, medium: true))
                    .foregroundStyle(hasPhoto ? .white : JournalTheme.ink)
                    .multilineTextAlignment(.leading).lineLimit(2).lineSpacing(1)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(7)

            }
            .frame(width: width, height: height)
            .overlay(alignment: .topLeading) {
                if let year = moment.year {
                    Text(String(year)).font(JournalTheme.font(10, medium: true))
                        .foregroundStyle(hasPhoto ? .white : JournalTheme.ink2)
                        .padding(.horizontal, 6).padding(.vertical, 3)
                        .background(hasPhoto ? JournalTheme.film.opacity(0.72) : JournalTheme.surface.opacity(0.9), in: Capsule())
                        .padding(6)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: Layout.radius))
            .contentShape(RoundedRectangle(cornerRadius: Layout.radius))
        }
        .buttonStyle(JournalActionButtonStyle())
        .accessibilityLabel("\(moment.memory.dateLabel)，\(moment.memory.title)")
        .accessibilityHint("查看完整回忆")
    }
}
