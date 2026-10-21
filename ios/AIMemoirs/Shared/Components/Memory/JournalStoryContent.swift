import SwiftUI
import UIKit

/// 已保存回忆的阅读版式：满版头图、人物、标题、时间/地点/感受卡和首字下沉正文。
struct JournalStoryContent: View {
    let memory: MemoryEvent
    let identity: String
    var person: FamilyMember? = nil
    var photoAPI: (any MemoryAPI)? = nil
    var topInset: CGFloat = 0
    private var hasPhoto: Bool { memory.imageData != nil || memory.imageName != nil }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if hasPhoto {
                    JournalPhoto(memory: memory, height: 360, radius: 0)
                        .overlay {
                            LinearGradient(stops: [.init(color: Color(red: 60 / 255, green: 40 / 255, blue: 25 / 255).opacity(0.25), location: 0),
                                                   .init(color: .clear, location: 0.3), .init(color: .clear, location: 0.7),
                                                   .init(color: JournalTheme.paper, location: 1)], startPoint: .top, endPoint: .bottom)
                        }
                        .padding(.bottom, -60)
                } else {
                    Color.clear.frame(height: topInset + 8)
                }
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 8) {
                        if let person { JournalAvatar(person: person, size: 30) }
                        Text(identity).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2)
                    }
                    Text(memory.title).font(JournalTheme.story(28)).lineSpacing(0).foregroundStyle(JournalTheme.ink)
                        .fixedSize(horizontal: false, vertical: true).padding(.top, 10)
                    facts.padding(.top, 14)
                    JournalDropCapText(text: memory.content).padding(.top, 16)
                    if let photoAPI, memory.mediaAssets.count > (hasPhoto ? 1 : 0) {
                        Text("这段回忆的照片").font(JournalTheme.font(12, medium: true)).foregroundStyle(JournalTheme.muted).padding(.top, 28)
                        ForEach(memory.mediaAssets.dropFirst(hasPhoto ? 1 : 0)) { photo in
                            MemoryPhotoView(attachment: photo, api: photoAPI).frame(maxWidth: .infinity, minHeight: 160)
                                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous)).padding(.top, 12)
                        }
                    }
                }.padding(.horizontal, JournalTheme.gutter).padding(.bottom, 40)
            }
        }
        .scrollIndicators(.hidden)
        .ignoresSafeArea(edges: hasPhoto ? .top : [])
    }

    private var facts: some View {
        HStack(spacing: 0) {
            fact("时间", memory.dateLabel)
            JournalTheme.line.frame(width: 1, height: 38)
            fact("地点", valid(memory.location) ?? "待补充")
            JournalTheme.line.frame(width: 1, height: 38)
            fact("感受", valid(memory.information.feeling.value) ?? "待补充", ink: JournalTheme.roseInk)
        }
        .padding(.vertical, 12).padding(.horizontal, 6)
        .journalCard()
    }
    private func fact(_ title: String, _ value: String, ink: Color = JournalTheme.ink) -> some View {
        VStack(spacing: 3) {
            Text(title).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
            Text(value).font(JournalTheme.font(14)).foregroundStyle(ink).lineLimit(1).minimumScaleFactor(0.8)
        }.frame(maxWidth: .infinity).accessibilityElement(children: .combine)
    }
    private func valid(_ value: String?) -> String? {
        guard let value, !value.isEmpty, value != "未提及", value != "待补充" else { return nil }
        return value
    }
}

/// 宋体正文，首字放大下沉两行，其余文字环绕。
struct JournalDropCapText: UIViewRepresentable {
    let text: String
    var size: CGFloat = 16

    func makeUIView(context: Context) -> DropCapView { DropCapView() }
    func updateUIView(_ view: DropCapView, context: Context) { view.configure(text: text, size: size) }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: DropCapView, context: Context) -> CGSize? {
        let width = proposal.width ?? UIScreen.main.bounds.width - 44
        return CGSize(width: width, height: uiView.height(for: width))
    }

    final class DropCapView: UIView {
        private let cap = UILabel()
        private let body = UITextView()
        private var capSize: CGSize = .zero
        override init(frame: CGRect) {
            super.init(frame: frame)
            body.isEditable = false; body.isScrollEnabled = false; body.isSelectable = true
            body.backgroundColor = .clear; body.textContainerInset = .zero; body.textContainer.lineFragmentPadding = 0
            addSubview(body); addSubview(cap)
            isAccessibilityElement = false
        }
        required init?(coder: NSCoder) { fatalError() }
        private var lineHeight: CGFloat = 32
        func configure(text: String, size: CGFloat) {
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            let first = trimmed.first.map(String.init) ?? ""
            let rest = String(trimmed.dropFirst())
            lineHeight = size * 2
            cap.attributedText = NSAttributedString(string: first, attributes: [
                .font: UIFont(name: "NotoSerifSC-Regular", size: size * 2.875) ?? .systemFont(ofSize: size * 2.875),
                .foregroundColor: UIColor(JournalTheme.accent)])
            cap.isAccessibilityElement = false
            capSize = cap.intrinsicContentSize
            let paragraph = NSMutableParagraphStyle(); paragraph.minimumLineHeight = lineHeight; paragraph.maximumLineHeight = lineHeight
            let font = UIFont(name: "NotoSerifSC-Regular", size: size) ?? .systemFont(ofSize: size)
            body.attributedText = NSAttributedString(string: rest, attributes: [
                .font: font, .paragraphStyle: paragraph, .foregroundColor: UIColor(JournalTheme.storyInk),
                .baselineOffset: (lineHeight - font.lineHeight) / 4])
            body.accessibilityLabel = trimmed
            setNeedsLayout()
        }
        private var exclusion: CGRect { CGRect(x: 0, y: 0, width: capSize.width + 8, height: lineHeight * 2 - 1) }
        func height(for width: CGFloat) -> CGFloat {
            body.textContainer.exclusionPaths = [UIBezierPath(rect: exclusion)]
            let fitted = body.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude)).height
            return max(fitted, lineHeight * 2)
        }
        override func layoutSubviews() {
            super.layoutSubviews()
            body.textContainer.exclusionPaths = [UIBezierPath(rect: exclusion)]
            body.frame = bounds
            cap.frame = CGRect(x: 0, y: 6, width: capSize.width, height: capSize.height).offsetBy(dx: 0, dy: (lineHeight * 2 - capSize.height) / 2 - 6)
        }
    }
}
