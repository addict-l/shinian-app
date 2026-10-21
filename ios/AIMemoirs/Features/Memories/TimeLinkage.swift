import SwiftUI

struct TimePreviewInput: Equatable, Identifiable {
    let id = UUID()
    let title: String
    let content: String
    let oldTime: InformationDimension
    let newTime: InformationDimension
    func fields() throws -> [String: Any] {
        func dimension(_ value: InformationDimension) throws -> Any { try JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) }
        return ["title": title, "summary": content, "old_time": try dimension(oldTime), "new_time": try dimension(newTime)]
    }
}
struct TimeSuggestion: Decodable, Identifiable {
    let id: String
    let field: String
    let start: Int
    let length: Int
    let before: String
    let after: String?
    let context: String
    let ambiguous: Bool
    let reason: String
}
struct TimePreview: Decodable {
    let snapshot: String
    let suggestions: [TimeSuggestion]
    let message: String
    /// Validate all ranges before applying anything. Offsets refer to the captured UTF-16 snapshot.
    func applying(_ selected: Set<String>, to input: TimePreviewInput) throws -> (String, String) {
        var title = input.title, body = input.content
        for field in ["title", "summary"] {
            let source = field == "title" ? input.title : input.content
            let edits = suggestions.filter { $0.field == field && selected.contains($0.id) }.sorted { $0.start > $1.start }
            var result = source
            var boundary = (source as NSString).length
            for item in edits {
                guard let after = item.after, item.start >= 0, item.length > 0, item.start + item.length <= boundary,
                      let range = Range(NSRange(location: item.start, length: item.length), in: result),
                      String(result[range]) == item.before else { throw APIError.server("文字已变化，请重新核对时间。") }
                result.replaceSubrange(range, with: after); boundary = item.start
            }
            if field == "title" { title = result } else { body = result }
        }
        guard title.count <= 200, body.count <= 100000 else { throw APIError.server("修改后文字过长，请减少内容再应用。") }
        return (title, body)
    }
}

struct TimeDimensionEditor: View {
    @Binding var value: InformationDimension
    var identifier: String
    @FocusState private var editing: Bool
    var body: some View {
        Picker("记录方式", selection: Binding(get: { value.status }, set: { status in
            value.status = status
            if status == .missing { value.value = nil }
            else if status == .unknown { value.value = "记不清了" }
            else if status == .withheld { value.value = "暂时不想说" }
            else if value.value == nil { value.value = "" }
        })) {
            Text("确定").tag(InformationStatus.known); Text("大概记得").tag(InformationStatus.approximate)
            Text("记不清").tag(InformationStatus.unknown); Text("暂时不想说").tag(InformationStatus.withheld)
            Text("待补充").tag(InformationStatus.missing)
        }.accessibilityIdentifier(identifier + ".status")
        if value.status != .missing {
            TextField("例如：2008年夏天，或 2008-06-01", text: Binding(get: { value.value ?? "" }, set: { value.value = $0 }))
                .focused($editing).submitLabel(.done).onSubmit { editing = false }
                .accessibilityIdentifier(identifier)
        }
        if value.user_edited == true { Label("用户修改的时间", systemImage: "pencil").font(.footnote).foregroundStyle(JournalTheme.ink2) }
    }
}

/// Suggestions are ephemeral; cancel, errors and retries leave the parent form intact.
struct TimeLinkageSheet: View {
    let input: TimePreviewInput
    let load: () async throws -> TimePreview
    let apply: (TimePreviewInput, TimePreview, Set<String>) throws -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var preview: TimePreview?
    @State private var selected: Set<String> = []
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section("回忆时间") {
                    LabeledContent("原时间", value: input.oldTime.value ?? "待补充")
                    LabeledContent("修改为", value: input.newTime.value ?? "待补充")
                }
                if busy { Section { ProgressView("正在核对时间…") } }
                if let error { Section { Text(error).foregroundStyle(.red); Button("重试核对") { Task { await fetch() } } } }
                if let preview {
                    Section { Text(preview.message).font(.subheadline).foregroundStyle(JournalTheme.ink2) }
                    ForEach(["title", "summary"], id: \.self) { field in
                        let suggestions = preview.suggestions.filter { $0.field == field }
                        Section(field == "title" ? "标题" : "正文") {
                            if suggestions.isEmpty { Text("未找到对应时间，保留原文。") }
                            ForEach(suggestions) { item in
                                VStack(alignment: .leading, spacing: 12) {
                                    Text(item.context).font(.body)
                                    if let after = item.after {
                                        Toggle(isOn: Binding(get: { selected.contains(item.id) }, set: { value in
                                            if value { selected.insert(item.id) } else { selected.remove(item.id) }
                                        })) {
                                            VStack(alignment: .leading, spacing: 6) {
                                                Text("原文：" + item.before).foregroundStyle(JournalTheme.ink2)
                                                Text("改为：" + after).fontWeight(.medium)
                                            }
                                        }.accessibilityIdentifier("time.suggestion." + item.id)
                                    }
                                    Label(item.reason, systemImage: item.ambiguous ? "exclamationmark.circle" : "checkmark.circle")
                                        .font(.footnote).foregroundStyle(JournalTheme.ink2)
                                }.padding(.vertical, 8)
                            }
                        }
                    }
                    Section { Text("这里只更新编辑框中的文字，点击保存后才会写入回忆。未选中的内容请继续手动核对。")
                            .font(.footnote).foregroundStyle(JournalTheme.ink2) }
                }
            }.scrollDismissesKeyboard(.interactively).scrollContentBackground(.hidden).background(JournalTheme.paper)
                .navigationTitle("核对时间文字").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("返回编辑") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("应用所选") {
                            guard let preview else { return }
                            do { try apply(input, preview, selected); dismiss() } catch { self.error = error.localizedDescription }
                        }.disabled(busy || preview == nil || selected.isEmpty).accessibilityIdentifier("time.apply")
                    }
                }
        }.task { await fetch() }
    }
    private func fetch() async {
        guard !busy else { return }; busy = true; error = nil; preview = nil; selected = []
        defer { busy = false }
        do { preview = try await load(); selected = [] } catch { self.error = error.localizedDescription }
    }
}
