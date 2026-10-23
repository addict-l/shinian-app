import SwiftUI

struct CareLifeSummaryLine: Identifiable {
    let id: String
    let text: String
    let subdued: Bool
}

struct CareLifeSummaryGroup: Identifiable {
    let title: String
    let symbol: String
    let tone: CareTone
    let fieldIDs: [String]
    let lines: [CareLifeSummaryLine]
    var id: String { title }
    var text: String { lines.isEmpty ? "之后可以慢慢补充。" : lines.map(\.text).joined(separator: "\n") }
}

/// Keep the original words visible for both interview catalogs, including fields
/// added by a future catalog that this version of the app does not recognize.
enum CareLifeSummaryGroups {
    private static let legacy: [(String, [String], String, CareTone)] = [
        ("小时候", ["home"], "house", .butter),
        ("读书工作", ["learning", "early_work", "later_work"], "book", .sage),
        ("家人近况", ["family", "changes", "present"], "person.2", .rose)
    ]
    private static let skeleton: [(String, [String], String, CareTone)] = [
        ("出生与家乡", ["SK01", "SK01b", "SK01c", "SK02"], "house", .butter),
        ("小时候的家", ["SK03", "SK03b", "SK03c", "SK03d", "SK04"], "person.2", .sage),
        ("性格与一生", ["SK05", "SK06"], "sun.max", .rose)
    ]

    static func make(fields: [LifeField]) -> [CareLifeSummaryGroup] {
        let definitions = fields.contains { $0.topic_id.hasPrefix("SK") } ? skeleton : legacy
        let groupedIDs = Set(definitions.flatMap { $0.1 })
        var result = definitions.map { title, ids, symbol, tone in
            group(title: title, symbol: symbol, tone: tone, fields: fields.filter { ids.contains($0.topic_id) })
        }
        let remaining = fields.filter { !groupedIDs.contains($0.topic_id) }
        if !remaining.isEmpty {
            result.append(group(title: "其他", symbol: "text.book.closed", tone: .apricot, fields: remaining))
        }
        return result
    }

    private static func group(title: String, symbol: String, tone: CareTone, fields: [LifeField]) -> CareLifeSummaryGroup {
        let lines = fields.compactMap { field -> CareLifeSummaryLine? in
            guard field.status != "pending" else { return nil }
            let quotes = field.evidence.map(\.quote).filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            if !quotes.isEmpty {
                return CareLifeSummaryLine(id: field.id, text: quotes.joined(separator: "\n"), subdued: false)
            }
            let status = ["skipped": "暂时跳过", "unknown": "记不清", "declined": "暂时不想讲"][field.status] ?? "待补充"
            return CareLifeSummaryLine(id: field.id, text: field.title + "：" + status, subdued: true)
        }
        return CareLifeSummaryGroup(title: title, symbol: symbol, tone: tone, fieldIDs: fields.map(\.id), lines: lines)
    }
}

struct CareLifeOverviewView: View {
    let overview: LifeOverview
    let busy: Bool
    let hasPendingAction: Bool
    let onDetails: () -> Void
    let onConfirm: () -> Void
    let onSelect: (String) -> Void
    let onHistory: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    private var confirmed: Bool { overview.status == "confirmed" }
    private let secondaryActionHeight: CGFloat = 88
    private let modules: [(id: String, title: String, hint: String, symbol: String, tone: CareTone)] = [
        ("childhood", "成长的地方", "家乡 · 童年", "house", .butter),
        ("growth", "读书或学艺", "学校 · 手艺", "book", .sage),
        ("work", "工作与生活", "工作 · 日常", "briefcase", .apricot),
        ("family", "重要家人", "亲情 · 陪伴", "person.2", .rose),
        ("later_life", "如今的生活", "现在 · 爱好", "cup.and.saucer", .sage),
        ("reflection", "人生回望", "往事 · 感悟", "sun.max", .butter)
    ]
    private var groups: [CareLifeSummaryGroup] { CareLifeSummaryGroups.make(fields: overview.fields) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                CareHeading(title: confirmed ? "想聊些什么？" : "这些经历记对了吗？",
                            subtitle: confirmed ? "选一个话题，慢慢讲。" : "记不清的，可以以后再补。")
                if confirmed {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: typeSize.isAccessibilitySize ? 1 : 2), spacing: 12) {
                        ForEach(modules, id: \.id) { module in
                            Button { onSelect(module.id) } label: {
                                VStack(alignment: .leading, spacing: 12) {
                                    Image(systemName: module.symbol).font(.system(size: 28, weight: .medium))
                                        .foregroundStyle(module.tone.ink).frame(width: 56, height: 56)
                                        .background(CareTheme.surface, in: Circle()).accessibilityHidden(true)
                                    Text(module.title).font(CareTheme.font(23, bold: true)).foregroundStyle(CareTheme.ink)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Text(module.hint).font(CareTheme.font(17)).foregroundStyle(module.tone.ink)
                                        .fixedSize(horizontal: false, vertical: true)
                                }.frame(maxWidth: .infinity, minHeight: 122, alignment: .topLeading).padding(18)
                                    .background(module.tone.fill, in: RoundedRectangle(cornerRadius: 26))
                                    .contentShape(RoundedRectangle(cornerRadius: 26))
                            }.buttonStyle(.plain).disabled(busy || hasPendingAction)
                                .accessibilityIdentifier("life.module.\(module.id)")
                        }
                    }
                    HStack {
                        Spacer(minLength: 0)
                        CarePill(title: "帮我挑一个", symbol: "shuffle", disabled: busy || hasPendingAction) {
                            if let module = modules.randomElement() { onSelect(module.id) }
                        }.accessibilityIdentifier("care.life.randomTopic")
                        Spacer(minLength: 0)
                    }.padding(.top, 2)
                } else {
                    VStack(spacing: 14) {
                        ForEach(groups) { group in
                            CareLifeSummaryRow(group: group, disabled: busy || hasPendingAction, onEdit: onDetails)
                        }
                    }.accessibilityIdentifier("life.summary")
                }
            }.padding(.horizontal, 20).padding(.top, 16).padding(.bottom, 24)
        }.scrollIndicators(.hidden)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if !confirmed {
                    VStack(spacing: 12) {
                        CareButton(title: typeSize.isAccessibilitySize ? "核对好了" : "记对了，下一步", symbol: "arrow.right", loading: busy, disabled: hasPendingAction, action: onConfirm)
                            .accessibilityIdentifier("life.confirm")
                        if typeSize.isAccessibilitySize {
                            Menu {
                                Button("修改经历", action: onDetails)
                                Button("查看刚才问答", action: onHistory).accessibilityIdentifier("care.life.history")
                            } label: {
                                Label("更多操作", systemImage: "ellipsis.circle").font(CareTheme.font(20, bold: true))
                                    .frame(maxWidth: .infinity, minHeight: 56)
                                    .foregroundStyle(CareTheme.accent)
                                    .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                                    .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) }
                            }.disabled(busy || hasPendingAction).accessibilityIdentifier("care.life.more")
                        } else {
                            ViewThatFits(in: .horizontal) {
                                HStack(spacing: 12) { editButton; historyButton }
                                VStack(spacing: 10) { editButton; historyButton }
                            }
                        }
                    }.careDock()
                }
            }
    }

    private var editButton: some View {
        CareButton(title: "修改经历", symbol: "pencil", secondary: true, disabled: busy || hasPendingAction, minimumHeight: secondaryActionHeight, fontSize: 21, action: onDetails)
            .accessibilityIdentifier("life.details")
    }
    private var historyButton: some View {
        CareButton(title: "查看刚才问答", symbol: "bubble.left", secondary: true, disabled: busy || hasPendingAction, minimumHeight: secondaryActionHeight, fontSize: 21, action: onHistory)
            .accessibilityIdentifier("care.life.history")
    }
}

private struct CareLifeSummaryRow: View {
    let group: CareLifeSummaryGroup
    let disabled: Bool
    let onEdit: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var expanded = false
    @State private var fullHeight: CGFloat = 0
    @State private var visibleHeight: CGFloat = 0

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            if !typeSize.isAccessibilitySize { CareIconTile(symbol: group.symbol, tone: group.tone, size: 56) }
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 10) {
                    Text(group.title).font(CareTheme.font(20, bold: true)).foregroundStyle(group.tone.ink)
                        .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                    CareMiniButton(title: "改", symbol: "pencil", action: onEdit)
                        .disabled(disabled).accessibilityLabel("修改" + group.title)
                }
                content
            }
        }.padding(18).journalCard(radius: 26, fill: CareTheme.surface)
            .accessibilityElement(children: .contain)
    }

    private var summary: Text {
        if group.lines.isEmpty { return Text(group.text).foregroundColor(CareTheme.ink2) }
        var result = AttributedString()
        for (index, line) in group.lines.enumerated() {
            var part = AttributedString((index == 0 ? "" : "\n") + line.text)
            part.foregroundColor = line.subdued ? CareTheme.ink2 : CareTheme.ink
            result.append(part)
        }
        return Text(result)
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 8) {
            summary.font(CareTheme.font(22)).lineSpacing(7).lineLimit(expanded ? nil : 3)
                .frame(maxWidth: .infinity, alignment: .leading)
                .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { visibleHeight = $0 }
                .background(alignment: .topLeading) {
                    Text(group.text).font(CareTheme.font(22)).lineSpacing(7).fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading).hidden().accessibilityHidden(true)
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { fullHeight = $0 }
                }
            if expanded || fullHeight > visibleHeight + 1 {
                CareMiniButton(title: expanded ? "收起" : "展开全文", symbol: expanded ? "chevron.up" : "chevron.down") { expanded.toggle() }
                    .accessibilityLabel((expanded ? "收起" : "展开") + group.title)
            }
        }
    }
}
