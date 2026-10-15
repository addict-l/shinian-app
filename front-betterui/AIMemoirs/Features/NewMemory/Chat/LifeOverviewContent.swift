import SwiftUI

/// Presentation for the two overview steps; the interview owns all server mutations.
struct LifeOverviewContent<Feedback: View>: View {
    let overview: LifeOverview
    @Binding var selected: String
    let busy: Bool
    let hasPendingAction: Bool
    let onDetails: () -> Void
    let onConfirm: () -> Void
    let onEnter: () -> Void
    @ViewBuilder let feedback: () -> Feedback
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.displayScale) private var displayScale

    private var confirmed: Bool { overview.status == "confirmed" }
    private var summary: String {
        overview.fields.filter { !$0.evidence.isEmpty }
            .map { $0.evidence.map(\.quote).joined(separator: " ") }.joined(separator: "\n")
    }
    private var selectedTitle: String { LifeOverviewModule.all.first { $0.id == selected }?.title ?? "成长的地方" }

    var body: some View {
        VStack(spacing: 0) {
            LifeOverviewSteps(confirmed: confirmed)
                .padding(.horizontal, 24).padding(.top, 6).padding(.bottom, 8)
            GeometryReader { geometry in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(confirmed ? "从哪段日子开始？" : "先核对人生脉络")
                                .font(JournalTheme.story(30).weight(.semibold))
                                .offset(x: confirmed ? -0.5 : 0)
                                .foregroundStyle(LifeOverviewStyle.ink)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityAddTraits(.isHeader)
                            Text(confirmed ? "选一段最想聊的，按您的节奏来。" : "确认后，选一段想聊的回忆。")
                                .font(JournalTheme.font(16)).foregroundStyle(LifeOverviewStyle.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        // Keep the heading and subtitle on the same shifted leading edge.
                        .offset(x: confirmed ? 20 / displayScale : 0)
                        .padding(.bottom, 20)
                        if !confirmed { Spacer(minLength: 0) }
                        LifeOverviewSummary(confirmed: confirmed, summary: summary, onDetails: onDetails)
                        if confirmed {
                            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: typeSize.isAccessibilitySize ? 1 : 2), spacing: 12) {
                                ForEach(LifeOverviewModule.all) { module in
                                    LifeOverviewModuleCard(module: module, selected: selected == module.id) { selected = module.id }
                                }
                            }.padding(.top, 16)
                        } else {
                            Spacer(minLength: 0)
                            Text("不必一次想全，回忆可以慢慢补充。")
                                .font(JournalTheme.font(14)).foregroundStyle(LifeOverviewStyle.secondary)
                                .multilineTextAlignment(.center).frame(maxWidth: .infinity)
                                .padding(.top, 24)
                            Spacer(minLength: 20)
                        }
                        feedback()
                    }
                    .padding(.horizontal, 22).padding(.top, 10).padding(.bottom, 12)
                    .frame(minHeight: max(0, geometry.size.height), alignment: .topLeading)
                }.scrollIndicators(.hidden)
                    .accessibilityIdentifier("life.overviewScroll")
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            LifeOverviewPrimaryButton(title: confirmed ? "进入「\(selectedTitle)」" : "确认这些脉络", busy: busy,
                disabled: busy || hasPendingAction, action: confirmed ? onEnter : onConfirm)
                .accessibilityIdentifier(confirmed ? "life.enter" : "life.confirm")
                .padding(.horizontal, 22).padding(.top, 12).padding(.bottom, 12)
                .background(LifeOverviewStyle.canvas)
        }
    }
}

enum LifeOverviewStyle {
    static let canvas = Color(hex: 0xFAF8F3)
    static let surface = Color(hex: 0xFFFEFC)
    static let ink = Color(hex: 0x211C18)
    static let secondary = Color(hex: 0x6B635B)
    static let border = Color(hex: 0xE9E2D9)
    static let accent = Color(hex: 0xB45637)
    static let selected = Color(hex: 0xFBEDE4)
    static let green = JournalTheme.sageInk
    static let greenSoft = Color(hex: 0xE9F0E3)
    static let illustration = Color(hex: 0xA39280)
}

private struct LifeOverviewSteps: View {
    let confirmed: Bool
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { first; line; second }
            VStack(alignment: .leading, spacing: 8) { first; second }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(confirmed ? "第一步核对脉络已完成，当前第二步选择板块" : "当前第一步核对脉络，下一步选择板块")
        .accessibilityIdentifier("life.steps")
    }
    private var first: some View {
        HStack(spacing: 7) {
            if confirmed { Image(systemName: "checkmark.circle.fill").foregroundStyle(LifeOverviewStyle.green) }
            Text("01 核对脉络").foregroundStyle(confirmed ? LifeOverviewStyle.green : LifeOverviewStyle.accent)
            if !confirmed { Circle().fill(LifeOverviewStyle.accent).frame(width: 9, height: 9) }
        }.font(JournalTheme.font(13, medium: true)).fixedSize()
    }
    private var second: some View {
        HStack(spacing: 7) {
            Circle().fill(confirmed ? LifeOverviewStyle.accent : LifeOverviewStyle.canvas)
                .overlay { Circle().stroke(confirmed ? LifeOverviewStyle.accent : LifeOverviewStyle.secondary, lineWidth: 1) }
                .frame(width: 11, height: 11)
            Text("02 选择板块").foregroundStyle(confirmed ? LifeOverviewStyle.accent : LifeOverviewStyle.secondary)
        }.font(JournalTheme.font(13, medium: confirmed)).fixedSize()
    }
    private var line: some View {
        Rectangle().fill(LifeOverviewStyle.secondary.opacity(0.45)).frame(minWidth: 24, maxWidth: 58).frame(height: 1)
    }
}

private struct LifeOverviewSummary: View {
    let confirmed: Bool
    let summary: String
    let onDetails: () -> Void
    private var empty: Bool { summary.isEmpty }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "doc.text").font(.system(size: 23, weight: .regular)).accessibilityHidden(true)
                Text(confirmed ? "人生脉络" : "回忆线索")
                    .font(JournalTheme.font(18, medium: true))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                HStack(spacing: 5) {
                    if confirmed { Image(systemName: "checkmark.circle.fill").accessibilityHidden(true) }
                    Text(confirmed ? "已核对" : "待核对")
                }
                .font(JournalTheme.font(13, medium: true)).fixedSize()
                .foregroundStyle(confirmed ? LifeOverviewStyle.green : LifeOverviewStyle.accent)
                .padding(.horizontal, 11).padding(.vertical, 7)
                .background(confirmed ? LifeOverviewStyle.greenSoft : LifeOverviewStyle.selected, in: Capsule())
                .accessibilityIdentifier("life.confirmationStatus")
            }
            if empty && !confirmed {
                VStack(spacing: 0) {
                    LifeOpenBookIllustration().stroke(LifeOverviewStyle.illustration, style: StrokeStyle(lineWidth: 1.7, lineCap: .round, lineJoin: .round))
                        .frame(width: 114, height: 78).padding(.top, 26).padding(.bottom, 22).accessibilityHidden(true)
                    Text("还没有具体生活线索").font(JournalTheme.font(20, medium: true))
                        .padding(.bottom, 9)
                    Text("之后可以随时补充，\n也可以先从熟悉的回忆开始。")
                        .font(JournalTheme.font(16)).foregroundStyle(LifeOverviewStyle.secondary)
                        .multilineTextAlignment(.center).lineSpacing(4)
                }.frame(maxWidth: .infinity).padding(.bottom, 26)
                    .accessibilityIdentifier("life.emptyOutline")
            } else {
                Text(empty ? "暂未提供具体线索，之后可以随时补充。" : summary)
                    .font(JournalTheme.font(15)).foregroundStyle(LifeOverviewStyle.secondary)
                    .lineSpacing(4).lineLimit(confirmed ? 2 : 8)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 12).padding(.bottom, confirmed ? 12 : 20)
                    .accessibilityIdentifier("life.summary")
            }
            LifeOverviewStyle.border.frame(height: 1)
            Button(action: onDetails) {
                HStack {
                    Text("查看全部与更正").font(JournalTheme.font(16, medium: !confirmed))
                    Spacer()
                    Image(systemName: "chevron.right").font(.system(size: 14, weight: .regular))
                }.frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("life.details")
                .padding(.top, confirmed ? 4 : 8)
        }
        .foregroundStyle(LifeOverviewStyle.ink)
        .padding(.horizontal, 18).padding(.top, 18).padding(.bottom, 6)
        .background(LifeOverviewStyle.surface, in: RoundedRectangle(cornerRadius: 17))
        .overlay { RoundedRectangle(cornerRadius: 17).stroke(LifeOverviewStyle.border, lineWidth: 0.8) }
    }
}

private struct LifeOverviewModule: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let symbol: String
    static let all = [
        Self(id: "childhood", title: "成长的地方", subtitle: "家乡与童年", symbol: "house"),
        Self(id: "growth", title: "读书或学艺", subtitle: "校园与手艺", symbol: "book"),
        Self(id: "work", title: "工作与生活", subtitle: "奋斗与日常", symbol: "briefcase"),
        Self(id: "family", title: "重要家人", subtitle: "亲人与陪伴", symbol: "person.2"),
        Self(id: "later_life", title: "如今的生活", subtitle: "此刻的日常", symbol: "cup.and.saucer"),
        Self(id: "reflection", title: "人生回望", subtitle: "回忆与感悟", symbol: "clock"),
    ]
}

private struct LifeOverviewModuleCard: View {
    let module: LifeOverviewModule
    let selected: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Image(systemName: module.symbol).font(.system(size: 25, weight: .regular))
                        .foregroundStyle(selected ? LifeOverviewStyle.accent : LifeOverviewStyle.ink)
                    Spacer()
                    if selected {
                        Image(systemName: "checkmark.circle.fill").font(.system(size: 23))
                            .symbolRenderingMode(.palette).foregroundStyle(.white, LifeOverviewStyle.accent)
                    }
                }.frame(height: 29).accessibilityHidden(true)
                Text(module.title).font(JournalTheme.font(18, medium: true)).foregroundStyle(LifeOverviewStyle.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(module.subtitle).font(JournalTheme.font(14)).foregroundStyle(LifeOverviewStyle.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16).padding(.vertical, 10)
            .background(selected ? LifeOverviewStyle.selected : LifeOverviewStyle.surface, in: RoundedRectangle(cornerRadius: 16))
            .overlay { RoundedRectangle(cornerRadius: 16).stroke(selected ? LifeOverviewStyle.accent : LifeOverviewStyle.border, lineWidth: selected ? 1.2 : 0.8) }
            .contentShape(RoundedRectangle(cornerRadius: 16))
        }.buttonStyle(.plain)
            .accessibilityElement(children: .ignore).accessibilityLabel(module.title + "，" + module.subtitle)
            .accessibilityAddTraits(.isButton).accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier("life.module.\(module.id)")
    }
}

private struct LifeOverviewPrimaryButton: View {
    let title: String
    let busy: Bool
    let disabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                if busy { ProgressView().tint(.white) }
                Text(title).font(JournalTheme.font(18, medium: true)).multilineTextAlignment(.center)
                Image(systemName: "arrow.right").font(.system(size: 20, weight: .medium)).accessibilityHidden(true)
            }.foregroundStyle(.white).frame(maxWidth: .infinity, minHeight: 56)
                .padding(.horizontal, 14)
                .background(LifeOverviewStyle.accent.opacity(disabled ? 0.5 : 1), in: RoundedRectangle(cornerRadius: 18))
                .contentShape(RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).disabled(disabled)
    }
}

/// The small empty-state drawing stays sharp at every display scale.
private struct LifeOpenBookIllustration: Shape {
    func path(in rect: CGRect) -> Path {
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * rect.width, y: rect.minY + y * rect.height) }
        var path = Path()
        path.move(to: p(0.5, 0.18))
        path.addCurve(to: p(0.08, 0.1), control1: p(0.36, 0.02), control2: p(0.18, 0.02))
        path.addLine(to: p(0.08, 0.85))
        path.addCurve(to: p(0.5, 0.92), control1: p(0.25, 0.77), control2: p(0.38, 0.82))
        path.addCurve(to: p(0.92, 0.85), control1: p(0.62, 0.82), control2: p(0.75, 0.77))
        path.addLine(to: p(0.92, 0.1))
        path.addCurve(to: p(0.5, 0.18), control1: p(0.82, 0.02), control2: p(0.64, 0.02))
        path.addLine(to: p(0.5, 0.92))
        path.move(to: p(0.08, 0.13)); path.addQuadCurve(to: p(0.04, 0.19), control: p(0.04, 0.12)); path.addLine(to: p(0.04, 0.94))
        path.addCurve(to: p(0.5, 0.97), control1: p(0.2, 0.87), control2: p(0.38, 0.87))
        path.addCurve(to: p(0.96, 0.94), control1: p(0.62, 0.87), control2: p(0.8, 0.87))
        path.addLine(to: p(0.96, 0.19)); path.addQuadCurve(to: p(0.92, 0.13), control: p(0.96, 0.12))
        for y in [CGFloat(0.29), 0.44, 0.59] {
            path.move(to: p(0.18, y)); path.addQuadCurve(to: p(0.4, y + 0.03), control: p(0.3, y - 0.03))
            path.move(to: p(0.6, y + 0.03)); path.addQuadCurve(to: p(0.82, y), control: p(0.7, y - 0.03))
        }
        return path
    }
}
