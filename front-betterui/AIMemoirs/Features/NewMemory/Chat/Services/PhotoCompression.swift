import Foundation
import ImageIO
import UIKit

enum PhotoCompression {
    static func thumbnail(_ data: Data, maxPixelSize: Int = 256) -> UIImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: maxPixelSize
              ] as CFDictionary) else { return nil }
        return UIImage(cgImage: image)
    }
    /// Decode a thumbnail directly to bound memory for large photos and apply EXIF orientation.
    static func compress(_ data: Data) throws -> Data {
        guard let image = thumbnail(data, maxPixelSize: 2560) else { throw APIError.server("照片无法读取，请重新选择。") }
        for quality in [0.85, 0.65, 0.45] {
            if let jpeg = image.jpegData(compressionQuality: quality), jpeg.count <= 8 * 1024 * 1024 {
                return jpeg
            }
        }
        throw APIError.server("照片压缩后仍超过 8 MB，请选择较小的图片。")
    }
}
