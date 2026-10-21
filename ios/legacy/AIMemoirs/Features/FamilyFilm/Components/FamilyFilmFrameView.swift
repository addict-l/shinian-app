import SwiftUI

/// 胶片画格保留温暖的深棕边框和齿孔，标题与时间放在纸张底色上，保证可读性。
struct FamilyFilmFrameView: View {
    let moment: FamilyFilmTimeline.Moment
    let index: Int
    let onOpen: () -> Void
    private let width: CGFloat = 184
    private let border = Color(red: 73/255, green: 63/255, blue: 54/255)

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 0) {
                VStack(spacing: 0) {
                    perforations
                    Group {
                        if moment.memory.imageData != nil || moment.memory.imageName != nil {
                            JournalPhoto(memory: moment.memory, height: 104, radius: 2)
                        } else {
                            Text(moment.memory.content.isEmpty ? moment.memory.title : moment.memory.content)
                                .font(JournalTheme.story(13)).lineSpacing(5).lineLimit(3)
                                .foregroundStyle(border).padding(14).frame(maxWidth: .infinity).frame(height: 104)
                                .background(Color(red: 224/255, green: 216/255, blue: 202/255))
                        }
                    }.padding(.horizontal, 8)
                    perforations
                }.background(border)
                HStack {
                    Text(moment.memory.dateLabel)
                    Spacer(minLength: 4)
                    Text(String(format: "%02d", index)).monospacedDigit()
                }.font(JournalTheme.font(10)).foregroundStyle(JournalTheme.muted).padding(.top, 10)
                Text(moment.memory.title).font(JournalTheme.story(14)).foregroundStyle(JournalTheme.ink)
                    .lineLimit(2).frame(maxWidth: .infinity, minHeight: 40, alignment: .topLeading).padding(.top, 5)
            }.frame(width: width).padding(.trailing, 8).contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityLabel("\(moment.memory.dateLabel)，\(moment.memory.title)")
    }

    private var perforations: some View {
        HStack(spacing: 11) {
            ForEach(0..<9) { _ in
                RoundedRectangle(cornerRadius: 1).fill(JournalTheme.paper.opacity(0.85)).frame(width: 7, height: 4)
            }
        }.frame(maxWidth: .infinity).frame(height: 12).accessibilityHidden(true)
    }
}
