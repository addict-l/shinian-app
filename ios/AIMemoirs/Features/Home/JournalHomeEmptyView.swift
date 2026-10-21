import SwiftUI

/// 首页空状态：水彩插画 + 两步引导；已有家人时第一步标记为完成。
struct JournalHomeEmptyView: View {
    let hasPeople: Bool
    let onAction: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            GeometryReader { proxy in
                Image("JournalWelcome").resizable().scaledToFill()
                    .frame(width: proxy.size.width, height: proxy.size.width * 4 / 3)
                    .offset(y: -(proxy.size.width * 4 / 3 - 230) * 0.62)
                    .frame(width: proxy.size.width, height: 230, alignment: .top).clipped()
                    .mask {
                        EllipticalGradient(colors: [.black, .black, .clear], center: .center,
                            startRadiusFraction: 0, endRadiusFraction: 0.65)
                    }
            }.frame(height: 230)
                .padding(.horizontal, -JournalTheme.gutter).padding(.top, 16)
                .accessibilityHidden(true)
            Text("把想念的人，写进第一页").font(JournalTheme.story(20)).foregroundStyle(JournalTheme.ink)
                .multilineTextAlignment(.center).padding(.top, 2)
            VStack(spacing: 0) {
                step("1", title: "添加第一位家人", message: "先记下家人的名字，再留住那些平凡又珍贵的瞬间。",
                     fill: JournalTheme.soft, ink: JournalTheme.accentDeep, done: hasPeople)
                Line().stroke(JournalTheme.line, style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                    .frame(height: 1.5).padding(.leading, 46).padding(.vertical, 14)
                step("2", title: "第一段回忆，慢慢说", message: "一个熟悉的声音，一顿家常饭。从你此刻想起的小事开始。",
                     fill: JournalTheme.sageSoft, ink: JournalTheme.sageInk, done: false)
            }
            .padding(16).journalCard().padding(.top, 16)
            JournalButton(title: "记录第一段回忆", icon: "plus", action: onAction)
                .padding(.top, 18).accessibilityIdentifier("home.newMemory")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("home.empty")
    }

    private func step(_ number: String, title: String, message: String, fill: Color, ink: Color, done: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Group {
                if done { DesignIcon("check", size: 16) } else { Text(number).font(JournalTheme.story(15)) }
            }
            .foregroundStyle(ink).frame(width: 34, height: 34).background(fill, in: Circle())
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(JournalTheme.font(15.5, medium: true)).foregroundStyle(JournalTheme.ink)
                Text(message).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineSpacing(5)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
    }
}

private struct Line: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path(); path.move(to: CGPoint(x: 0, y: rect.midY)); path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY)); return path
    }
}
