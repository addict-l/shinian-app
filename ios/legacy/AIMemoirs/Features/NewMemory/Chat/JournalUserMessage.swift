import SwiftUI

/// Photos and optional text form one right-aligned message, without an album wrapper.
struct JournalUserMessage: View {
    let message: ChatMessage
    let api: any ChatAPI
    var localPhotos: [MessagePhoto] = []
    let onOpenPhoto: (ChatAttachment) -> Void

    private var columnCount: Int { min(3, message.attachments.count) }

    var body: some View {
        HStack(spacing: 0) {
            Spacer(minLength: 31)
            VStack(alignment: .trailing, spacing: 8) {
                if !localPhotos.isEmpty {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: min(3, localPhotos.count)), spacing: 8) {
                        ForEach(Array(localPhotos.enumerated()), id: \.element.id) { index, photo in
                            GeometryReader { geometry in
                                Group {
                                    if let thumbnail = photo.thumbnail { Image(uiImage: thumbnail).resizable().scaledToFill() }
                                    else { Rectangle().fill(JournalTheme.soft).overlay(Image(systemName: "photo")) }
                                }
                                .frame(width: geometry.size.width, height: geometry.size.height)
                                .clipped().contentShape(Rectangle())
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel("待发送照片 \(index + 1)，共 \(localPhotos.count) 张")
                                .accessibilityIdentifier("chat.pendingPhoto.\(photo.id)")
                            }
                            .aspectRatio(localPhotos.count == 1 ? 4.0 / 3.0 : 1, contentMode: .fit)
                            .clipped().clipShape(RoundedRectangle(cornerRadius: 14))
                        }
                    }.accessibilityIdentifier("chat.message.photos.\(message.id)")
                } else if !message.attachments.isEmpty {
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
                        .foregroundStyle(JournalTheme.userMessageInk)
                        .background(JournalTheme.userMessageSurface,
                                    in: UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20,
                                                              bottomTrailingRadius: 6, topTrailingRadius: 20))
                        .overlay {
                            UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20,
                                                   bottomTrailingRadius: 6, topTrailingRadius: 20)
                                .strokeBorder(JournalTheme.userMessageBorder, lineWidth: 1)
                        }
                        .accessibilityIdentifier("chat.message.text.\(message.id)")
                }
            }.frame(maxWidth: 340, alignment: .trailing)
        }
    }
}
