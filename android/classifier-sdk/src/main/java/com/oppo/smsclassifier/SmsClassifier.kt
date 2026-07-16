package com.oppo.smsclassifier

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Main SDK entry point for offline SMS classification.
 */
interface SmsClassifier : AutoCloseable {
    suspend fun classify(input: SmsInput): ClassificationResult
    fun warmUp()
    override fun close()
}

/**
 * Production classifier: normalize → rules → encode → optional model → route.
 */
class DefaultSmsClassifier(
    private val readAsset: (String) -> String,
    private val modelBytes: ByteArray? = null,
) : SmsClassifier {
    private val metadata: ModelMetadata = ModelMetadata.loadFromJson(
        readAsset("model/model_metadata.json"),
    )
    private val normalizer: TextNormalizer = TextNormalizer(
        version = metadata.normalizationVersion,
        confusableReplacements = TextNormalizer.loadConfusablesFromJson(
            readAsset("normalize/confusables.json"),
        ),
    )
    private val ruleEngine: RuleEngine = RuleEngine.fromReader(readAsset)
    private val byteEncoder: ByteEncoder = ByteEncoder(
        maxBytes = metadata.inputLength,
        padId = metadata.padId,
        byteOffset = metadata.byteOffset,
    )
    private val model: LiteRtPredictor = LiteRtClassifier(metadata, modelBytes)
    private val router: DecisionRouter = DecisionRouter(metadata)

    override suspend fun classify(input: SmsInput): ClassificationResult {
        val startNs = System.nanoTime()
        return withContext(Dispatchers.Default) {
            val normalized = normalizer.normalize(input.body)
            val signals = ruleEngine.collectSignals(normalized, input.sender)
            val tokenIds = byteEncoder.encode(normalized)
            val modelProbs = if (model.isAvailable) model.predict(tokenIds) else null
            val result = router.route(
                input = input,
                normalized = normalized,
                signals = signals,
                modelProbs = modelProbs,
                modelAvailable = model.isAvailable && modelProbs != null,
            )
            val elapsedMs = (System.nanoTime() - startNs) / 1_000_000.0
            result.copy(
                elapsedMs = elapsedMs,
                rulesVersion = ruleEngine.rulesVersion,
                normalizationVersion = normalizer.normalizationVersion,
            )
        }
    }

    override fun warmUp() {
        model.warmUp()
    }

    override fun close() {
        model.close()
    }
}

/**
 * Phase 0 stub kept for backward compatibility in tests.
 */
class StubSmsClassifier : SmsClassifier {
    private val classifier = SmsClassifierFactory.createForJvmTests()

    override suspend fun classify(input: SmsInput): ClassificationResult =
        classifier.classify(input)

    override fun warmUp() = classifier.warmUp()

    override fun close() = classifier.close()
}

object SmsClassifierFactory {
    fun createForJvmTests(modelBytes: ByteArray? = null): SmsClassifier =
        DefaultSmsClassifier(
            readAsset = AssetLoader::readText,
            modelBytes = modelBytes,
        )
}
