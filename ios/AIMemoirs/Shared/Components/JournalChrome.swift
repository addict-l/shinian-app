import SwiftUI

/// 页首小字：“拾年 / 星期一”“新的回忆 / 01 添加人物”，其中一段用杏色强调。
struct JournalEyebrow: View {
    let lead: String
    var trail: String? = nil
    /// true 时强调前半段（首页），否则强调后半段（流程步骤）。
    var accentLead = false
    var body: some View {
        HStack(spacing: 0) {
            Text(lead).foregroundStyle(accentLead || trail == nil ? JournalTheme.accent : JournalTheme.muted)
                .font(JournalTheme.font(12, medium: accentLead || trail == nil))
            if let trail {
                Text("　/　").foregroundStyle(JournalTheme.muted).font(JournalTheme.font(12))
                Text(trail).foregroundStyle(accentLead ? JournalTheme.muted : JournalTheme.accent)
                    .font(JournalTheme.font(12, medium: !accentLead))
            }
        }
        .tracking(2.2).lineLimit(1)
    }
}

/// 宋体大标题，30pt、1.35 行高。
struct JournalTitle: View {
    let text: String
    var size: CGFloat = 30
    init(_ text: String, size: CGFloat = 30) { self.text = text; self.size = size }
    var body: some View {
        Text(text).font(JournalTheme.story(size)).tracking(size * 0.02).lineSpacing(0)
            .foregroundStyle(JournalTheme.ink).fixedSize(horizontal: false, vertical: true)
    }
}

struct JournalSubtitle: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(JournalTheme.font(14)).foregroundStyle(JournalTheme.ink2).lineSpacing(4)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// 40pt 暖白圆形按钮，用于返回、关闭和更多操作。
struct JournalRoundButton: View {
    let icon: String
    var label: String = ""
    var background: Color = JournalTheme.surface
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            DesignIcon(icon).foregroundStyle(JournalTheme.ink)
                .frame(width: 40, height: 40).background(background, in: Circle())
                .shadow(color: JournalTheme.shadow.opacity(0.08), radius: 7, x: 0, y: 4)
                .frame(width: 44, height: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityLabel(label)
    }
}

/// 页面顶部 48pt 导航条：左右圆形按钮，中间 16pt 标题。
struct JournalNavBar<Leading: View, Trailing: View>: View {
    var title: String? = nil
    @ViewBuilder var leading: () -> Leading
    @ViewBuilder var trailing: () -> Trailing
    var body: some View {
        ZStack {
            if let title { Text(title).font(JournalTheme.font(16, medium: true)).foregroundStyle(JournalTheme.ink).lineLimit(1) }
            HStack { leading(); Spacer(minLength: 0); trailing() }
        }
        .padding(.horizontal, 14).frame(height: 48)
    }
}

extension JournalNavBar where Trailing == Color {
    init(title: String? = nil, @ViewBuilder leading: @escaping () -> Leading) {
        self.title = title; self.leading = leading; self.trailing = { Color.clear }
    }
}

/// 返回上一层的标准导航条。
struct JournalBackBar: View {
    var title: String? = nil
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        JournalNavBar(title: title) {
            JournalRoundButton(icon: "back", label: "返回") { dismiss() }
        } trailing: { Color.clear.frame(width: 44, height: 44) }
    }
}

/// 设计稿中的胶囊标签。
struct JournalChip: View {
    enum Style { case plain, selected, sage, butter, rose }
    let text: String
    var icon: String? = nil
    var style: Style = .plain
    var compact = false
    var body: some View {
        HStack(spacing: 5) {
            if let icon { DesignIcon(icon, size: 14) }
            Text(text).lineLimit(1)
        }
        .font(JournalTheme.font(compact ? 11.5 : 13))
        .foregroundStyle(ink)
        .padding(.horizontal, compact ? 10 : 14).frame(height: compact ? 24 : 32)
        .background(fill, in: Capsule())
        .overlay { if style == .plain { Capsule().stroke(JournalTheme.line, lineWidth: 1) } }
    }
    private var fill: Color {
        switch style {
        case .plain: JournalTheme.surface
        case .selected: JournalTheme.accent
        case .sage: JournalTheme.sageSoft
        case .butter: JournalTheme.butterSoft
        case .rose: JournalTheme.roseSoft
        }
    }
    private var ink: Color {
        switch style {
        case .plain: JournalTheme.ink2
        case .selected: .white
        case .sage: JournalTheme.sageInk
        case .butter: JournalTheme.butterChipInk
        case .rose: JournalTheme.roseInk
        }
    }
}

/// 标签在框内的输入卡片：12pt 标签 + 16pt 内容，18pt 圆角。
struct JournalFieldBox<Content: View, Accessory: View>: View {
    let label: String
    var vertical: CGFloat = 12
    @ViewBuilder var content: () -> Content
    @ViewBuilder var accessory: () -> Accessory
    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text(label).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                content().font(JournalTheme.font(16)).foregroundStyle(JournalTheme.ink)
            }
            Spacer(minLength: 0)
            accessory()
        }
        .padding(.horizontal, 16).padding(.vertical, vertical)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(JournalTheme.line, lineWidth: 1) }
    }
}

extension JournalFieldBox where Accessory == EmptyView {
    init(label: String, vertical: CGFloat = 12, @ViewBuilder content: @escaping () -> Content) {
        self.label = label; self.vertical = vertical; self.content = content; self.accessory = { EmptyView() }
    }
}

/// 区块标题：宋体 19pt + 右侧说明或链接。
struct JournalSectionHeader<Trailing: View>: View {
    let title: String
    @ViewBuilder var trailing: () -> Trailing
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(JournalTheme.story(19)).foregroundStyle(JournalTheme.ink)
            Spacer()
            trailing()
        }
        .padding(.horizontal, 2).padding(.top, 22).padding(.bottom, 12)
    }
}

/// 色块图标：圆角方块里放线性图标（我的、设置、人物页）。
struct JournalIconTile: View {
    let icon: String
    var fill: Color = JournalTheme.soft
    var ink: Color = JournalTheme.accentDeep
    var size: CGFloat = 38
    var radius: CGFloat = 12
    var iconSize: CGFloat = 22
    var body: some View {
        DesignIcon(icon, size: iconSize).foregroundStyle(ink)
            .frame(width: size, height: size)
            .background(fill, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
    }
}

/// 中文日期，“1946 年 3 月 12 日”的设计稿写法。
enum JournalSpacedDate {
    static func string(_ date: Date) -> String {
        let c = Calendar(identifier: .gregorian).dateComponents([.year, .month, .day], from: date)
        return "\(c.year ?? 0) 年 \(c.month ?? 0) 月 \(c.day ?? 0) 日"
    }
}
