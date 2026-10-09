import XCTest

final class FullStackFlowTests: XCTestCase {
    @MainActor func testGrandpaMemoryPersistsAfterRelaunch() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        let name = "联调爷爷" + String(Int(Date().timeIntervalSince1970))
        app.tabBars.buttons["新的回忆"].tap()
        let nameField = app.textFields["member.realName"]
        XCTAssertTrue(nameField.waitForExistence(timeout: 15))
        nameField.tap(); nameField.typeText(name)
        let relationship = app.textFields["member.relationship"]
        relationship.tap(); relationship.typeText("爷爷")
        app.buttons["member.birthday"].tap()
        let wheels = app.pickerWheels
        XCTAssertTrue(wheels.firstMatch.waitForExistence(timeout: 5))
        // Store an actual grandfather birthday, independent of the test run date.
        wheels.element(boundBy: 0).adjust(toPickerWheelValue: "1940年")
        wheels.element(boundBy: 1).adjust(toPickerWheelValue: "5月")
        wheels.element(boundBy: 2).adjust(toPickerWheelValue: "12日")
        let confirmBirthday = app.buttons["member.confirmBirthday"]
        reveal(confirmBirthday, in: app); confirmBirthday.tap()
        let addMember = app.buttons["member.add"]
        reveal(addMember, in: app); addMember.tap()
        let person = app.buttons["members.card.\(name)"]
        XCTAssertTrue(person.waitForExistence(timeout: 15))
        attach(app, "01-member-from-database")
        person.tap()
        let input = app.textFields["chat.input"]
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        XCTAssertTrue(waitEnabled(input, seconds: 100))
        input.tap()
        input.typeText("2010年5月1日，爷爷在家门口的小广场教我骑自行车。他一直扶着车后座，告诉我看前方不要怕。那天我终于学会了骑车，爷爷特别开心。")
        app.buttons["chat.send"].tap()
        let generate = app.buttons["chat.generate"]
        XCTAssertTrue(generate.waitForExistence(timeout: 100))
        XCTAssertTrue(waitEnabled(generate, seconds: 100))
        reveal(generate, in: app)
        attach(app, "02-real-ai-conversation")
        generate.tap()
        let save = app.buttons["memory.save"]
        XCTAssertTrue(save.waitForExistence(timeout: 100))
        reveal(save, in: app)
        attach(app, "03-server-draft-preview")
        save.tap()
        XCTAssertTrue(app.staticTexts["共 1 段回忆"].waitForExistence(timeout: 20) || app.staticTexts["1个回忆"].exists || app.staticTexts["珍藏了 1 个美好回忆"].exists)
        attach(app, "04-saved-timeline")
        app.terminate(); app.launch()
        app.tabBars.buttons["新的回忆"].tap()
        let select = app.buttons["newMemory.step.1"]
        XCTAssertTrue(waitEnabled(select, seconds: 20)); select.tap()
        XCTAssertTrue(app.buttons["members.card.\(name)"].waitForExistence(timeout: 15))
        app.tabBars.buttons["家族树"].tap()
        let all = app.buttons["family.allMemories"]
        XCTAssertTrue(all.waitForExistence(timeout: 10)); all.tap()
        XCTAssertTrue(app.staticTexts[name].waitForExistence(timeout: 20))
        attach(app, "05-memory-reloaded-from-server")
    }
    @MainActor private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }
    @MainActor private func waitEnabled(_ element: XCUIElement, seconds: TimeInterval) -> Bool {
        XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND enabled == true"), object: element)], timeout: seconds) == .completed
    }
    @MainActor private func attach(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
