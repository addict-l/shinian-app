import SwiftUI

/// Photos and optional text form one right-aligned message, without an album wrapper.
struct JournalUserMessage: View {
    let message: ChatMessage
    let api: any ChatAPI
    let onOpenPhoto: (ChatAttachment) -> Void

    private var columnCount: Int { min(3, message.attachments.count) }

    var body: some View {
        HStack(spacing: 0) {
            Spacer(minLength: 31)
            VStack(alignment: .trailing, spacing: 8) {
                if !message.attachments.isEmpty {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: columnCount), alignment: .trailing, spacing: 8) {
                        ForEach(Array(message.attachments.enumerated()), id: \.element.id) { index, attachment in
                            JournalMessagePhoto(attachment: attachment, api: api,
                                thumbnailMaxPixelSize: message.attachments.count < 3 ? 1024 : 400,
                                label: "讲述照片 \(index + 1)，共 \(message.attachments.count) 张",
                                onOpen: { onOpenPhoto(attachment) })
                                .aspectRatio(message.attachments.count == 1 ? 4.0 / 3.0 : 1, contentMode: .fit)
                        }
                    }
                    .accessibilityIdentifier("chat.message.photos.\(message.id)")
                }
                if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(message.text).font(JournalTheme.font(16)).lineSpacing(6)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(16)
                        .frame(maxWidth: message.attachments.isEmpty ? nil : .infinity, alignment: .leading)
                        .background(JournalTheme.soft, in: RoundedRectangle(cornerRadius: 18))
                        .accessibilityIdentifier("chat.message.text.\(message.id)")
                }
            }.frame(maxWidth: 340, alignment: .trailing)
        }
    }
}
