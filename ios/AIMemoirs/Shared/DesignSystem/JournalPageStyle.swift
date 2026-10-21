import SwiftUI
import UIKit

/// 暖纸底色：右上角杏色、左下角鼠尾草绿的椭圆柔光。
struct JournalBackdrop: View {
    var body: some View {
        GeometryReader { proxy in
            let w = proxy.size.width, h = proxy.size.height
            ZStack {
                JournalTheme.paper
                EllipticalGradient(stops: [.init(color: Color(hex: 0xFDE9D9), location: 0), .init(color: Color(hex: 0xFDE9D9, opacity: 0), location: 0.55)],
                                   center: .center, startRadiusFraction: 0, endRadiusFraction: 0.5)
                    .frame(width: w * 2.4, height: h * 1.2).position(x: w, y: 0)
                EllipticalGradient(stops: [.init(color: Color(hex: 0xEEF1E4), location: 0), .init(color: Color(hex: 0xEEF1E4, opacity: 0), location: 0.6)],
                                   center: .center, startRadiusFraction: 0, endRadiusFraction: 0.5)
                    .frame(width: w * 1.8, height: h).position(x: 0, y: h)
            }
        }
        .accessibilityHidden(true)
    }
}

extension View {
    @ViewBuilder
    fileprivate func journalBottomScrollEdge() -> some View {
        if #available(iOS 26.0, *) {
            scrollEdgeEffectHidden(true, for: .bottom).scrollEdgeEffectHidden(true, for: .top)
        } else {
            self
        }
    }

    /// 统一页面底色；系统导航栏隐藏，由页面内的圆形按钮导航。
    func journalPage() -> some View {
        journalBottomScrollEdge()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(JournalBackdrop().ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
    }
}

/// 隐藏系统导航栏后保留边缘右滑返回。
extension UINavigationController: @retroactive UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }
    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        viewControllers.count > 1
    }
}
