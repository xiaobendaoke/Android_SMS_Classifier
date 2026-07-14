package com.oppo.smsclassifier

import org.json.JSONArray
import org.json.JSONObject
import java.util.regex.Pattern

enum class RuleType {
    OTP_PROTECT,
    PICKUP_PROTECT,
    TRANSACTION_HINT,
    FRAUD_RISK,
    AD_HINT,
    HARASS_HINT,
}

data class RuleDefinition(
    val id: String,
    val language: String,
    val type: RuleType,
    val priority: Int,
    val pattern: String,
    val categoryHint: SmsCategory?,
    val action: SmsAction?,
    val reasonCode: String,
    val enabled: Boolean,
)

data class RuleFile(
    val version: String,
    val rules: List<RuleDefinition>,
)

data class CompiledRule(
    val definition: RuleDefinition,
    val compiledPattern: Pattern,
)

object RuleParser {
    fun parseRuleFile(json: String): RuleFile {
        val root = JSONObject(json)
        val version = root.optString("version", "1.0.0")
        val rulesArray = root.optJSONArray("rules") ?: JSONArray()
        val rules = buildList {
            for (i in 0 until rulesArray.length()) {
                add(parseRule(rulesArray.getJSONObject(i)))
            }
        }
        return RuleFile(version = version, rules = rules)
    }

    fun parseAndCompile(json: String): Pair<String, List<CompiledRule>> {
        val file = parseRuleFile(json)
        val compiled = file.rules
            .filter { it.enabled }
            .map { rule ->
                CompiledRule(
                    definition = rule,
                    compiledPattern = Pattern.compile(rule.pattern, Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE),
                )
            }
        return file.version to compiled
    }

    private fun parseRule(obj: JSONObject): RuleDefinition {
        val type = RuleType.valueOf(obj.getString("type"))
        val categoryHint = obj.optString("categoryHint", "").takeIf { it.isNotEmpty() }?.let {
            SmsCategory.valueOf(it)
        }
        val action = obj.optString("action", "").takeIf { it.isNotEmpty() }?.let {
            SmsAction.valueOf(it)
        }
        return RuleDefinition(
            id = obj.getString("id"),
            language = obj.optString("language", "unknown"),
            type = type,
            priority = obj.optInt("priority", 0),
            pattern = obj.getString("pattern"),
            categoryHint = categoryHint,
            action = action,
            reasonCode = obj.optString("reasonCode", "RULE_MATCH"),
            enabled = obj.optBoolean("enabled", true),
        )
    }
}
