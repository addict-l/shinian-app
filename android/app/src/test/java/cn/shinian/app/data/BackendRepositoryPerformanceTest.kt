package cn.shinian.app.data

import cn.shinian.app.FamilyDataController
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.assertEquals
import org.junit.Test

class BackendRepositoryPerformanceTest {
    @Test fun concurrentHomeLoadsFetchIdentityPeopleAndMemoriesOnlyOnce() = runBlocking {
        val paths = java.util.Collections.synchronizedList(mutableListOf<String>())
        val server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.requestUrl!!.encodedPath
                paths += path
                return MockResponse().setBodyDelay(80, TimeUnit.MILLISECONDS).setBody(when (path) {
                    "/api/v1/auth/me" -> """{"account_id":"$ACCOUNT","family_id":"$FAMILY","username":"test_family"}"""
                    "/api/v1/family-members/" -> """[{"id":"$PERSON","name":"外婆","relationship":"外婆","birth_date":"1948-06-01"}]"""
                    "/api/v1/memories/" -> """[{"id":"$MEMORY","person_ids":["$PERSON"],"title":"旧时光","raw_content":"故事","summary":"故事","version":1}]"""
                    else -> error("Unexpected request $path")
                })
            }
        }
        server.start()
        val repository = BackendRepository(AuthSession(server.url("/").toString().trimEnd('/'), ACCOUNT, FAMILY,
            "test_family", false, "test-token", "2030-01-01T00:00:00Z"))
        try {
            val controller = FamilyDataController(this)
            controller.bind(repository)
            controller.refresh()!!.join()
            assertEquals(1, controller.state.value.people.single().memoryCount)
            assertEquals("外婆", controller.state.value.memories.single().personName)
            assertEquals("Concurrent home loading should share identity verification", 1, paths.count { it == "/api/v1/auth/me" })
            assertEquals("Concurrent home loading should share the people response", 1, paths.count { it == "/api/v1/family-members/" })
            assertEquals("Counts and home cards should share the memories response", 1, paths.count { it == "/api/v1/memories/" })
        } finally {
            repository.invalidate()
            server.shutdown()
        }
    }

    private companion object {
        const val ACCOUNT = "ea28ff04-a728-4efa-8c2c-9dbdc111cace"
        const val FAMILY = "b19a6d11-f176-4189-a532-d5ff36495451"
        const val PERSON = "fc15d63d-6a8c-4572-8743-d08cf1f6c5c1"
        const val MEMORY = "50847b40-175f-4a9e-89aa-576c72f3a1dd"
    }
}
