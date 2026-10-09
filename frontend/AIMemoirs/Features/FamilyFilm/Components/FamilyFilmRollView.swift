import SwiftUI

/// 一位家人的完整胶卷。回忆独立横向滚动，不为其他人的回忆生成空白片段。
struct FamilyFilmRollView: View {
    let lane: FamilyFilmTimeline.Lane
    let portrait: UIImage?
    let isLoading: Bool
    let onPerson: () -> Void
    let onMemory: (UUID) -> Void
    let onAdd: () -> Void
    let onPortrait: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Button(action: onPerson) {
                    HStack(spacing: 12) {
                        avatar.frame(width: 42, height: 42).clipShape(Circle())
                        VStack(alignment: .leading, spacing: 4) {
                            Text(lane.person.relationship.isEmpty ? lane.person.name : lane.person.relationship)
                                .font(JournalTheme.font(16, medium: true)).foregroundStyle(JournalTheme.ink)
                            if !lane.person.relationship.isEmpty {
                                Text(lane.person.name).font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                            }
                        }
                    }.contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("film.person.\(lane.person.name)")
                    .contextMenu {
                        Button("查看人物回忆", action: onPerson)
                        Button("更换人物照片", systemImage: "photo", action: onPortrait)
                    }
                Spacer()
                Text("\(lane.moments.count) 段回忆").font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                    .accessibilityIdentifier("film.count.\(lane.person.name)")
                Button(action: onAdd) {
                    Image(systemName: "plus").font(.system(size: 14))
                        .frame(width: 36, height: 36).background(JournalTheme.soft, in: Circle())
                }.buttonStyle(.plain).accessibilityLabel("记录关于\(lane.person.name)的回忆")
            }.padding(.horizontal, 24)

            if lane.moments.isEmpty {
                if isLoading {
                    ProgressView("正在取出回忆…").frame(maxWidth: .infinity).frame(height: 94)
                } else {
                    Button(action: onAdd) {
                        HStack(spacing: 12) {
                            Image(systemName: "film").font(.system(size: 23, weight: .light))
                            VStack(alignment: .leading, spacing: 5) {
                                Text("这一卷，等一个故事").font(JournalTheme.font(13))
                                Text("记下你们的第一段回忆").font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                            }
                            Spacer()
                            Image(systemName: "arrow.right").font(.system(size: 13))
                        }.foregroundStyle(JournalTheme.accent).padding(18).frame(maxWidth: .infinity)
                            .background(JournalTheme.soft.opacity(0.55), in: RoundedRectangle(cornerRadius: 14))
                    }.buttonStyle(.plain).padding(.horizontal, 24)
                        .accessibilityIdentifier("film.empty.\(lane.person.name)")
                }
            } else {
                ScrollView(.horizontal) {
                    LazyHStack(alignment: .top, spacing: 0) {
                        ForEach(Array(lane.moments.enumerated()), id: \.element.id) { index, moment in
                            FamilyFilmFrameView(moment: moment, index: index + 1) { onMemory(moment.id) }
                                .accessibilityIdentifier("film.frame.\(lane.id).\(moment.id)")
                        }
                    }.scrollTargetLayout()
                }
                .contentMargins(.horizontal, 24, for: .scrollContent)
                .scrollTargetBehavior(.viewAligned).scrollIndicators(.hidden)
                .accessibilityIdentifier("film.roll.\(lane.person.name)")
            }
        }.accessibilityElement(children: .contain)
    }

    @ViewBuilder private var avatar: some View {
        if let portrait {
            Image(uiImage: portrait).resizable().scaledToFill()
        } else if let name = lane.person.profileImages.first(where: { UIImage(named: $0) != nil }) {
            Image(name).resizable().scaledToFill()
        } else {
            JournalAvatar(person: lane.person, size: 42)
        }
    }
}
