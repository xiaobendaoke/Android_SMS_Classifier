package com.oppo.smsclassifier.ui.common

object NavRoutes {
    const val ONBOARDING = "onboarding"
    const val INBOX = "inbox"
    const val SUSPECT = "suspect"
    const val REVIEW = "review"
    const val DETAIL = "detail/{messageUri}"
    const val EVALUATION = "evaluation"
    const val PERFORMANCE = "performance"
    const val ABOUT = "about"

    fun detail(messageUri: String): String =
        "detail/${java.net.URLEncoder.encode(messageUri, Charsets.UTF_8.name())}"

    fun decodeMessageUri(encoded: String): String =
        java.net.URLDecoder.decode(encoded, Charsets.UTF_8.name())
}
