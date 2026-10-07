package com.oppo.smsclassifier.ui.evaluation

import com.oppo.smsclassifier.ClassificationResult
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsCategory
import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineEvalLogicTest {

    private fun sample(id: String, expected: String? = "AD"): EvalSample =
        EvalSample(id = id, sender = "snd", body = "body-$id", expectedCategory = expected, expectedAction = null)

    private fun result(category: SmsCategory): ClassificationResult =
        ClassificationResult(
            category = category,
            action = SmsAction.INBOX,
            probabilities = floatArrayOf(0.25f, 0.25f, 0.25f, 0.25f),
            confidence = 0.9f,
            rawModelCategory = category,
            ruleIds = emptyList(),
            reasonCode = "MODEL",
            languageHint = null,
            elapsedMs = 1.5,
            modelVersion = "1.0.0",
            rulesVersion = "1.0.0",
            normalizationVersion = "1.0.0",
        )

    @Test
    fun effectiveBatchSize_neverTakesWholePool_whenPoolIsLargerThanOne() {
        assertEquals(7, OfflineEvalLogic.effectiveBatchSize(8, 10))
        assertEquals(9, OfflineEvalLogic.effectiveBatchSize(10, 10))
        assertEquals(5, OfflineEvalLogic.effectiveBatchSize(8, 5))
        assertEquals(10, OfflineEvalLogic.effectiveBatchSize(100, 10))
        assertEquals(1, OfflineEvalLogic.effectiveBatchSize(1, 10))
        assertEquals(0, OfflineEvalLogic.effectiveBatchSize(0, 10))
    }

    @Test
    fun sample_resamplesChangeTheIdSet() {
        val pool = (1..8).map { sample(it.toString()) }
        val sets = (1..20).map { seed ->
            OfflineEvalLogic.sample(pool, 10, Random(seed)).map { it.id }.toSet()
        }
        assertEquals(7, sets.first().size)
        assertTrue(sets.distinct().size > 1)
    }

    @Test
    fun sample_smallBatchHasNoDuplicatesAndChangesAcrossSeeds() {
        val pool = (1..8).map { sample(it.toString()) }
        val first = OfflineEvalLogic.sample(pool, 5, Random(1))
        val second = OfflineEvalLogic.sample(pool, 5, Random(2))
        assertEquals(5, first.size)
        assertEquals(5, first.map { it.id }.toSet().size)
        assertNotEquals(first.map { it.id }.toSet(), second.map { it.id }.toSet())
    }

    @Test
    fun sample_largePoolRespectsBatchSize() {
        val pool = (1..100).map { sample(it.toString()) }
        val batch = OfflineEvalLogic.sample(pool, 10, Random(3))
        assertEquals(10, batch.size)
        assertEquals(10, batch.map { it.id }.toSet().size)
    }

    @Test
    fun sample_singletonAndEmptyPool() {
        val one = listOf(sample("1"))
        assertEquals(1, OfflineEvalLogic.sample(one, 10, Random(1)).size)
        assertTrue(OfflineEvalLogic.sample(emptyList(), 10, Random(1)).isEmpty())
    }

    @Test
    fun summarize_computesAccuracyAndExcludesUnlabeled() {
        val results = listOf(
            EvalResult(sample("1", "TRANSACTION"), result(SmsCategory.TRANSACTION)),
            EvalResult(sample("2", "TRANSACTION"), result(SmsCategory.TRANSACTION)),
            EvalResult(sample("3", "TRANSACTION"), result(SmsCategory.AD)),
            EvalResult(sample("4", "AD"), result(SmsCategory.AD)),
            EvalResult(sample("5", null), result(SmsCategory.FRAUD)),
        )
        val summary = OfflineEvalLogic.summarize(poolSize = 5, results = results)
        assertEquals(5, summary.sampled)
        assertEquals(4, summary.labeled)
        assertEquals(3, summary.categoryCorrect)
        assertEquals(0.75, summary.accuracy, 1e-9)
    }

    @Test
    fun summarize_allUnlabeledAccuracyIsZero() {
        val results = listOf(EvalResult(sample("1", null), result(SmsCategory.AD)))
        val summary = OfflineEvalLogic.summarize(1, results)
        assertEquals(0.0, summary.accuracy, 1e-9)
    }

    @Test
    fun redactedPayloadHasNoBodyTextAndCompleteFields() {
        val results = listOf(EvalResult(sample("1", "AD"), result(SmsCategory.AD)))
        val summary = OfflineEvalLogic.summarize(1, results)
        val payload = OfflineEvalLogic.buildRedactedPayload(summary)
        assertFalse(payload.has("body"))
        val row = payload.getJSONArray("rows").getJSONObject(0)
        assertEquals("1", row.getString("id"))
        assertEquals("AD", row.getString("expectedCategory"))
        assertEquals("AD", row.getString("predictedCategory"))
        assertEquals("INBOX", row.getString("action"))
        assertTrue(row.getBoolean("bodyRedacted"))
        assertEquals(6, row.getInt("bodyLength"))
        assertEquals(1.0, payload.getDouble("accuracy"), 1e-9)
    }

    @Test
    fun parseSamples_supportsArraySamplesObjectAndJsonl() {
        val array = OfflineEvalLogic.parseSamples(
            """[{"id":"a","body":"hello","label":"AD"}]""",
        )
        assertEquals("a", array.single().id)
        assertEquals("AD", array.single().expectedCategory)

        val obj = OfflineEvalLogic.parseSamples(
            """{"samples":[{"id":"b","text":"world","expectedCategory":"FRAUD"}]}""",
        )
        assertEquals("b", obj.single().id)
        assertEquals("FRAUD", obj.single().expectedCategory)

        val jsonl = OfflineEvalLogic.parseSamples(
            "{\"id\":\"1\",\"body\":\"x\",\"label\":\"TRANSACTION\"}\n{\"id\":\"2\",\"text\":\"y\",\"expectedCategory\":\"HARASS\"}",
        )
        assertEquals(2, jsonl.size)
        assertEquals("TRANSACTION", jsonl[0].expectedCategory)
        assertEquals("HARASS", jsonl[1].expectedCategory)
    }

    @Test(expected = Exception::class)
    fun parseSamples_rejectsInvalidJson() {
        OfflineEvalLogic.parseSamples("not json at all")
    }
}
