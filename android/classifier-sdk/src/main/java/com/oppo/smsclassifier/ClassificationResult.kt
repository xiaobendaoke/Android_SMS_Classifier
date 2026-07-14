package com.oppo.smsclassifier

/**
 * Input to the offline SMS classifier.
 */
data class SmsInput(
    val sender: String?,
    val body: String,
    val timestampMillis: Long,
    val subscriptionId: Int? = null,
    val localeHint: String? = null,
)

enum class SmsCategory {
    TRANSACTION,
    AD,
    HARASS,
    FRAUD,
}

enum class SmsAction {
    INBOX,
    SUSPECT,
    REVIEW,
}

/**
 * Classification output with separate category and action.
 */
data class ClassificationResult(
    val category: SmsCategory,
    val action: SmsAction,
    val probabilities: FloatArray,
    val confidence: Float,
    val rawModelCategory: SmsCategory,
    val ruleIds: List<String>,
    val reasonCode: String,
    val languageHint: String?,
    val elapsedMs: Double,
    val modelVersion: String,
    val rulesVersion: String,
    val normalizationVersion: String,
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as ClassificationResult
        return category == other.category &&
            action == other.action &&
            probabilities.contentEquals(other.probabilities) &&
            confidence == other.confidence &&
            rawModelCategory == other.rawModelCategory &&
            ruleIds == other.ruleIds &&
            reasonCode == other.reasonCode &&
            languageHint == other.languageHint &&
            elapsedMs == other.elapsedMs &&
            modelVersion == other.modelVersion &&
            rulesVersion == other.rulesVersion &&
            normalizationVersion == other.normalizationVersion
    }

    override fun hashCode(): Int {
        var result = category.hashCode()
        result = 31 * result + action.hashCode()
        result = 31 * result + probabilities.contentHashCode()
        result = 31 * result + confidence.hashCode()
        result = 31 * result + rawModelCategory.hashCode()
        result = 31 * result + ruleIds.hashCode()
        result = 31 * result + reasonCode.hashCode()
        result = 31 * result + (languageHint?.hashCode() ?: 0)
        result = 31 * result + elapsedMs.hashCode()
        result = 31 * result + modelVersion.hashCode()
        result = 31 * result + rulesVersion.hashCode()
        result = 31 * result + normalizationVersion.hashCode()
        return result
    }
}
