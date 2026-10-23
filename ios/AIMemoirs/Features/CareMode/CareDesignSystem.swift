import SwiftUI

/// 关怀版独立令牌，普通版继续使用 JournalTheme。
enum CareTheme {
    static let paper = Color(hex: 0xFBF5EC)
    static let paper2 = Color(hex: 0xF6EDE0)
    static let surface = Color(hex: 0xFFFDF9)
    static let ink = Color(hex: 0x3D2E24)
    static let ink2 = Color(hex: 0x6B5848)
    static let accent = Color(hex: 0xAD5634)
    static let accentTop = Color(hex: 0xC46A41)
    static let accent2 = Color(hex: 0xC2683F)
    static let soft = Color(hex: 0xF8E3D5)
    static let faint = Color(hex: 0xFCF1E9)
    static let border = Color(hex: 0xE6D5C2)
    static let line = Color(hex: 0xEADBC9)
    static let sage = Color(hex: 0x8EA27C)
    static let sageSoft = Color(hex: 0xE6ECDD)
    static let sageInk = Color(hex: 0x4F6443)
    static let butterSoft = Color(hex: 0xFBEFD3)
    static let butterInk = Color(hex: 0x8A611A)
    static let roseSoft = Color(hex: 0xF7E4E1)
    static let roseInk = Color(hex: 0x97504B)
    static let dangerSoft = Color(hex: 0xFBE6E1)
    static let dangerInk = Color(hex: 0x9C3F2F)
    static let recordSoft = Color(hex: 0xFBE3DD)
    static let recordInk = Color(hex: 0xA3402B)
    static let recordDot = Color(hex: 0xD44B33)
    static func font(_ size: CGFloat = 22, bold: Bool = false) -> Font { JournalTheme.font(size, medium: bold) }
}

enum CareTone {
    case apricot, sage, butter, rose
    var fill: Color {
        switch self { case .apricot: CareTheme.soft; case .sage: CareTheme.sageSoft; case .butter: CareTheme.butterSoft; case .rose: CareTheme.roseSoft }
    }
    var ink: Color {
        switch self { case .apricot: CareTheme.accent; case .sage: CareTheme.sageInk; case .butter: CareTheme.butterInk; case .rose: CareTheme.roseInk }
    }
}

struct CarePressStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.76 : 1)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

extension View {
    func carePage() -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(JournalBackdrop().ignoresSafeArea()).foregroundStyle(CareTheme.ink)
    }
    func careDock() -> some View {
        padding(.horizontal, 20).padding(.top, 14).padding(.bottom, 8)
            .background {
                LinearGradient(stops: [.init(color: CareTheme.paper.opacity(0), location: 0), .init(color: CareTheme.paper, location: 0.24)], startPoint: .top, endPoint: .bottom)
                    .ignoresSafeArea(edges: .bottom).allowsHitTesting(false)
            }
    }
}

struct CareButton: View {
    let title: String
    var symbol: String? = nil
    var secondary = false
    var loading = false
    var disabled = false
    var minimumHeight: CGFloat = 68
    var fontSize: CGFloat = 24
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading { ProgressView().tint(secondary ? CareTheme.accent : .white) }
                else if let symbol { Image(systemName: symbol).foregroundStyle(secondary ? CareTheme.accent : .white).accessibilityHidden(true) }
                Text(title).fixedSize(horizontal: false, vertical: true)
            }.font(CareTheme.font(fontSize, bold: true)).multilineTextAlignment(.center)
                .padding(.horizontal, 14).padding(.vertical, 14)
                .frame(maxWidth: .infinity, minHeight: secondary && minimumHeight == 68 ? 64 : minimumHeight)
                .foregroundStyle(secondary ? CareTheme.ink : .white)
                .background {
                    if secondary { RoundedRectangle(cornerRadius: 22).fill(CareTheme.surface) }
                    else { RoundedRectangle(cornerRadius: 22).fill(LinearGradient(colors: [CareTheme.accentTop, CareTheme.accent], startPoint: .top, endPoint: .bottom)) }
                }
                .overlay { if secondary { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) } }
                .shadow(color: CareTheme.accent.opacity(secondary ? 0.03 : 0.22), radius: secondary ? 3 : 12, y: secondary ? 2 : 6)
                .opacity(disabled || loading ? 0.45 : 1).contentShape(RoundedRectangle(cornerRadius: 22))
        }.buttonStyle(CarePressStyle()).disabled(disabled || loading)
    }
}

struct CarePill: View {
    let title: String
    var symbol: String? = nil
    var disabled = false
    let action: () -> Void
    var body: some View {
        Button(action: action) { CarePillLabel(title: title, symbol: symbol) }
            .buttonStyle(CarePressStyle()).disabled(disabled).opacity(disabled ? 0.45 : 1)
    }
}

struct CarePillLabel: View {
    let title: String
    var symbol: String? = nil
    var body: some View {
        HStack(spacing: 7) {
            if let symbol { Image(systemName: symbol).foregroundStyle(CareTheme.accent).accessibilityHidden(true) }
            Text(title).fixedSize(horizontal: false, vertical: true)
        }.font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.ink)
            .padding(.horizontal, 14).padding(.vertical, 10).frame(minHeight: 56)
            .background(CareTheme.surface, in: Capsule())
            .overlay { Capsule().stroke(CareTheme.border, lineWidth: 1.5) }
            .contentShape(Capsule())
    }
}

struct CareMiniButton: View {
    let title: String
    var symbol: String? = "pencil"
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if let symbol { Image(systemName: symbol).accessibilityHidden(true) }
                Text(title).fixedSize(horizontal: false, vertical: true)
            }.font(CareTheme.font(18, bold: true)).foregroundStyle(CareTheme.accent)
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(CareTheme.faint, in: Capsule()).frame(minHeight: 48).contentShape(Rectangle())
        }.buttonStyle(CarePressStyle())
    }
}

struct CareToolbar: View {
    let title: String
    var backTitle = "返回"
    var step: String? = nil
    var backIdentifier = "care.back"
    let onBack: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    var body: some View {
        Group {
            if typeSize.isAccessibilitySize && verticalSizeClass != .compact {
                VStack(spacing: 8) {
                    HStack { backButton; Spacer(minLength: 8); stepLabel }
                    heading
                }
            } else {
                HStack(spacing: 8) {
                    backButton
                    heading
                    stepLabel.frame(minWidth: 76, alignment: .trailing)
                }
            }
        }.padding(.horizontal, 20).padding(.top, 6).padding(.bottom, 10)
    }
    private var heading: some View {
        Text(title).font(CareTheme.font(22, bold: true)).foregroundStyle(CareTheme.ink)
            .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity).accessibilityAddTraits(.isHeader)
    }
    @ViewBuilder private var stepLabel: some View {
        if let step {
            Text(step).font(CareTheme.font(19, bold: true)).foregroundStyle(CareTheme.accent)
                .padding(.horizontal, 11).padding(.vertical, 9).background(CareTheme.faint, in: Capsule())
        } else { Color.clear.frame(width: 76, height: 1).accessibilityHidden(true) }
    }
    private var backButton: some View {
        Button(action: onBack) {
            HStack(spacing: 5) {
                Image(systemName: backTitle == "暂停" ? "pause" : backTitle == "取消" ? "xmark" : "chevron.left").foregroundStyle(CareTheme.accent).accessibilityHidden(true)
                Text(backTitle).fixedSize(horizontal: false, vertical: true)
            }.font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.ink)
                .padding(.horizontal, 12).padding(.vertical, 10).frame(minHeight: 52)
                .background(CareTheme.surface, in: Capsule()).overlay { Capsule().stroke(CareTheme.border, lineWidth: 1.5) }
                .shadow(color: JournalTheme.shadow.opacity(0.06), radius: 3, y: 2)
        }.buttonStyle(CarePressStyle()).accessibilityIdentifier(backIdentifier)
    }
}

struct CareHeading: View {
    let title: String
    var subtitle: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(CareTheme.font(30, bold: true)).foregroundStyle(CareTheme.ink).accessibilityAddTraits(.isHeader)
            if let subtitle { Text(subtitle).font(CareTheme.font(19)).foregroundStyle(CareTheme.ink2) }
        }.multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct CareProgressBar: View {
    let current: Int
    let total: Int
    private var count: Int { max(1, total) }
    var body: some View {
        GeometryReader { geometry in
            if count > 16 {
                Capsule().fill(CareTheme.line).overlay(alignment: .leading) {
                    Capsule().fill(CareTheme.accent2).frame(width: geometry.size.width * min(1, max(0, Double(current) - 0.5) / Double(count)))
                }
            } else {
                HStack(spacing: 4) {
                    ForEach(0..<count, id: \.self) { index in
                        Capsule().fill(Color(hex: 0xEBDDCC)).overlay(alignment: .leading) {
                            if index < current {
                                Capsule().fill(CareTheme.accent2).frame(width: max(0, (geometry.size.width - CGFloat(count - 1) * 4) / CGFloat(count)) * (index == current - 1 ? 0.5 : 1))
                            }
                        }
                    }
                }
            }
        }.frame(height: 7).accessibilityElement(children: .ignore)
            .accessibilityLabel("第 \(current) 个问题，共 \(total) 个")
    }
}

struct CareIconTile: View {
    let symbol: String
    var tone: CareTone = .apricot
    var size: CGFloat = 56
    var body: some View {
        Image(systemName: symbol).font(.system(size: size * 0.48, weight: .medium))
            .foregroundStyle(tone.ink).frame(width: size, height: size)
            .background(tone.fill, in: RoundedRectangle(cornerRadius: size * 0.32)).accessibilityHidden(true)
    }
}

struct CarePersonLine: View {
    let person: FamilyMember
    var text = "故事"
    var body: some View {
        HStack(spacing: 9) {
            JournalAvatar(person: person, size: 38)
            (Text("正在记录 ") + Text(person.relationship.isEmpty ? person.name : "\(person.relationship) · \(person.name)").bold() + Text(" 的\(text)"))
                .font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading).accessibilityElement(children: .combine)
    }
}

struct CareQuestionCard: View {
    var label = "回忆助手问您"
    let text: String
    var compact = false
    var body: some View {
        Group {
            if compact {
                HStack(alignment: .top, spacing: 10) {
                    CareIconTile(symbol: "sparkles", size: 40)
                    Text(text).font(CareTheme.font(19)).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    Label(label, systemImage: "sparkles").font(CareTheme.font(19, bold: true)).foregroundStyle(CareTheme.accent)
                    Text(text).font(CareTheme.font(27, bold: true)).foregroundStyle(CareTheme.ink)
                        .fixedSize(horizontal: false, vertical: true).lineSpacing(5)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(22)
            }
        }.background(LinearGradient(colors: [CareTheme.faint, CareTheme.surface], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: compact ? 22 : 26))
            .overlay { RoundedRectangle(cornerRadius: compact ? 22 : 26).stroke(CareTheme.border.opacity(0.65), lineWidth: 1) }
            .shadow(color: JournalTheme.shadow.opacity(0.06), radius: 8, y: 4)
    }
}

struct CareError: View {
    let message: String
    var retry: (() -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(message, systemImage: "exclamationmark.circle").font(CareTheme.font(19))
                .foregroundStyle(CareTheme.dangerInk).fixedSize(horizontal: false, vertical: true)
            if let retry { CareButton(title: "再试一次", symbol: "arrow.clockwise", secondary: true, action: retry) }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(CareTheme.dangerSoft, in: RoundedRectangle(cornerRadius: 22))
            .accessibilityElement(children: .contain)
    }
}

struct CareBusyOverlay: View {
    let text: String
    var body: some View {
        ZStack {
            CareTheme.paper.opacity(0.94).ignoresSafeArea()
            VStack(spacing: 24) {
                ProgressView().controlSize(.large).tint(CareTheme.accent).scaleEffect(1.4).frame(width: 54, height: 54)
                Text(text).font(CareTheme.font(22, bold: true)).foregroundStyle(CareTheme.ink).multilineTextAlignment(.center)
            }.padding(28)
        }.accessibilityElement(children: .combine).accessibilityAddTraits(.updatesFrequently)
    }
}
