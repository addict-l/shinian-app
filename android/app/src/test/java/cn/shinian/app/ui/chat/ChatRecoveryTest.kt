package cn.shinian.app.ui.chat

import cn.shinian.app.data.ChatSnapshot
import cn.shinian.app.data.InformationDimension
import cn.shinian.app.data.Media
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Test

class ChatRecoveryTest {
    private val edits = DraftEdits("draft", "😀 2008年的夏天", "2008年，我们离开故乡。2008年，开始新的生活。",
        InformationDimension("known", "2010年", listOf("source"), true), InformationDimension("approximate", "2008年"))

    private fun suggestion(id: String, field: String, start: Int, before: String, after: String) = buildJsonObject {
        put("id", id); put("field", field); put("start", start); put("length", before.length)
        put("before", before); put("after", after)
    }
    private fun preview(vararg suggestions: JsonObject) = buildJsonObject { put("suggestions", JsonArray(suggestions.toList())) }

    @Test fun `selected UTF16 suggestions change only captured ranges`() {
        val value = applyDraftTime(edits, preview(suggestion("title", "title", 3, "2008年", "2010年"),
            suggestion("first", "summary", 0, "2008年", "2010年"),
            suggestion("second", "summary", edits.content.lastIndexOf("2008年"), "2008年", "2010年")), setOf("title", "second"))
        assertEquals("😀 2010年的夏天", value.title)
        assertEquals("2008年，我们离开故乡。2010年，开始新的生活。", value.content)
        assertEquals(edits.time, value.anchor)
        assertEquals(edits.time.sourceMessageIds, value.time.sourceMessageIds)
    }

    @Test fun `overlapping ranges are rejected before returning edited content`() {
        assertThrows(IllegalArgumentException::class.java) {
            applyDraftTime(edits.copy(title = "2008年"), preview(suggestion("a", "title", 0, "2008", "2010"),
                suggestion("b", "title", 2, "08年", "10年")), setOf("a", "b"))
        }
    }

    @Test fun `stale text and split surrogate ranges are rejected`() {
        assertThrows(IllegalArgumentException::class.java) {
            applyDraftTime(edits, preview(suggestion("a", "title", 3, "2009年", "2010年")), setOf("a"))
        }
        assertThrows(IllegalArgumentException::class.java) {
            applyDraftTime(edits, preview(suggestion("a", "title", 0, "\uD83D", "旧")), setOf("a"))
        }
    }

    @Test fun `draft manifest roundtrip retains upload order and idempotency identities`() {
        val media = Media("uploaded-photo", "/api/v1/media/uploaded-photo")
        val value = LocalChatDraft("person", "session", "stable-start", "unsent input",
            PendingNarration("stable-message", "待回复的讲述", listOf(media.id)),
            listOf(StoredPhoto("stable-photo-1", media), StoredPhoto("stable-photo-2")),
            ChatSnapshot("session"), "骨架回答", LifeCommand("answer", 7, "stable-life", "原始回答"))
        val json = Json { encodeDefaults = true }
        val encoded = json.encodeToString(value)
        val restored = json.decodeFromString<LocalChatDraft>(encoded)
        assertEquals(value, restored)
        assertEquals(listOf("stable-photo-1", "stable-photo-2"), restored.photos.map { it.id })
        assertEquals("stable-message", restored.pending?.id)
        assertEquals("stable-life", restored.pendingLife?.requestId)
        assertEquals("", restored.copy(input = "  待回复的讲述\n").restoredInput)
        assertEquals("unsent input", restored.restoredInput)
        assertFalse(encoded.contains("token"))
    }

    @Test fun `memory deletion drops downloaded state while retaining recoverable narration and photo IDs`() {
        val photo = StoredPhoto("stable-photo", Media("uploaded", "/api/v1/media/uploaded"))
        val original = LocalChatDraft("person", "deleted-session", "start", "还没发送的文字",
            PendingNarration("stable-message", "正在重试的讲述", listOf("uploaded")), listOf(photo), ChatSnapshot("deleted-session"),
            "还没提交的骨架回答", LifeCommand("answer", 3, "stable-life", "骨架讲述"), edits = edits)
        val result = original.withoutDownloadedHistory("deleted-session")
        assertEquals(null, result.snapshot)
        assertEquals(null, result.sessionId)
        assertEquals(original.input, result.input)
        assertEquals(original.pending?.id, result.pending?.id)
        assertEquals(original.pending?.text, result.pending?.text)
        assertEquals(original.pendingLife, result.pendingLife)
        assertEquals(original.lifeInput, result.lifeInput)
        assertEquals(original.photos.map { it.id }, result.photos.map { it.id })
        assertEquals(null, result.photos.single().attachment)
        assertEquals(original.edits, result.edits)
        val editInvalidation = original.withoutDownloadedHistory(null)
        assertEquals(original.sessionId, editInvalidation.sessionId)
        assertEquals(original.pending, editInvalidation.pending)
        assertEquals(original.photos, editInvalidation.photos)
    }
}
