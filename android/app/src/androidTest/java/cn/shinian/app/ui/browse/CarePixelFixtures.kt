package cn.shinian.app.ui.browse

import android.content.Context
import android.os.SystemClock
import cn.shinian.app.data.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import java.io.File
import java.time.Instant
import java.util.Collections
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/** Exact text and images from current JournalDemoAPI.loadDesignMockup, entirely local. */
internal class CarePixelFixtures(private val appContext: Context, testContext: Context) {
    val session = AuthSession("https://care-reference.invalid", UUID.randomUUID().toString(), UUID.randomUUID().toString(),
        "care-pixel-reference", false, "local-fixture-token", "2099-01-01T00:00:00Z")
    val scope = session.scopeKey
    val preferenceName = "care-pixel-reference-$scope"
    private val basePeople = listOf(
        Person(personID(1), "陈建国", "爷爷", "1946-03-12"),
        Person(personID(2), "李秀英", "外婆", "1949-08-02"),
        Person(personID(3), "王丽华", "妈妈", "1972-11-20"),
        Person(personID(4), "陈志明", "爸爸", "1970-05-06"),
    )
    private val images = listOf("grandpa", "grandma", "mom", "dinner", "bike", "summer")
        .associateWith { testContext.assets.open("care-reference/$it.jpg").use { stream -> stream.readBytes() } }
    private val mediaImages = mutableMapOf<String, ByteArray>()
    val requests = Collections.synchronizedList(mutableListOf<String>())
    val unexpectedRequests = Collections.synchronizedList(mutableListOf<String>())
    val activeRequests = AtomicInteger(0)
    val lastRequestCompletedAt = AtomicLong(0)
    val memories: List<Memory> = buildList {
        var day = 0
        fun memory(person: String, title: String, whenText: String?, place: String? = null, photo: String? = null,
            date: String? = null, feeling: String? = null, content: String): Memory {
            day++
            val media = photo?.let {
                val id = UUID.fromString("00000000-0000-0000-0000-${(9000 + day).toString().padStart(12, '0')}").toString()
                mediaImages[id] = images.getValue(it)
                listOf(Media(id, "/api/v1/media/$id"))
            }.orEmpty()
            return Memory("00000000-0000-0000-0000-${(1000 + day).toString().padStart(12, '0')}", title, content,
                personIds = listOf(person), personName = basePeople.first { it.id == person }.name, primaryPersonId = person,
                memoryDate = date, createdAt = Instant.ofEpochSecond(1_790_000_000L - day * 86_400L).toString(),
                time = whenText?.let { InformationDimension(if (date == null) "approximate" else "known", it) } ?: InformationDimension(),
                place = place?.let { InformationDimension("known", it) } ?: InformationDimension(),
                feeling = feeling?.let { InformationDimension("known", it) } ?: InformationDimension(), media = media)
        }
        val grandpa = personID(1); val grandma = personID(2); val mom = personID(3); val dad = personID(4)
        add(memory(grandma, "葡萄架下的那把蒲扇", "2008年夏天", "老家院子", "summer", feeling = "想念",
            content = "那年夏天特别热，院子里的葡萄架投下一片斑驳的阴凉。外婆坐在门槛上，一手摇着那把旧蒲扇，一手轻轻拍着我的背。西瓜在井水里冰了一下午，她总把最中间那一块留给我……"))
        add(memory(dad, "爸爸扶着我学骑车", "1998年秋天", "厂区大道", "bike", content = "“别回头，往前看。”那条落满银杏叶的路，爸爸扶着后座跑了一路……"))
        add(memory(grandpa, "除夕夜里的那枚硬币", "2003年除夕", "老家厨房", "dinner", "2003-01-31", "温暖",
            "每年除夕，爷爷都会早早系上那条洗得发白的围裙，在厨房里擀皮、调馅。他总会趁我们不注意，把一枚擦得锃亮的硬币悄悄包进饺子里。那一年，硬币落在了我的碗里，爷爷笑着说：“来年，咱家的小福星就是你。”"))
        add(memory(grandpa, "窗台上的那盆茉莉", "1995年春天", photo = "grandpa", content = "爷爷每天清晨都给窗台上的茉莉浇水，花开的时候，满屋子都是香气。"))
        add(memory(grandpa, "银杏路上的二八自行车", "1988年秋天", "厂区大道", "bike", content = "爷爷骑着那辆二八自行车，载着我穿过落满银杏叶的厂区大道。"))
        add(memory(grandpa, "那年的团圆饭", "2008年除夕", photo = "dinner", content = "一大家子围坐在圆桌旁，爷爷举起酒杯，说今年最高兴的是人都到齐了。"))
        add(memory(grandma, "外婆的老花镜", "2001年冬天", photo = "grandma", content = "外婆戴着老花镜给我缝棉袄，针脚细细密密。"))
        add(memory(mom, "妈妈的五十岁生日", "2015年", photo = "mom", content = "那天妈妈穿上了新买的毛衣，笑得像个小姑娘。"))
        add(memory(mom, "妈妈送我去上学", "1998年秋天", photo = "bike", content = "妈妈推着自行车送我到校门口，一直看着我走进教室。"))
        add(memory(mom, "妈妈的拿手红烧肉", "1992年", photo = "dinner", content = "每到周末，妈妈都会做一锅红烧肉，整栋楼都闻得到香味。"))
        add(memory(grandpa, "爷爷的收音机", "1982年", "老屋", content = "爷爷的收音机总是调到戏曲频道，他跟着哼，我在旁边打瞌睡。"))
        add(memory(grandma, "外婆的桂花糕", "1996年秋天", "老家院子", content = "桂花开的时候，外婆会把花收起来，做成一笼甜甜的桂花糕。"))
        add(memory(grandpa, "老屋门前的石榴树", "1979年秋天", "老屋门前", content = "石榴熟了，爷爷踩着板凳摘下最大的一个，掰开分给我们。"))
        add(memory(grandma, "井边的西瓜", "1993年夏天", "老家院子", content = "外婆把西瓜放进井水里，等我们放学回家正好冰凉。"))
        add(memory(grandpa, "爷爷写给奶奶的信", "1970年", "工厂宿舍", content = "那些信被奶奶收在铁盒子里，字迹工整，每一封都写着“一切都好”。"))
        add(memory(grandma, "外婆教我包粽子", "1990年", "老家厨房", content = "外婆的手很巧，三两下就包好一个，我的总是漏米。"))
        add(memory(grandpa, "第一次进城", "1965年春天", "县城", content = "爷爷说，他第一次进城，是挑着两担米走了一整天。"))
        add(memory(mom, "妈妈的第一份工作", null, content = "妈妈说，第一个月的工资，她全都寄回了家。"))
    }
    val people = basePeople.map { person -> person.copy(memoryCount = memories.count { person.id in it.personIds }) }
    val grandpa get() = people.first()
    val repository = BackendRepository(session, OkHttpClient.Builder().addInterceptor { chain ->
        activeRequests.incrementAndGet()
        try {
            val request = chain.request()
            requests += "${request.method} ${request.url.encodedPath}"
            val photo = request.url.encodedPath.removePrefix("/api/v1/media/")
            val bytes = if (request.method == "GET" && request.url.host == "care-reference.invalid" && request.url.encodedPath.startsWith("/api/v1/media/")) mediaImages[photo] else null
            if (bytes == null) unexpectedRequests += "${request.method} ${request.url.encodedPath}"
            // Every request terminates inside this interceptor; chain.proceed is never called.
            Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(if (bytes == null) 500 else 200)
                .message("Local care reference fixture").body((bytes ?: ByteArray(0)).toResponseBody("image/jpeg".toMediaType())).build()
        } finally {
            lastRequestCompletedAt.set(SystemClock.uptimeMillis())
            activeRequests.decrementAndGet()
        }
    }.build())

    fun stagePortraits() {
        listOf("grandpa", "grandma", "mom").forEachIndexed { index, image ->
            portraitFile(appContext.filesDir, scope, people[index].id).also { it.parentFile!!.mkdirs(); it.writeBytes(images.getValue(image)) }
        }
        appContext.getSharedPreferences(preferenceName, Context.MODE_PRIVATE).edit().putFloat("care.readingScale", 1f).commit()
    }

    fun cleanup() {
        repository.invalidate()
        File(appContext.filesDir, "Accounts/$scope").deleteRecursively()
        File(File(appContext.noBackupFilesDir, "PendingStories"), scope).deleteRecursively()
        appContext.deleteSharedPreferences(preferenceName)
    }

    companion object { private fun personID(index: Int) = "00000000-0000-0000-0000-${index.toString().padStart(12, '0')}" }
}
