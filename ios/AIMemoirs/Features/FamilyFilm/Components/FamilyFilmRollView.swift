import SwiftUI

/// 一位家人的完整胶卷：深棕片基、上下齿孔，画格可横向翻阅，末尾留一格“＋ 添一格”。
struct FamilyFilmRollView: View {
    let lane: FamilyFilmTimeline.Lane
    let portrait: UIImage?
    let isLoading: Bool
    let onPerson: () -> Void
    let onMemory: (UUID) -> Void
    let onAdd: () -> Void
    let onPortrait: () -> Void
    @ScaledMetric(relativeTo: .body) private var frameHeight = FamilyFilmFrameView.Layout.height

    /// 从近到远翻阅；未知年份排在最后。
    private var moments: [FamilyFilmTimeline.Moment] {
        lane.moments.enumerated().sorted { left, right in
            let priority = ["除夕夜里的那枚硬币", "窗台上的那盆茉莉", "银杏路上的二八自行车"]
            if JournalDemo.isPreview && lane.person.relationship == "爷爷" {
                let l = priority.firstIndex(of: left.element.memory.title) ?? 100
                let r = priority.firstIndex(of: right.element.memory.title) ?? 100
                if l != r { return l < r }
            }
            if !JournalDemo.isPreview {
                let l = left.element.year ?? Int.min, r = right.element.year ?? Int.min
                if l != r { return l > r }
            }
            if left.element.memory.createdAt != right.element.memory.createdAt {
                return left.element.memory.createdAt > right.element.memory.createdAt
            }
            return left.offset < right.offset
        }.map(\.element)
    }

    private var previewCount: Int { JournalDemo.isPreview ? (lane.person.relationship == "外婆" ? 2 : 3) : moments.count }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button(action: onPerson) {
                HStack(spacing: 10) {
                    if let portrait {
                        JournalAvatarFrame(size: 34) { Image(uiImage: portrait).resizable().scaledToFill() }
                    } else {
                        JournalAvatar(person: lane.person, size: 34)
                    }
                    Text(lane.person.relationship.isEmpty ? lane.person.name : lane.person.relationship)
                        .font(JournalTheme.font(15, medium: true)).foregroundStyle(JournalTheme.ink)
                    if !lane.person.relationship.isEmpty {
                        Text(lane.person.name).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }
                    Spacer()
                    Text("\(lane.moments.count) 段回忆 ›").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        .accessibilityIdentifier("film.count.\(lane.person.name)")
                }.contentShape(Rectangle())
            }
            .buttonStyle(.plain).accessibilityIdentifier("film.person.\(lane.person.name)")
            .contextMenu {
                Button("查看人物回忆", action: onPerson)
                Button("更换人物照片", systemImage: "photo", action: onPortrait)
            }
            .padding(.horizontal, 6)

            VStack(spacing: 0) {
                perforations
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        if lane.moments.isEmpty && isLoading {
                            ProgressView().tint(Color(hex: 0xF8E3D5)).frame(width: FamilyFilmFrameView.Layout.width, height: frameHeight)
                        }
                        ForEach(moments.prefix(previewCount)) { moment in
                            FamilyFilmFrameView(moment: moment) { onMemory(moment.id) }
                                .accessibilityIdentifier("film.frame.\(lane.id).\(moment.id)")
                        }
                        Button(action: onAdd) {
                            Text("＋ 添一格").font(JournalTheme.font(11.5)).foregroundStyle(Color(hex: 0xF8E3D5))
                                .frame(width: lane.moments.isEmpty ? FamilyFilmFrameView.Layout.width : 70, height: frameHeight)
                                .overlay { RoundedRectangle(cornerRadius: 5).strokeBorder(JournalTheme.paper.opacity(0.5), style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])) }
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain).accessibilityLabel("记录关于\(lane.person.name)的回忆")
                        .accessibilityIdentifier(lane.moments.isEmpty ? "film.empty.\(lane.person.name)" : "film.add.\(lane.person.name)")
                        ForEach(moments.dropFirst(previewCount)) { moment in
                            FamilyFilmFrameView(moment: moment) { onMemory(moment.id) }
                        }
                        if lane.moments.isEmpty && !isLoading {
                            Text("这一卷，等一个故事").font(JournalTheme.story(12)).foregroundStyle(Color(hex: 0xF8E3D5).opacity(0.8))
                                .padding(.leading, 6)
                        }
                    }.padding(.horizontal, 8).padding(.vertical, 6)
                }
                .scrollIndicators(.hidden)
                .accessibilityIdentifier("film.roll.\(lane.person.name)")
                perforations
            }
            .padding(.vertical, 6)
            .background(JournalTheme.film, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .shadow(color: JournalTheme.film.opacity(0.22), radius: 9, x: 0, y: 8)
        }
        .padding(.horizontal, JournalTheme.gutter - 6)
        .accessibilityElement(children: .contain)
    }

    private var perforations: some View {
        HStack(spacing: 0) {
            ForEach(0..<16, id: \.self) { index in
                RoundedRectangle(cornerRadius: 1.5).fill(JournalTheme.paper.opacity(0.85)).frame(width: 7, height: 5)
                if index < 15 { Spacer(minLength: 0) }
            }
        }.padding(.horizontal, 6).accessibilityHidden(true)
    }
}
