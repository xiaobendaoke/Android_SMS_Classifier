package com.oppo.smsclassifier.ui.evaluation

import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.ClassificationResult
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsInput
import com.oppo.smsclassifier.classifier.DefaultSmsClassifier
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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
    val total: Int,
    val labeled: Int,
    val categoryCorrect: Int,
    val accuracy: Double,
    val results: List<EvalResult>,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EvaluationScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var summary by remember { mutableStateOf<EvalSummary?>(null) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var exportMsg by remember { mutableStateOf<String?>(null) }
    var externalJson by remember { mutableStateOf<String?>(null) }

    val openDocument = androidx.activity.compose.rememberLauncherForActivityResult(
        contract = androidx.activity.result.contract.ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            loading = true
            error = null
            try {
                val text = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                }
                if (text.isNullOrBlank()) {
                    error = "无法读取所选文件"
                } else {
                    externalJson = text
                    summary = withContext(Dispatchers.IO) {
                        runOfflineEval(context, text)
                    }
                }
            } catch (e: Exception) {
                error = e.message
            } finally {
                loading = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.tab_evaluation)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
        ) {
            Button(
                onClick = {
                    scope.launch {
                        loading = true
                        error = null
                        exportMsg = null
                        externalJson = null
                        try {
                            summary = withContext(Dispatchers.IO) {
                                runOfflineEval(context)
                            }
                        } catch (e: Exception) {
                            error = e.message
                        } finally {
                            loading = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !loading,
            ) {
                Text(stringResource(R.string.eval_run))
            }
            Button(
                onClick = { openDocument.launch(arrayOf("application/json", "text/*")) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                enabled = !loading,
            ) {
                Text(stringResource(R.string.eval_import_saf))
            }
            Button(
                onClick = {
                    val s = summary ?: return@Button
                    scope.launch {
                        exportMsg = withContext(Dispatchers.IO) {
                            exportRedactedReport(context, s)
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                enabled = summary != null && !loading,
            ) {
                Text(stringResource(R.string.eval_export))
            }
            if (loading) {
                Box(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }
            }
            error?.let {
                Text(text = it, color = MaterialTheme.colorScheme.error)
            }
            exportMsg?.let {
                Text(text = it, style = MaterialTheme.typography.bodySmall)
            }
            summary?.let { s ->
                Text(
                    text = stringResource(
                        R.string.eval_summary,
                        s.total,
                        s.labeled,
                        s.categoryCorrect,
                        (s.accuracy * 100).toInt(),
                    ),
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(top = 8.dp),
            ) {
                items(summary?.results.orEmpty(), key = { it.sample.id }) { item ->
                    EvalResultCard(item)
                }
            }
        }
    }
}

@Composable
private fun EvalResultCard(item: EvalResult) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(text = "#${item.sample.id}", style = MaterialTheme.typography.titleSmall)
            Text(text = item.sample.body, style = MaterialTheme.typography.bodyMedium)
            Text(
                text = "→ ${item.result.category} / ${item.result.action} " +
                    "(${(item.result.confidence * 100).toInt()}%) " +
                    String.format("%.1fms", item.result.elapsedMs),
                style = MaterialTheme.typography.labelLarge,
            )
            item.sample.expectedCategory?.let { expected ->
                val match = expected == item.result.category.name
                Text(
                    text = "期望: $expected ${if (match) "✓" else "✗"}",
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}

private suspend fun runOfflineEval(
    context: android.content.Context,
    jsonOverride: String? = null,
): EvalSummary {
    DefaultSmsClassifier.init(context)
    val json = jsonOverride
        ?: context.assets.open("eval/sample_eval.json").bufferedReader().use { it.readText() }
    val trimmed = json.trim()
    val samplesArray = when {
        trimmed.startsWith("[") -> JSONArray(trimmed)
        else -> {
            val root = JSONObject(trimmed)
            when {
                root.has("samples") -> root.getJSONArray("samples")
                else -> error("评测 JSON 需为数组，或含 samples 字段的对象")
            }
        }
    }
    val samples = (0 until samplesArray.length()).map { i ->
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
    val results = samples.map { sample ->
        val result = DefaultSmsClassifier.classify(
            context,
            SmsInput(
                sender = sample.sender,
                body = sample.body,
                timestampMillis = System.currentTimeMillis(),
            ),
        )
        EvalResult(sample = sample, result = result)
    }
    val labeled = results.filter { it.sample.expectedCategory != null }
    val correct = labeled.count { it.sample.expectedCategory == it.result.category.name }
    return EvalSummary(
        total = results.size,
        labeled = labeled.size,
        categoryCorrect = correct,
        accuracy = if (labeled.isEmpty()) 0.0 else correct.toDouble() / labeled.size,
        results = results,
    )
}

/**
 * Export redacted metrics only (no full SMS bodies) via MediaStore Downloads.
 */
private fun exportRedactedReport(context: android.content.Context, summary: EvalSummary): String {
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
    val payload = JSONObject()
        .put("total", summary.total)
        .put("labeled", summary.labeled)
        .put("categoryCorrect", summary.categoryCorrect)
        .put("accuracy", summary.accuracy)
        .put("rows", rows)
        .toString(2)

    val fileName = "sms_eval_redacted_${System.currentTimeMillis()}.json"
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, fileName)
            put(MediaStore.Downloads.MIME_TYPE, "application/json")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
        }
        val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: return "导出失败：无法创建文件"
        context.contentResolver.openOutputStream(uri)?.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
            ?: return "导出失败：无法写入"
        return "已导出脱敏报告到 Downloads/$fileName"
    }
    return "当前系统需 API 29+ 才能导出到 Downloads"
}
