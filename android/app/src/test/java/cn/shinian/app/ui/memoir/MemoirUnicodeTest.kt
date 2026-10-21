package cn.shinian.app.ui.memoir

import org.junit.Assert.*
import org.junit.Test

class MemoirUnicodeTest {
    @Test fun chineseSharedGlyphsCopyAsTheirOrdinaryCharacters() {
        val value = "1 beginbfchar\n<2F4D> <2F26>\nendbfchar"
        val corrected = MemoirPdf.canonicalizeUnicodeMappings(value)
        assertTrue(corrected.contains("<2F4D> <5B50>"))
        assertFalse(corrected.contains("<2F26>"))
    }

    @Test fun rangeMappingsAreExpandedWithoutChangingSourceCharacterCodes() {
        val value = "1 beginbfrange\n<0001> <0002> <2F00>\nendbfrange"
        val corrected = MemoirPdf.canonicalizeUnicodeMappings(value)
        assertTrue(corrected.contains("<0001> <4E00>"))
        assertTrue(corrected.contains("<0002> <4E28>"))
    }
}
