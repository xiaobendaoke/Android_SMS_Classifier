package com.oppo.smsclassifier

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ByteEncoderTest {
    @Test
    fun encode_producesFixedLength() {
        val encoder = ByteEncoder()
        val ids = encoder.encode("hello")
        assertEquals(512, ids.size)
    }

    @Test
    fun encode_mapsAsciiWithOffset() {
        val encoder = ByteEncoder()
        val ids = encoder.encode("A")
        assertEquals('A'.code + ByteEncoder.BYTE_OFFSET, ids[0])
        assertEquals(ByteEncoder.PAD_ID, ids[1])
    }

    @Test
    fun encode_abc_matchesPythonParity() {
        val encoder = ByteEncoder()
        val ids = encoder.encode("abc")
        assertEquals(97 + ByteEncoder.BYTE_OFFSET, ids[0])
        assertEquals(98 + ByteEncoder.BYTE_OFFSET, ids[1])
        assertEquals(99 + ByteEncoder.BYTE_OFFSET, ids[2])
        assertEquals(ByteEncoder.PAD_ID, ids[3])
    }
}

class TextNormalizerTest {
    @Test
    fun normalize_nfkc_fullwidth() {
        val normalizer = TextNormalizer()
        assertEquals("123", normalizer.normalize("１２３"))
    }

    @Test
    fun normalize_collapsesWhitespace() {
        val normalizer = TextNormalizer()
        assertEquals("a b", normalizer.normalize("a   b"))
    }

    @Test
    fun normalize_hindiDevanagari_preservesCombiningMarks() {
        val normalizer = TextNormalizer()
        val input = "आपका OTP 123456 है"
        val normalized = normalizer.normalize(input)
        assertFalse(normalized.isEmpty())
        assertTrue(normalized.contains("आपका"))
        assertTrue(normalized.contains("OTP"))
        assertTrue(normalized.contains("123456"))
    }

    @Test
    fun normalize_appliesConfusablesFromJson() {
        val json = AssetLoader.readText("normalize/confusables.json")
        val normalizer = TextNormalizer(confusableReplacements = TextNormalizer.loadConfusablesFromJson(json))
        assertEquals("微信", normalizer.normalize("薇信"))
    }
}

class ModelMetadataTest {
    @Test
    fun loadFromJson_hasFourLabelsAndThresholds() {
        val json = AssetLoader.readText("model/model_metadata.json")
        val metadata = ModelMetadata.loadFromJson(json)
        assertEquals(4, metadata.labels.size)
        assertTrue(metadata.labels.contains("TRANSACTION"))
        assertEquals(0.55f, metadata.thresholdFor(SmsCategory.TRANSACTION), 0.001f)
        assertEquals(0.75f, metadata.thresholdFor(SmsCategory.FRAUD), 0.001f)
    }
}

class RuleEngineTest {
    @Test
    fun collectSignals_otpChinese_matchesOtpRule() {
        val engine = RuleEngine.fromReader(AssetLoader::readText)
        val signals = engine.collectSignals("您的验证码为123456", null)
        assertTrue(signals.hasOtpProtect)
        assertTrue(signals.matchedRuleIds.contains("OTP_CN_001"))
        assertEquals(SmsCategory.TRANSACTION, signals.categoryHint)
    }

    @Test
    fun collectSignals_transferAlone_doesNotTriggerOtp() {
        val engine = RuleEngine.fromReader(AssetLoader::readText)
        val signals = engine.collectSignals("请尽快转账到指定账户", null)
        assertFalse(signals.hasOtpProtect)
    }
}

class DecisionRouterTest {
    private val metadata = ModelMetadata.loadFromJson(AssetLoader.readText("model/model_metadata.json"))
    private val router = DecisionRouter(metadata)

    @Test
    fun route_otpFraudConflict_reviewAction() {
        val engine = RuleEngine.fromReader(AssetLoader::readText)
        val body = "您的验证码为123456，请转账到安全账户"
        val signals = engine.collectSignals(body, null)
        val result = router.route(
            input = SmsInput(sender = null, body = body, timestampMillis = 0L),
            normalized = body,
            signals = signals,
            modelProbs = null,
            modelAvailable = false,
        )
        assertEquals(SmsAction.REVIEW, result.action)
        assertEquals(SmsCategory.FRAUD, result.category)
        assertEquals("OTP_FRAUD_CONFLICT", result.reasonCode)
    }
}

class SdkUnitTest {
    @Test
    fun classify_otpChinese_inboxWithOtpRule() = runTest {
        val classifier = SmsClassifierFactory.createForJvmTests()
        val result = classifier.classify(
            SmsInput(
                sender = "10086",
                body = "您的验证码为123456",
                timestampMillis = System.currentTimeMillis(),
            ),
        )
        assertEquals(SmsAction.INBOX, result.action)
        assertEquals(SmsCategory.TRANSACTION, result.category)
        assertTrue(result.ruleIds.contains("OTP_CN_001"))
        classifier.close()
    }

    @Test
    fun classify_otpAndSafeAccountTransfer_reviewOnConflict() = runTest {
        val classifier = SmsClassifierFactory.createForJvmTests()
        val body = "您的验证码为123456，请转账到安全账户"
        val result = classifier.classify(
            SmsInput(
                sender = "unknown",
                body = body,
                timestampMillis = System.currentTimeMillis(),
            ),
        )
        assertEquals(SmsAction.REVIEW, result.action)
        assertEquals("OTP_FRAUD_CONFLICT", result.reasonCode)
        assertTrue(result.ruleIds.contains("OTP_CN_001"))
        assertTrue(result.ruleIds.contains("FRAUD_CN_001"))
        classifier.close()
    }

    @Test
    fun classify_noModelUnknownText_reviewWithoutFakeTransaction() = runTest {
        val classifier = SmsClassifierFactory.createForJvmTests()
        val result = classifier.classify(
            SmsInput(
                sender = null,
                body = "hello there",
                timestampMillis = System.currentTimeMillis(),
            ),
        )
        assertEquals(SmsAction.REVIEW, result.action)
        assertEquals("NO_MODEL_LOW_CONFIDENCE", result.reasonCode)
        classifier.close()
    }

    @Test
    fun liteRtClassifier_withoutModelBytes_isUnavailable() {
        val metadata = ModelMetadata.loadDefault()
        val classifier = LiteRtClassifier(metadata, modelBytes = null)
        assertFalse(classifier.isAvailable)
        assertEquals(null, classifier.predict(IntArray(512) { 0 }))
        classifier.close()
    }
}
