import SwiftUI

struct CareAddPersonView: View {
    @Binding var draft: FamilyMemberDraft
    let loading: Bool
    let error: String?
    let onAdd: () -> Void
    let onClose: () -> Void
    private enum Field { case relationship, name }
    @FocusState private var field: Field?
    @State private var showingBirthday = false
    @State private var birthday = APIDate.parseDay("1950-01-01")!
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "添加家人", onBack: onClose).disabled(loading)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    CareHeading(title: "先记下家人的名字", subtitle: "这些资料，之后也可以查看。")
                    Text("怎么称呼这位家人").font(CareTheme.font(20, bold: true))
                    TextField("例如爷爷、奶奶", text: $draft.relationship).font(CareTheme.font()).padding(14)
                        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                        .focused($field, equals: .relationship).submitLabel(.next).onSubmit { field = .name }
                        .accessibilityIdentifier("member.relationship")
                    Text("真实姓名").font(CareTheme.font(20, bold: true))
                    TextField("填写家人的姓名", text: $draft.realName).textContentType(.name).font(CareTheme.font()).padding(14)
                        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                        .focused($field, equals: .name).submitLabel(.done).onSubmit { field = nil }
                        .accessibilityIdentifier("member.realName")
                    Text("生日").font(CareTheme.font(20, bold: true))
                    CareButton(title: draft.birthDate.map(JournalSpacedDate.string) ?? "选择家人的生日", symbol: "calendar", secondary: true) {
                        field = nil; birthday = draft.birthDate ?? APIDate.parseDay("1950-01-01")!; showingBirthday = true
                    }.accessibilityIdentifier("member.birthday")
                    if let error { CareError(message: error) }
                }.padding(20)
            }.scrollDismissesKeyboard(.interactively).disabled(loading)
            CareButton(title: "添加并开始讲述", loading: loading, disabled: !draft.isValid(), action: onAdd)
                .padding(20).accessibilityIdentifier("member.add")
        }.background(CareTheme.paper.ignoresSafeArea())
            .sheet(isPresented: $showingBirthday) {
                NavigationStack {
                    DatePicker("家人的生日", selection: $birthday, in: ...Date(), displayedComponents: .date)
                        .datePickerStyle(.wheel).padding()
                        .navigationTitle("家人的生日").navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) { Button("取消") { showingBirthday = false } }
                            ToolbarItem(placement: .confirmationAction) {
                                Button("确定") { draft.birthDate = birthday; showingBirthday = false }.accessibilityIdentifier("member.confirmBirthday")
                            }
                        }
                }.presentationDetents([.medium, .large]).environment(\.locale, Locale(identifier: "zh_CN"))
            }
    }
}
