import SwiftUI

/// 表单内联的常用身份选项；仅返回称呼，不修改人物数据或限制自定义身份。
struct JournalRelationshipOptions: View {
    let selection: String
    let onSelect: (String) -> Void
    private let roles = ["爷爷", "奶奶", "外公", "外婆", "爸爸", "妈妈", "姑姑", "舅舅"]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("选一个熟悉的称呼")
                .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.accent)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 64), spacing: 8)], spacing: 8) {
                ForEach(roles, id: \.self) { role in
                    Button { onSelect(role) } label: {
                        Text(role).font(JournalTheme.font(14))
                            .foregroundStyle(selection == role ? JournalTheme.surface : JournalTheme.accent)
                            .frame(maxWidth: .infinity).frame(minHeight: 44)
                            .background(selection == role ? JournalTheme.accent : JournalTheme.surface.opacity(0.8),
                                        in: RoundedRectangle(cornerRadius: 12))
                    }.buttonStyle(.plain)
                        .accessibilityAddTraits(selection == role ? .isSelected : [])
                        .accessibilityIdentifier("member.role.\(role)")
                }
            }
            Text("也可以在输入框里填写其他称呼")
                .font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
        }.padding(14)
            .background(JournalTheme.soft.opacity(0.65), in: RoundedRectangle(cornerRadius: 16))
    }
}
