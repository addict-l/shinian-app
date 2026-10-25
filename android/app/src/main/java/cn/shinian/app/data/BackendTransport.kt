package cn.shinian.app.data

import okhttp3.OkHttpClient

/** Reuse established server connections across login and account-bound repositories.
 * Authorization remains on individual requests; repositories cancel only their own calls.
 */
internal object BackendTransport {
    val client = OkHttpClient()
}
