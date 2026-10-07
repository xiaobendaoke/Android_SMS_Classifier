package com.oppo.smsclassifier.ui.evaluation

import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EvaluationScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val batchOptions = listOf(5, 10, 20)
    var batchSize by remember { mutableStateOf(10) }
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
                        runOfflineEval(context, text, batchSize)
                    }
                }
            } catch (e: Exception) {
                error = e.message
            } finally {
                loading = false
            }
        }
    }

    fun runRandom(jsonOverride: String?) {
        scope.launch {
            loading = true
            error = null
            exportMsg = null
            try {
                summary = withContext(Dispatchers.IO) {
                    runOfflineEval(context, jsonOverride, batchSize)
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
            Text(
                text = stringResource(R.string.eval_batch_size),
                style = MaterialTheme.typography.labelLarge,
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
            ) {
                batchOptions.forEach { option ->
                    FilterChip(
                        selected = batchSize == option,
                        onClick = { batchSize = option },
                        label = { Text("$option") },
                    )
                }
            }
            Button(
                onClick = { runRandom(externalJson) },
                modifier = Modifier.fillMaxWidth(),
                enabled = !loading,
            ) {
                Text(stringResource(R.string.eval_run))
            }
            Button(
                onClick = { runRandom(externalJson) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                enabled = summary != null && !loading,
            ) {
                Text(stringResource(R.string.eval_resample))
            }
            Button(
                onClick = { openDocument.launch(arrayOf("*/*")) },
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
                    text = stringResource(R.string.eval_pool_hint, s.poolSize, s.sampled),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 8.dp),
                )
                if (s.poolSize > 1 && s.sampled < batchSize) {
                    Text(
                        text = stringResource(R.string.eval_batch_shrink_hint, s.sampled),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.secondary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                Text(
                    text = stringResource(
                        R.string.eval_summary,
                        s.sampled,
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
    jsonOverride: String?,
    batchSize: Int,
): EvalSummary {
    DefaultSmsClassifier.init(context)
    val text = jsonOverride
        ?: context.assets.open("eval/sample_eval.json").bufferedReader().use { it.readText() }
    val pool = OfflineEvalLogic.parseSamples(text)
    if (pool.isEmpty()) error("评测样本池为空")
    val sampled = OfflineEvalLogic.sample(pool, batchSize)
    val results = sampled.map { sample ->
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
    return OfflineEvalLogic.summarize(pool.size, results)
}

/**
 * Export redacted metrics only (no full SMS bodies) via MediaStore Downloads.
 */
private fun exportRedactedReport(context: android.content.Context, summary: EvalSummary): String {
    val payload = OfflineEvalLogic.buildRedactedPayload(summary).toString(2)

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
