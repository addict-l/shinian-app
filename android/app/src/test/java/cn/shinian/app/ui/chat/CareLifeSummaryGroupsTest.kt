package cn.shinian.app.ui.chat

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class CareLifeSummaryGroupsTest {
    private fun field(id: String, status: String = "known", vararg quotes: String) = buildJsonObject {
        put("topic_id", id); put("title", "字段$id"); put("status", status)
        put("evidence", buildJsonArray { quotes.forEach { add(buildJsonObject { put("quote", it) }) } })
    }

    @Test fun allElevenSkeletonQuestionsRetainTheirOriginalWords() {
        val ids = listOf("SK01", "SK01b", "SK01c", "SK02", "SK03", "SK03b", "SK03c", "SK03d", "SK04", "SK05", "SK06")
        val groups = careLifeSummaryGroups(ids.map { field(it, "known", "$it 的原话") })
        assertEquals(listOf("出生与家乡", "小时候的家", "性格与一生"), groups.map { it.title })
        assertEquals(ids.map { "$it 的原话" }, groups.flatMap { it.lines }.map { it.text })
    }

    @Test fun oldCatalogAndMultipleEvidenceQuotesRemainComplete() {
        val groups = careLifeSummaryGroups(listOf(field("home", "known", "在家乡长大。", "住在河边。"), field("learning", "known", "后来去上学。"), field("present", "known", "如今和家人生活。")))
        assertEquals(listOf("小时候", "读书工作", "家人近况"), groups.map { it.title })
        assertEquals("在家乡长大。\n住在河边。", groups.first().lines.single().text)
        assertFalse(groups.first().lines.single().subdued)
    }

    @Test fun pendingAnswersAreNotInventedAndOtherStatusesStayDistinct() {
        val groups = careLifeSummaryGroups(listOf(field("SK01", "pending"), field("SK01b", "unknown"), field("SK03", "declined"), field("SK06", "skipped")))
        assertEquals(3, groups.flatMap { it.lines }.size)
        assertTrue(groups[0].lines.single().text.endsWith("记不清"))
        assertTrue(groups[1].lines.single().text.endsWith("暂时不想讲"))
        assertTrue(groups[2].lines.single().text.endsWith("暂时跳过"))
        assertTrue(groups.flatMap { it.lines }.all { it.subdued })
    }

    @Test fun futureFieldsAreVisibleWithoutChangingTheCatalog() {
        val groups = careLifeSummaryGroups(listOf(field("SK01", "known", "一九四零年出生。"), field("FUTURE01", "known", "这段未来字段里的原话也要保留。")))
        assertEquals("其他", groups.last().title)
        assertEquals("这段未来字段里的原话也要保留。", groups.last().lines.single().text)
    }
}
