import SwiftUI

/// Photos and optional text form one right-aligned message, without an album wrapper.
struct JournalUserMessage: View {
    let message: ChatMessage
    let api: any ChatAPI
    var localPhotos: [MessagePhoto] = []
    let onOpenPhoto: (ChatAttachment) -> Void

    private var photoCount: Int { localPhotos.isEmpty ? message.attachments.count : localPhotos.count }
    private var columns: [GridItem] { Array(repeating: GridItem(.flexible(), spacing: 6), count: min(3, max(1, photoCount))) }
    private var aspect: CGFloat { photoCount == 1 ? 4.0 / 3.0 : photoCount == 2 ? 129.0 / 96.0 : 1 }

    var body: some View {
        HStack(spacing: 0) {
            Spacer(minLength: 60)
            VStack(alignment: .trailing, spacing: 6) {
                if !localPhotos.isEmpty {
                    LazyVGrid(columns: columns, spacing: 6) {
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
                            .aspectRatio(aspect, contentMode: .fit)
                            .clipped().clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                    }.accessibilityIdentifier("chat.message.photos.\(message.id)")
                } else if !message.attachments.isEmpty {
                    LazyVGrid(columns: columns, alignment: .trailing, spacing: 6) {
                        ForEach(Array(message.attachments.enumerated()), id: \.element.id) { index, attachment in
                            JournalMessagePhoto(attachment: attachment, api: api,
                                thumbnailMaxPixelSize: message.attachments.count < 3 ? 1024 : 400,
                                label: "讲述照片 \(index + 1)，共 \(message.attachments.count) 张",
                                onOpen: { onOpenPhoto(attachment) })
                                .aspectRatio(aspect, contentMode: .fit)
                        }
                    }
                    .accessibilityIdentifier("chat.message.photos.\(message.id)")
                }
                if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(message.text).font(JournalTheme.font(14.5)).lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 14).padding(.vertical, 12)
                        .foregroundStyle(JournalTheme.userMessageInk)
                        .background(JournalTheme.userMessageSurface,
                                    in: UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20,
                                                              bottomTrailingRadius: 20, topTrailingRadius: 4))
                        .accessibilityIdentifier("chat.message.text.\(message.id)")
                }
            }.frame(maxWidth: 264, alignment: .trailing)
        }
    }
}
