import Foundation
let input = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let root = try JSONSerialization.jsonObject(with: input) as! [String: Any]
let responses = root["responses"] as! [[String: Any]]
var decoded = 0
var knownChecked = 0
for response in responses {
    guard let raw = response["life_overview"] else { continue }
    let data = try JSONSerialization.data(withJSONObject: raw)
    let overview = try JSONDecoder().decode(LifeOverview.self, from: data)
    decoded += 1
    if let field = overview.fields.first(where: { $0.topic_id == "SK02" && $0.status == "known" }) {
        let expected = field.evidence.map(\.quote).joined(separator: "\n")
        precondition(!expected.isEmpty)
        precondition(field.content == expected)
        let line = CareLifeSummaryGroups.make(fields: overview.fields).flatMap(\.lines).first(where: { $0.id == "SK02" })!
        precondition(line.text == expected && !line.subdued)
        knownChecked += 1
    }
}
precondition(knownChecked > 0)
let report: [String: Any] = ["decoded_overviews": decoded, "known_partial_answer_projections": knownChecked, "normal_display_keeps_original_quotes": true, "care_display_keeps_original_quotes": true, "full_product_GUI_test": false]
let output = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
print(String(data: output, encoding: .utf8)!)
