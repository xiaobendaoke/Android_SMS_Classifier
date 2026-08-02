package com.oppo.smsclassifier

/**
 * Signals collected from precompiled JSON rules.
 */
data class RuleSignals(
    val matchedRuleIds: List<String> = emptyList(),
    val hasOtpProtect: Boolean = false,
    val hasHighFraudRisk: Boolean = false,
    val hasPickupProtect: Boolean = false,
    val hasTransactionProtect: Boolean = false,
    val categoryHint: SmsCategory? = null,
    val reasonCode: String = "NO_RULE_MATCH",
)

class RuleEngine(
    rules: List<CompiledRule>,
    val rulesVersion: String = "1.0.0",
) {
    private val compiledRules: List<CompiledRule> = rules.sortedByDescending { it.definition.priority }

    fun collectSignals(normalizedBody: String, sender: String?): RuleSignals {
        val text = normalizedBody
        val matched = compiledRules.filter { rule ->
            rule.compiledPattern.matcher(text).find()
        }
        val matchedIds = matched.map { it.definition.id }

        val hasOtpProtect = matched.any { it.definition.type == RuleType.OTP_PROTECT }
        val hasHighFraudRisk = matched.any { it.definition.type == RuleType.FRAUD_RISK }
        val hasPickupProtect = matched.any { it.definition.type == RuleType.PICKUP_PROTECT }
        val hasTransactionProtect = matched.any {
            it.definition.type == RuleType.TRANSACTION_PROTECT
        }

        val categoryWinner = matched
            .filter { it.definition.type.isCategoryHintType() }
            .maxByOrNull { it.definition.priority }

        val categoryHint = categoryWinner?.definition?.categoryHint
        val reasonCode = when {
            hasOtpProtect && hasHighFraudRisk -> "OTP_FRAUD_CONFLICT"
            hasTransactionProtect && hasHighFraudRisk -> "TRANSACTION_FRAUD_CONFLICT"
            categoryWinner != null -> categoryWinner.definition.reasonCode
            hasOtpProtect -> "OTP_PROTECT"
            hasPickupProtect -> "PICKUP_PROTECT"
            hasTransactionProtect -> "TRANSACTION_PROTECT"
            hasHighFraudRisk -> "HIGH_FRAUD_RISK"
            else -> "NO_RULE_MATCH"
        }

        return RuleSignals(
            matchedRuleIds = matchedIds,
            hasOtpProtect = hasOtpProtect,
            hasHighFraudRisk = hasHighFraudRisk,
            hasPickupProtect = hasPickupProtect,
            hasTransactionProtect = hasTransactionProtect,
            categoryHint = categoryHint,
            reasonCode = reasonCode,
        )
    }

    companion object {
        val RULE_ASSET_PATHS = listOf(
            "rules/otp_rules.json",
            "rules/transaction_rules.json",
            "rules/fraud_rules.json",
            "rules/ad_rules.json",
            "rules/harass_rules.json",
        )

        fun fromAssetJsons(
            ruleJsons: List<String>,
            rulesVersion: String = "1.0.0",
        ): RuleEngine {
            val allRules = ruleJsons.flatMap { json ->
                RuleParser.parseAndCompile(json).second
            }
            return RuleEngine(rules = allRules, rulesVersion = rulesVersion)
        }

        fun fromReader(readAsset: (String) -> String): RuleEngine {
            val versions = mutableListOf<String>()
            val allRules = RULE_ASSET_PATHS.flatMap { path ->
                val (version, rules) = RuleParser.parseAndCompile(readAsset(path))
                versions.add(version)
                rules
            }
            val rulesVersion = versions.maxOrNull() ?: "1.0.0"
            return RuleEngine(rules = allRules, rulesVersion = rulesVersion)
        }
    }
}

private fun RuleType.isCategoryHintType(): Boolean = when (this) {
    RuleType.OTP_PROTECT,
    RuleType.PICKUP_PROTECT,
    RuleType.TRANSACTION_PROTECT,
    RuleType.TRANSACTION_HINT,
    RuleType.FRAUD_RISK,
    RuleType.AD_HINT,
    RuleType.HARASS_HINT,
    -> true
}
