package com.oppo.smsclassifier

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RuleDefinitionTest {
    @Test
    fun parseRuleFile_loadsOtpProtectRule() {
        val json = AssetLoader.readText("rules/otp_rules.json")
        val file = RuleParser.parseRuleFile(json)
        assertEquals("1.0.0", file.version)
        assertTrue(file.rules.any { it.type == RuleType.OTP_PROTECT && it.id == "OTP_CN_001" })
    }

    @Test
    fun parseAndCompile_precompilesPatterns() {
        val json = AssetLoader.readText("rules/fraud_rules.json")
        val (_, compiled) = RuleParser.parseAndCompile(json)
        val fraudRule = compiled.first { it.definition.id == "FRAUD_CN_001" }
        assertTrue(fraudRule.compiledPattern.matcher("请转账到安全账户").find())
    }

    @Test
    fun assetLoader_readsClasspathResource() {
        val text = AssetLoader.readText("model/model_metadata.json")
        assertTrue(text.contains("\"modelVersion\""))
    }
}
