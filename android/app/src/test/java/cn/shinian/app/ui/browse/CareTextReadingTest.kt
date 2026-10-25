package cn.shinian.app.ui.browse

import org.junit.Assert.*
import org.junit.Test

class CareTextReadingTest {
    @Test fun longReadingKeepsEveryCharacterWithoutSplittingSurrogates() {
        val text = "一家人的回忆".repeat(900) + "留住这一刻\uD83C\uDF3F".repeat(900)
        val chunks = careSpeechChunks(text, 4000)
        assertEquals(text, chunks.joinToString(""))
        assertTrue(chunks.all { it.length <= 4000 && !it.last().isHighSurrogate() && !it.first().isLowSurrogate() })
    }
    @Test fun surrogateAtTheBoundaryMovesToTheNextChunk() {
        val chunks = careSpeechChunks("abc\uD83C\uDF3Fde", 4)
        assertEquals(listOf("abc", "\uD83C\uDF3Fde"), chunks)
    }
}
