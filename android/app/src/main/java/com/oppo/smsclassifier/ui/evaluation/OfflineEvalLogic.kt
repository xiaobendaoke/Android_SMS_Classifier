package com.oppo.smsclassifier.ui.evaluation

import com.oppo.smsclassifier.ClassificationResult
import kotlin.random.Random
import org.json.JSONArray
import org.json.JSONObject

data class EvalSample(
    val id: String,
    val sender: String?,
    val body: String,
    val expectedCategory: String?,
    val expectedAction: String?,
)

data class EvalResult(
    val sample: EvalSample,
    val result: ClassificationResult,
)

data class EvalSummary(
    val poolSize: Int,
    val sampled: Int,
    val labeled: Int,
    val categoryCorrect: Int,
    val accuracy: Double,
    val results: List<EvalResult>,
)

/**
 * Pure offline-evaluation logic. Kept Android-free so it can be unit tested on the JVM.
 */
object OfflineEvalLogic {

    /**
     * A batch can never contain the whole pool when the pool has more than one row;
     * otherwise "换一批" would only shuffle order and never change the sample set.
     */
    fun effectiveBatchSize(poolSize: Int, selectedBatchSize: Int): Int = when {
        poolSize <= 0 -> 0
        poolSize == 1 -> 1
        poolSize <= selectedBatchSize -> poolSize - 1
        else -> selectedBatchSize
    }

    fun sample(
        pool: List<EvalSample>,
        selectedBatchSize: Int,
        random: Random = Random.Default,
    ): List<EvalSample> {
        val size = effectiveBatchSize(pool.size, selectedBatchSize)
        return pool.shuffled(random).take(size)
    }

    fun summarize(poolSize: Int, results: List<EvalResult>): EvalSummary {
        val labeled = results.filter { it.sample.expectedCategory != null }
        val correct = labeled.count { it.sample.expectedCategory == it.result.category.name }
        return EvalSummary(
            poolSize = poolSize,
            sampled = results.size,
            labeled = labeled.size,
            categoryCorrect = correct,
            accuracy = if (labeled.isEmpty()) 0.0 else correct.toDouble() / labeled.size,
            results = results,
        )
    }

    fun buildRedactedPayload(summary: EvalSummary): JSONObject {
        val rows = JSONArray()
        for (item in summary.results) {
            rows.put(
                JSONObject()
                    .put("id", item.sample.id)
                    .put("expectedCategory", item.sample.expectedCategory)
                    .put("predictedCategory", item.result.category.name)
                    .put("action", item.result.action.name)
                    .put("confidence", item.result.confidence)
                    .put("elapsedMs", item.result.elapsedMs)
                    .put("reasonCode", item.result.reasonCode)
                    .put("bodyRedacted", true)
                    .put("bodyLength", item.sample.body.length),
            )
        }
        return JSONObject()
            .put("poolSize", summary.poolSize)
            .put("sampled", summary.sampled)
            .put("labeled", summary.labeled)
            .put("categoryCorrect", summary.categoryCorrect)
            .put("accuracy", summary.accuracy)
            .put("rows", rows)
    }

    fun parseSamples(text: String): List<EvalSample> = try {
        parseSamplesUnchecked(text)
    } catch (e: Exception) {
        error("评测文件格式错误：无法解析所选文件（${e.message}）")
    }

    private fun parseSamplesUnchecked(text: String): List<EvalSample> {
        val trimmed = text.trim()
        val samplesArray = if (trimmed.startsWith("[")) {
            JSONArray(trimmed)
        } else if (isJsonl(text)) {
            parseJsonl(text)
        } else {
            val root = JSONObject(trimmed)
            when {
                root.has("samples") -> root.getJSONArray("samples")
                else -> error("评测 JSON 需为数组，或含 samples 字段的对象")
            }
        }
        return (0 until samplesArray.length()).map { i ->
            val obj = samplesArray.getJSONObject(i)
            EvalSample(
                id = obj.optString("id", "eval-$i"),
                sender = obj.optString("sender").takeIf { it.isNotBlank() },
                body = obj.optString("body", obj.optString("text")),
                expectedCategory = obj.optString("expectedCategory", obj.optString("label"))
                    .takeIf { it.isNotBlank() },
                expectedAction = obj.optString("expectedAction").takeIf { it.isNotBlank() },
            )
        }
    }

    private fun isJsonl(text: String): Boolean {
        val nonEmptyLines = text.lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .toList()
        return nonEmptyLines.size > 1 && nonEmptyLines.all { it.startsWith("{") }
    }

    private fun parseJsonl(text: String): JSONArray {
        val arr = JSONArray()
        text.lineSequence().forEach { line ->
            val trimmed = line.trim()
            if (trimmed.isEmpty()) return@forEach
            if (!trimmed.startsWith("{")) error("JSONL 每行需为 JSON 对象")
            arr.put(JSONObject(trimmed))
        }
        if (arr.length() == 0) error("评测文件为空")
        return arr
    }
}
