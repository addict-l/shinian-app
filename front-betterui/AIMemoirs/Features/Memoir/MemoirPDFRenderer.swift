import UIKit
import CoreText
import PDFKit

/// The cover thumbnail and exported cover use exactly the same drawing geometry.
enum MemoirPDFRenderer {
    static let page = CGRect(x: 0, y: 0, width: 148 * 72 / 25.4, height: 210 * 72 / 25.4)
    static let ink = UIColor(red: 0.24, green: 0.19, blue: 0.15, alpha: 1)
    static let paper = UIColor(red: 0.98, green: 0.96, blue: 0.92, alpha: 1)
    static let accent = UIColor(red: 0.70, green: 0.38, blue: 0.24, alpha: 1)
    private static let margin: CGFloat = 38
    private static var width: CGFloat { page.width - margin * 2 }
    private struct TextPage { let text: NSAttributedString; let range: CFRange; let rect: CGRect }
    private enum PageContent { case text(TextPage), illustrated(TextPage, URL, CGRect), photos([URL]) }
    private struct Chapter { let title: String; let start: Int }

    static func font(_ size: CGFloat, heading: Bool = false) -> UIFont {
        if heading { return UIFont(name: "NotoSerifSC-Regular", size: size) ?? UIFont.systemFont(ofSize: size, weight: .medium) }
        return UIFont(name: "PingFangSC-Regular", size: size) ?? .systemFont(ofSize: size)
    }
    private static func attributed(_ text: String, size: CGFloat, heading: Bool = false, color: UIColor = ink,
                                   alignment: NSTextAlignment = .left) -> NSAttributedString {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = alignment; paragraph.lineSpacing = size * 0.40; paragraph.paragraphSpacing = size * 0.75
        return NSAttributedString(string: text, attributes: [.font: font(size, heading: heading), .foregroundColor: color, .paragraphStyle: paragraph])
    }
    private static func height(_ text: NSAttributedString, width: CGFloat) -> CGFloat {
        ceil(text.boundingRect(with: CGSize(width: width, height: .greatestFiniteMagnitude), options: [.usesLineFragmentOrigin, .usesFontLeading], context: nil).height)
    }
    static func coverImage(settings: MemoirSettings, personName: String, photos: [UUID: UIImage]) -> UIImage {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size: page.size, format: format).image { _ in
            drawCover(settings: settings, personName: personName, photo: { photos[$0] })
        }
    }
    private static func background() { paper.setFill(); UIBezierPath(rect: page).fill() }

    static func drawCover(settings: MemoirSettings, personName: String, photo: (UUID) -> UIImage?) {
        let elegant = settings.coverTemplate == .text
        let fill = elegant ? ink : settings.coverTemplate == .collage
            ? UIColor(red: 0.90, green: 0.93, blue: 0.86, alpha: 1)
            : UIColor(red: 0.96, green: 0.90, blue: 0.83, alpha: 1)
        fill.setFill(); UIBezierPath(rect: page).fill()
        let coverInk = elegant ? paper : ink
        let coverAccent = elegant ? UIColor(red: 0.78, green: 0.69, blue: 0.60, alpha: 1) : accent
        let chosen = Array(settings.coverPhotos.prefix(settings.coverTemplate.limit))
        let area = CGRect(x: 46, y: 38, width: page.width - 86, height: 315)
        if !elegant {
            for index in 0..<max(1, chosen.count) {
                let rect: CGRect
                if chosen.count <= 1 { rect = area }
                else if chosen.count == 2 {
                    rect = CGRect(x: area.minX + CGFloat(index) * (area.width + 8) / 2, y: area.minY,
                                  width: (area.width - 8) / 2, height: area.height)
                } else if index == 0 {
                    rect = CGRect(x: area.minX, y: area.minY, width: area.width * 0.58 - 4, height: area.height)
                } else {
                    rect = CGRect(x: area.minX + area.width * 0.58 + 4,
                                  y: area.minY + CGFloat(index - 1) * (area.height + 8) / 2,
                                  width: area.width * 0.42 - 4, height: (area.height - 8) / 2)
                }
                let context = UIGraphicsGetCurrentContext()!; context.saveGState()
                UIBezierPath(roundedRect: rect, cornerRadius: 14).addClip()
                if chosen.indices.contains(index), let image = photo(chosen[index].id) {
                    drawCropped(image, in: rect, crop: chosen[index])
                } else {
                    UIColor(red: 0.91, green: 0.84, blue: 0.75, alpha: 1).setFill(); UIBezierPath(rect: rect).fill()
                    attributed(String(personName.prefix(1)), size: 60, heading: true, color: coverAccent, alignment: .center)
                        .draw(in: CGRect(x: rect.minX, y: rect.midY - 40, width: rect.width, height: 90))
                }
                context.restoreGState()
            }
        }
        let top: CGFloat = elegant ? 124 : area.maxY + 24
        let textBudget: CGFloat = page.height - 78 - top
        let titleText = settings.title.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        let subtitleText = settings.subtitle.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        var titleSize: CGFloat = 38, subtitleSize: CGFloat = 22
        var title = attributed(titleText, size: titleSize, heading: true, color: coverInk)
        var subtitle = attributed(subtitleText, size: subtitleSize, heading: true, color: coverAccent)
        while height(title, width: area.width) + height(subtitle, width: area.width) + 14 > textBudget,
              titleSize > 14 || subtitleSize > 10 {
            if titleSize > 14 { titleSize -= 1 }; if subtitleSize > 10 { subtitleSize -= 0.5 }
            title = attributed(titleText, size: titleSize, heading: true, color: coverInk)
            subtitle = attributed(subtitleText, size: subtitleSize, heading: true, color: coverAccent)
        }
        let titleHeight = height(title, width: area.width)
        title.draw(in: CGRect(x: area.minX, y: top, width: area.width, height: titleHeight + 2))
        if !subtitleText.isEmpty {
            subtitle.draw(in: CGRect(x: area.minX, y: top + titleHeight + 10, width: area.width,
                                    height: height(subtitle, width: area.width) + 2))
        }
        attributed("拾 年 · " + personName, size: 16, color: coverAccent)
            .draw(in: CGRect(x: area.minX, y: page.height - 48, width: area.width, height: 30))
    }
    private static func drawCropped(_ image: UIImage, in rect: CGRect, crop: MemoirCoverPhoto) {
        let factor = max(rect.width / image.size.width, rect.height / image.size.height) * crop.zoom
        let size = CGSize(width: image.size.width * factor, height: image.size.height * factor)
        let origin = CGPoint(x: rect.midX - size.width / 2 + crop.x * (size.width - rect.width) / 2,
                             y: rect.midY - size.height / 2 + crop.y * (size.height - rect.height) / 2)
        let context = UIGraphicsGetCurrentContext()!; context.saveGState()
        context.clip(to: rect); image.draw(in: CGRect(origin: origin, size: size)); context.restoreGState()
    }
    private static func fullImage(_ image: UIImage, in rect: CGRect) {
        let factor = min(rect.width / image.size.width, rect.height / image.size.height)
        let size = CGSize(width: image.size.width * factor, height: image.size.height * factor)
        image.draw(in: CGRect(x: rect.midX - size.width / 2, y: rect.midY - size.height / 2, width: size.width, height: size.height))
    }
    private static func textPages(_ string: NSAttributedString) throws -> [TextPage] {
        let framesetter = CTFramesetterCreateWithAttributedString(string)
        let rect = CGRect(x: margin, y: 46, width: width, height: page.height - 46 - 60)
        var pages: [TextPage] = [], offset = 0
        while offset < string.length {
            let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: offset, length: 0), CGPath(rect: CGRect(origin: .zero, size: rect.size), transform: nil), nil)
            let range = CTFrameGetVisibleStringRange(frame)
            guard range.length > 0 else { throw APIError.server("这段文字暂时无法分页，请调整后重试。") }
            pages.append(TextPage(text: string, range: range, rect: rect)); offset += range.length
        }
        return pages
    }
    private static func drawText(_ value: TextPage) {
        let frame = CTFramesetterCreateFrame(CTFramesetterCreateWithAttributedString(value.text), value.range,
            CGPath(rect: CGRect(origin: .zero, size: value.rect.size), transform: nil), nil)
        let context = UIGraphicsGetCurrentContext()!; context.saveGState()
        context.translateBy(x: value.rect.minX, y: value.rect.maxY); context.scaleBy(x: 1, y: -1)
        context.textMatrix = .identity; CTFrameDraw(frame, context); context.restoreGState()
    }
    /// Measure the actual last line of the same CoreText frame used for drawing.
    private static func usedTextHeight(_ value: TextPage) -> CGFloat {
        let frame = CTFramesetterCreateFrame(CTFramesetterCreateWithAttributedString(value.text), value.range,
            CGPath(rect: CGRect(origin: .zero, size: value.rect.size), transform: nil), nil)
        let lines = CTFrameGetLines(frame) as! [CTLine]
        guard let last = lines.last else { return 0 }
        var origins = Array(repeating: CGPoint.zero, count: lines.count)
        CTFrameGetLineOrigins(frame, CFRange(location: 0, length: 0), &origins)
        var descent: CGFloat = 0
        _ = CTLineGetTypographicBounds(last, nil, &descent, nil)
        return ceil(value.rect.height - origins[lines.count - 1].y + descent)
    }
    /// Two passes: paginate chapters first, then contents; links use the final physical offset.
    static func render(snapshot: MemoirSnapshot, settings: MemoirSettings, photos: [UUID: URL], to url: URL) throws -> Int {
        guard settings.valid else { throw APIError.server("请填写有效的书名和副标题。") }
        let stories = settings.ordered(snapshot.stories)
        guard !stories.isEmpty else { throw APIError.server("至少需要一段已保存回忆。") }
        let chosen = Array(settings.coverPhotos.prefix(settings.coverTemplate.limit))
        if settings.coverTemplate != .text && chosen.isEmpty { throw APIError.server("请先选择封面照片。") }
        let required = Set(stories.flatMap { settings.selectedPhotos($0).map(\.id) } + chosen.map(\.id))
        for id in required {
            guard let path = photos[id], let data = try? Data(contentsOf: path), PhotoCompression.thumbnail(data) != nil else {
                throw APIError.server("选中的照片无法读取，请重试或取消选择后再生成。")
            }
        }
        var pages: [PageContent] = [], chapters: [Chapter] = []
        for story in stories {
            chapters.append(Chapter(title: story.title, start: pages.count + 1))
            var headingSize: CGFloat = 23
            while height(attributed(story.title, size: headingSize, heading: true), width: width) > 210, headingSize > 16 { headingSize -= 1 }
            let text = NSMutableAttributedString(attributedString: attributed(story.title + "\n", size: headingSize, heading: true))
            let meta = [story.dateDescription ?? story.date.map(APIDate.day), story.location].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
            if !meta.isEmpty { text.append(attributed(meta + "\n", size: 10, color: accent)) }
            text.append(attributed(story.content, size: CGFloat(settings.textSize)))
            // Keep a normal chapter title and metadata with the first body lines.
            let titleRange = (text.string as NSString).range(of: story.title)
            text.addAttribute(.kern, value: 0.2, range: titleRange)
            let chapterPages = try textPages(text)
            var images = settings.selectedPhotos(story).compactMap { photos[$0.id] }
            if chapterPages.count == 1, let value = chapterPages.first, let firstPhoto = images.first,
               usedTextHeight(value) <= value.rect.height / 2 {
                guard let data = try? Data(contentsOf: firstPhoto), let image = PhotoCompression.thumbnail(data, maxPixelSize: 2560) else {
                    throw APIError.server("选中的照片无法读取，请重试或取消选择后再生成。")
                }
                let y = value.rect.minY + usedTextHeight(value) + 20
                let h = min(value.rect.maxY - y, width * image.size.height / image.size.width)
                pages.append(.illustrated(value, firstPhoto, CGRect(x: margin, y: y, width: width, height: h)))
                images.removeFirst()
            } else {
                pages += chapterPages.map { .text($0) }
            }
            for index in stride(from: 0, to: images.count, by: 2) { pages.append(.photos(Array(images[index..<min(index + 2, images.count)]))) }
        }
        // Contents rows can wrap, and each row remains intact for link hit testing.
        var toc: [[(Chapter, CGFloat)]] = [[]], used: CGFloat = 0
        for chapter in chapters {
            let h = max(32, height(attributed(chapter.title, size: 12), width: width - 42) + 14)
            if used + h > page.height - 150, !toc.last!.isEmpty { toc.append([]); used = 0 }
            toc[toc.count - 1].append((chapter, h)); used += h
        }
        let renderer = UIGraphicsPDFRenderer(bounds: page)
        try renderer.writePDF(to: url) { context in
            context.beginPage()
            drawCover(settings: settings, personName: snapshot.personName, photo: { id in
                guard let path = photos[id], let data = try? Data(contentsOf: path) else { return nil }
                return PhotoCompression.thumbnail(data, maxPixelSize: 2560)
            })
            for (index, rows) in toc.enumerated() {
                context.beginPage(); background()
                attributed(index == 0 ? "目录" : "目录 · 续", size: 26, heading: true).draw(in: CGRect(x: margin, y: 42, width: width, height: 50))
                var y: CGFloat = 108
                for (chapter, h) in rows {
                    let rect = CGRect(x: margin, y: y, width: width, height: h)
                    attributed(chapter.title, size: 12).draw(in: CGRect(x: rect.minX, y: y, width: width - 42, height: h))
                    attributed(String(chapter.start), size: 11, color: accent, alignment: .right)
                        .draw(in: CGRect(x: rect.maxX - 38, y: y, width: 38, height: h))
                    // PDF link/destination APIs use bottom-left coordinates even
                    // though UIKit text drawing uses top-left coordinates.
                    let link = CGRect(x: rect.minX, y: page.height - rect.maxY, width: rect.width, height: rect.height)
                    context.setDestinationWithName("chapter-\(chapter.start)", for: link)
                    y += h
                }
            }
            for (index, content) in pages.enumerated() {
                autoreleasepool {
                    context.beginPage(); background()
                    if chapters.contains(where: { $0.start == index + 1 }) {
                        context.addDestination(withName: "chapter-\(index + 1)", at: CGPoint(x: margin, y: page.height - 46))
                    }
                    switch content {
                    case .text(let value): drawText(value)
                    case .illustrated(let value, let path, let rect):
                        drawText(value)
                        if let data = try? Data(contentsOf: path), let image = PhotoCompression.thumbnail(data, maxPixelSize: 2560) {
                            fullImage(image, in: rect)
                        }
                    case .photos(let paths):
                        let available = page.height - 114
                        for (i, path) in paths.enumerated() {
                            if let data = try? Data(contentsOf: path), let image = PhotoCompression.thumbnail(data, maxPixelSize: 2560) {
                                let h = (available - CGFloat(paths.count - 1) * 24) / CGFloat(paths.count)
                                fullImage(image, in: CGRect(x: margin, y: 46 + CGFloat(i) * (h + 24), width: width, height: h))
                            }
                        }
                    }
                    attributed(String(index + 1), size: 10, color: accent, alignment: .center)
                        .draw(in: CGRect(x: margin, y: page.height - 36, width: width, height: 22))
                }
            }
        }
        // Resolve internal PDF destinations to native PDFKit go-to annotations.
        // UIGraphicsPDFRenderer emits these links; PDFKit also reads them in export.
        guard let document = PDFDocument(url: url), document.pageCount == 1 + toc.count + pages.count else {
            throw APIError.server("PDF 未能完整生成，请重试。")
        }
        return document.pageCount
    }
}
