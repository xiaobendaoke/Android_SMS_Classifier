package com.oppo.smsclassifier.benchmark

import android.content.Context
import android.os.Environment
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.oppo.smsclassifier.DefaultSmsClassifier as SdkDefaultSmsClassifier
import com.oppo.smsclassifier.SmsClassifier
import com.oppo.smsclassifier.SmsInput
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.math.roundToLong

@RunWith(AndroidJUnit4::class)
class BulkDatasetEvalTest {

    private val labels = listOf("TRANSACTION", "AD", "HARASS", "FRAUD")

    private fun buildClassifier(context: Context): SmsClassifier {
        val assets = context.assets
        val modelBytes = runCatching {
            assets.open("model/sms_bytecnn_int8.tflite").use { it.readBytes() }
        }.getOrNull()
        val readAsset: (String) -> String = { path ->
            assets.open(path).bufferedReader().use { it.readText() }
        }
        return SdkDefaultSmsClassifier(
            readAsset = readAsset,
            modelBytes = modelBytes,
        )
    }

    private fun percentile(sorted: List<Double>, p: Double): Double {
        if (sorted.isEmpty()) return 0.0
        val idx = ((sorted.size - 1) * p).toInt().coerceIn(0, sorted.lastIndex)
        return sorted[idx]
    }

    private fun round1(value: Double): Double {
        return (value * 10.0).roundToLong() / 10.0
    }


    @Test
    fun bulkEval_trainAndValidation() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val classifier = buildClassifier(context)
        classifier.warmUp()

        val externalRoot = context.getExternalFilesDir(null)
        val candidates = listOfNotNull(
            File(context.cacheDir, "eval_input"),
            externalRoot?.let { File(it, "eval_input") },
            File(Environment.getExternalStorageDirectory(), "Download/eval_input"),
        )
        val evalRoot = candidates.firstOrNull { dir -> File(dir, "train.jsonl").exists() }
            ?: candidates.first()
        val reportDir = File(externalRoot ?: context.filesDir, "benchmark")
        reportDir.mkdirs()

        for (dataset in listOf("train", "validation")) {
            val input = File(evalRoot, "$dataset.jsonl")
            require(input.exists()) { "missing input: ${input.absolutePath}; candidates=${candidates.map { it.absolutePath }}" }
            val entries = JSONArray()
            val times = ArrayList<Double>()
            var total = 0
            var labeled = 0
            var correct = 0
            var zhRows = 0
            val confusion = Array(4) { IntArray(4) }
            val tp = IntArray(4)
            val fp = IntArray(4)
            val fn = IntArray(4)

            input.useLines { lines ->
                for (line in lines) {
                    val trimmed = line.trim()
                    if (trimmed.isEmpty()) continue
                    val row = JSONObject(trimmed)
                    val id = row.optString("id", "")
                    val text = row.optString("text", "")
                    val expected = row.optString("label", "").uppercase()
                    val language = row.optString("language", "")
                    if (language == "zh") zhRows++
                    total++
                    if (expected !in labels) continue
                    labeled++

                    val result = classifier.classify(
                        SmsInput(
                            sender = row.optString("sender_group", "").take(20),
                            body = text,
                            timestampMillis = System.currentTimeMillis(),
                        ),
                    )
                    val predicted = result.category.name
                    val elapsed = result.elapsedMs.toDouble()
                    times.add(elapsed)
                    if (predicted == expected) correct++

                    val expectedIdx = labels.indexOf(expected)
                    val predictedIdx = labels.indexOf(predicted)
                    if (expectedIdx >= 0 && predictedIdx >= 0) {
                        confusion[expectedIdx][predictedIdx]++
                        if (expectedIdx == predictedIdx) {
                            tp[expectedIdx]++
                        } else {
                            fp[predictedIdx]++
                            fn[expectedIdx]++
                        }
                    }

                    val entry = JSONObject()
                    entry.put("id", id)
                    entry.put("expected", expected)
                    entry.put("predicted", predicted)
                    entry.put("confidence", result.confidence)
                    entry.put("elapsed_ms", round1(elapsed))
                    entry.put("reason_code", result.reasonCode)
                    entry.put("language", language)
                    entries.put(entry)
                }
            }

            val perClass = JSONObject()
            var macroF1 = 0.0
            for (i in labels.indices) {
                val precision = if (tp[i] + fp[i] > 0) tp[i].toDouble() / (tp[i] + fp[i]) else 0.0
                val recall = if (tp[i] + fn[i] > 0) tp[i].toDouble() / (tp[i] + fn[i]) else 0.0
                val f1 = if (precision + recall > 0) 2.0 * precision * recall / (precision + recall) else 0.0
                macroF1 += f1
                val item = JSONObject()
                item.put("count", tp[i] + fn[i])
                item.put("precision", round1(precision))
                item.put("recall", round1(recall))
                item.put("f1", round1(f1))
                perClass.put(labels[i], item)
            }
            macroF1 /= labels.size

            val sortedTimes = times.sorted()
            val timing = JSONObject()
            timing.put("p50_ms", round1(percentile(sortedTimes, 0.50)))
            timing.put("p95_ms", round1(percentile(sortedTimes, 0.95)))
            timing.put("p99_ms", round1(percentile(sortedTimes, 0.99)))

            val report = JSONObject()
            report.put("dataset", dataset)
            report.put("total_rows", total)
            report.put("zh_rows", zhRows)
            report.put("labeled_rows", labeled)
            report.put("accuracy", if (labeled > 0) round1(correct.toDouble() / labeled) else 0.0)
            report.put("macro_f1", round1(macroF1))
            report.put("per_class", perClass)
            report.put("label_order", JSONArray(labels))
            report.put("confusion_matrix", JSONArray(confusion.map { JSONArray(it.toList()) }))
            report.put("timing_ms", timing)
            report.put("note", "On-device bulk evaluation via the real SDK pipeline; redacted, no SMS bodies.")
            report.put("entries", entries)

            val out = File(reportDir, "app_bulk_eval_$dataset.json")
            out.writeText(report.toString(2))
        }
    }
}
