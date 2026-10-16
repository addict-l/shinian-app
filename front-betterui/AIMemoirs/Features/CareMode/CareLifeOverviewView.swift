import SwiftUI

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
    private let modules: [(id: String, title: String, hint: String, symbol: String)] = [
        ("childhood", "成长的地方", "家乡 · 童年", "house"),
        ("growth", "读书或学艺", "学校 · 手艺", "book"),
        ("work", "工作与生活", "工作 · 日常", "briefcase"),
        ("family", "重要家人", "亲情 · 陪伴", "person.2"),
        ("later_life", "如今的生活", "现在 · 爱好", "cup.and.saucer"),
        ("reflection", "人生回望", "往事 · 感悟", "sun.max")
    ]
    private var groups: [(title: String, text: String)] {
        [("小时候", ["home"]), ("读书工作", ["learning", "early_work", "later_work"]), ("家人近况", ["family", "changes", "present"])].map { title, ids in
            let fields = overview.fields.filter { ids.contains($0.topic_id) }
            let quotes = fields.flatMap { $0.evidence.map(\.quote) }
            let text = quotes.isEmpty ? fields.map { $0.title + "：" + $0.content }.joined(separator: "；") : quotes.joined(separator: "\n")
            return (title, text.isEmpty ? "之后可以慢慢补充。" : text)
        }
    }
    var body: some View {
        GeometryReader { proxy in
        ScrollView {
            VStack(spacing: 18) {
                if !typeSize.isAccessibilitySize {
                    CareHeading(title: confirmed ? "想聊些什么？" : "这些经历记对了吗？",
                                subtitle: confirmed ? "选一个话题，慢慢讲。" : "记不清的，可以以后再补。")
                }
                if confirmed {
                    if !typeSize.isAccessibilitySize { Spacer(minLength: 0) }
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: typeSize.isAccessibilitySize ? 1 : 2), spacing: 12) {
                        ForEach(modules, id: \.id) { module in
                            Button { onSelect(module.id) } label: {
                                VStack(spacing: 8) {
                                    Image(systemName: module.symbol).font(.system(size: 28)).foregroundStyle(CareTheme.accent).accessibilityHidden(true)
                                    Text(module.title).font(CareTheme.font(22, bold: true)).fixedSize(horizontal: false, vertical: true)
                                    Text(module.hint).font(CareTheme.font(17)).foregroundStyle(JournalTheme.ink2)
                                }.multilineTextAlignment(.center).frame(maxWidth: .infinity, minHeight: 100).padding(12)
                                    .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                                    .overlay { RoundedRectangle(cornerRadius: 16).stroke(CareTheme.border, lineWidth: 1) }
                                    .contentShape(RoundedRectangle(cornerRadius: 16))
                            }.buttonStyle(.plain).disabled(busy || hasPendingAction)
                                .accessibilityIdentifier("life.module.\(module.id)")
                        }
                    }
                    if !typeSize.isAccessibilitySize { Spacer(minLength: 0) }
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(groups.enumerated()), id: \.offset) { index, group in
                            CareLifeSummaryRow(title: group.title, text: group.text)
                            if index < groups.count - 1 { CareTheme.border.frame(height: 1) }
                        }
                    }.padding(.horizontal, 16).background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 20))
                        .overlay { RoundedRectangle(cornerRadius: 20).stroke(CareTheme.border, lineWidth: 1) }
                        .accessibilityIdentifier("life.summary")
                }
            }.padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 20)
                .frame(minHeight: confirmed && !typeSize.isAccessibilitySize ? proxy.size.height : 0, alignment: .top)
        }.scrollIndicators(.hidden)
        }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if !confirmed {
                    VStack(spacing: 8) {
                        CareButton(title: typeSize.isAccessibilitySize ? "核对好了" : "记对了，下一步", symbol: typeSize.isAccessibilitySize ? nil : "arrow.right", loading: busy, disabled: hasPendingAction, action: onConfirm)
                            .accessibilityIdentifier("life.confirm")
                        if typeSize.isAccessibilitySize {
                            Menu {
                                Button("修改经历", action: onDetails)
                                Button("查看刚才问答", action: onHistory).accessibilityIdentifier("care.life.history")
                            } label: {
                                Text("更多操作").font(CareTheme.font(19)).frame(maxWidth: .infinity, minHeight: 48)
                            }.accessibilityIdentifier("care.life.more")
                        } else { ViewThatFits(in: .horizontal) {
                            HStack(spacing: 12) { editButton; historyButton }
                            VStack(spacing: 8) { editButton; historyButton }
                        } }
                    }.padding(.horizontal, 20).padding(.top, 10).padding(.bottom, 8).background(CareTheme.paper)
                }
            }
    }
    private var editButton: some View {
        Button("修改经历", action: onDetails).font(CareTheme.font(19)).frame(maxWidth: .infinity, minHeight: 48)
            .disabled(busy || hasPendingAction).accessibilityIdentifier("life.details")
    }
    private var historyButton: some View {
        Button("查看刚才问答", action: onHistory).font(CareTheme.font(19)).frame(maxWidth: .infinity, minHeight: 48)
            .accessibilityIdentifier("care.life.history")
    }
}

private struct CareLifeSummaryRow: View {
    let title: String
    let text: String
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var expanded = false
    @State private var fullHeight: CGFloat = 0
    @State private var visibleHeight: CGFloat = 0
    var body: some View {
        Group {
            if !typeSize.isAccessibilitySize {
                HStack(alignment: .top, spacing: 12) {
                    Text(title).font(CareTheme.font(18)).foregroundStyle(CareTheme.accent).frame(width: 74, alignment: .leading)
                    content
                }
            } else { VStack(alignment: .leading, spacing: 8) {
                Text(title).font(CareTheme.font(18)).foregroundStyle(CareTheme.accent)
                content
            } }
        }.padding(.vertical, 16).accessibilityElement(children: .contain)
    }
    private var content: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(text).font(CareTheme.font()).lineSpacing(3).lineLimit(expanded ? nil : 3)
                .frame(maxWidth: .infinity, alignment: .leading)
                .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { visibleHeight = $0 }
                .background(alignment: .topLeading) {
                    Text(text).font(CareTheme.font()).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading).hidden().accessibilityHidden(true)
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { fullHeight = $0 }
                }
            if expanded || fullHeight > visibleHeight + 1 {
                Button(expanded ? "收起" : "展开全文") { expanded.toggle() }.font(CareTheme.font(18)).frame(minHeight: 44)
                    .accessibilityLabel((expanded ? "收起" : "展开") + title)
            }
        }
    }
}
