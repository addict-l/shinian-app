import SwiftUI

/// 表单内联的常用身份选项；仅返回称呼，不修改人物数据或限制自定义身份。
struct JournalRelationshipOptions: View {
    let selection: String
    let onSelect: (String) -> Void
    private let roles = ["爷爷", "奶奶", "外公", "外婆", "爸爸", "妈妈", "姑姑", "舅舅"]

    var body: some View {
        JournalFlowLayout(spacing: 8) {
            ForEach(roles, id: \.self) { role in
                Button { onSelect(role) } label: {
                    JournalChip(text: role, style: selection == role ? .selected : .plain)
                        .contentShape(Capsule())
                }.buttonStyle(.plain)
                    .accessibilityAddTraits(selection == role ? .isSelected : [])
                    .accessibilityIdentifier("member.role.\(role)")
            }
        }
    }
}

/// 自动换行的横向排布。
struct JournalFlowLayout: Layout {
    var spacing: CGFloat = 8
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: rows.last.map { $0.y + $0.height } ?? 0)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for row in arrange(width: bounds.width, subviews: subviews) {
            for item in row.items {
                subviews[item.index].place(at: CGPoint(x: bounds.minX + item.x, y: bounds.minY + row.y), proposal: ProposedViewSize(item.size))
            }
        }
    }
    private struct Row { var items: [(index: Int, x: CGFloat, size: CGSize)] = []; var y: CGFloat = 0; var width: CGFloat = 0; var height: CGFloat = 0 }
    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows = [Row()]
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty, rows[rows.count - 1].width + spacing + size.width > width {
                let last = rows[rows.count - 1]
                rows.append(Row(y: last.y + last.height + spacing))
            }
            let x = rows[rows.count - 1].items.isEmpty ? 0 : rows[rows.count - 1].width + spacing
            rows[rows.count - 1].items.append((index, x, size))
            rows[rows.count - 1].width = x + size.width
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
        }
        return rows
    }
}
