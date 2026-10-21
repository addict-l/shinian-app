package cn.shinian.app.ui

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import cn.shinian.app.data.*
import cn.shinian.app.ui.browse.*
import cn.shinian.app.ui.theme.ShinianTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BrowseInteractionTest {
    @get:Rule val compose = createComposeRule()
    private val grandpa=Person("11111111-1111-1111-1111-111111111111","李明","爷爷","1948-03-01")
    private val mother=Person("22222222-2222-2222-2222-222222222222","陈芳","妈妈","1976-06-18")

    @Test fun personSearchAndDeleteRequireOneExplicitConfirmation() {
        var deleted:Person?=null
        compose.setContent { ShinianTheme { PersonSelectionScreen(listOf(grandpa,mother),onDelete={deleted=it}) } }
        compose.onNodeWithTag("browse.search").performTextInput("李明")
        compose.onNodeWithTag("member.${mother.id}").assertDoesNotExist()
        compose.onNodeWithTag("member.${grandpa.id}").performTouchInput{swipeLeft()}
        compose.onNodeWithContentDescription("删除李明").performClick()
        compose.onNodeWithText("删除「李明」？").assertIsDisplayed()
        compose.runOnIdle { assertNull(deleted) }
        compose.onNodeWithText("取消").performClick()
        compose.runOnIdle { assertNull(deleted) }
        compose.onNodeWithTag("member.${grandpa.id}").performTouchInput{swipeLeft()}
        compose.onNodeWithContentDescription("删除李明").performClick()
        compose.onNode(hasText("删除") and hasAnyAncestor(isDialog())).performClick()
        compose.runOnIdle { assertEquals(grandpa,deleted) }
    }

    @Test fun personCannotBeSubmittedUntilBirthdayIsChosen() {
        var added:Triple<String,String,String>?=null
        compose.setContent { ShinianTheme { AddPersonScreen(onAdd={name,role,birth->added=Triple(name,role,birth)}) } }
        compose.onNodeWithTag("member.add").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("member.role.爷爷").performScrollTo().performClick()
        compose.onNodeWithTag("member.realName").performScrollTo().performTextInput("李明")
        compose.onNodeWithTag("member.add").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("member.birthday").performScrollTo().performClick()
        compose.onNodeWithTag("member.confirmBirthday").performClick()
        compose.onNodeWithTag("member.add").performScrollTo().assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(Triple("李明","爷爷","1950-01-01"),added) }
    }

    @Test fun memoriesCanBeFilteredByParticipatingPersonAndSearched() {
        val first=Memory("m1","第一次工作","爷爷在乡下的第一份工作",personIds=listOf(grandpa.id),personName=grandpa.name,time=InformationDimension("known","1968年"))
        val second=Memory("m2","一顿家常饭","妈妈记得的一顿饭",personIds=listOf(mother.id),personName=mother.name)
        compose.setContent { ShinianTheme { MemoriesScreen(listOf(grandpa,mother),listOf(first,second)) } }
        compose.onNodeWithText("妈妈",substring=false).performClick()
        compose.onNodeWithTag("memory.card.m1").assertDoesNotExist()
        compose.onNodeWithTag("memory.card.m2").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("全部",substring=false).performScrollTo().performClick()
        compose.onNodeWithTag("memories.search").performScrollTo().performTextInput("第一次")
        compose.onNodeWithTag("memory.card.m2").assertDoesNotExist()
        compose.onNodeWithTag("memory.card.m1").performScrollTo().assertIsDisplayed()
    }

    @Test fun careModeUsesSimpleMenuAndConfirmsSwitchingBack() {
        var mode:Boolean?=null
        compose.setContent { ShinianTheme { ProfileScreen(emptyList(),emptyList(),care=true,onCareChange={mode=it}) } }
        compose.onNodeWithText("更多",substring=false).assertIsDisplayed()
        compose.onNodeWithText("家人管理").assertIsDisplayed()
        compose.onNodeWithText("我的全部回忆").assertDoesNotExist()
        compose.onNodeWithTag("care.switchStandard").performScrollTo().performClick()
        compose.runOnIdle{assertNull(mode)}
        compose.onNode(hasText("切换普通模式") and hasAnyAncestor(isDialog())).performClick()
        compose.runOnIdle{assertEquals(false,mode)}
    }

    @Test fun careHomeOmitsRecentMemoryPhotoAndKeepsOpenActionReachable() {
        val memory=Memory("recent-photo","和家人一起过年","一家人在小屋里包饺子。",personIds=listOf(grandpa.id),personName=grandpa.name,
            media=listOf(Media("family-photo","/api/v1/media/family-photo")))
        var opened:Memory?=null
        compose.setContent { ShinianTheme { HomeScreen(listOf(grandpa),listOf(memory),care=true,onMemory={opened=it}) } }
        compose.onNodeWithTag("memory.card.photo.${memory.id}").assertDoesNotExist()
        compose.onNodeWithText("打开看看",substring=true).performScrollTo().assertIsDisplayed().performClick()
        compose.runOnIdle{assertEquals(memory,opened)}
    }
}
