package com.oppo.smsclassifier.ui.evaluation

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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EvaluationScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var results by remember { mutableStateOf<List<EvalResult>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

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
                        try {
                            results = withContext(Dispatchers.IO) {
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
            if (loading) {
                Box(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }
            }
            error?.let {
                Text(text = it, color = MaterialTheme.colorScheme.error)
            }
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(top = 8.dp),
            ) {
                items(results, key = { it.sample.id }) { item ->
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
                    "(${(item.result.confidence * 100).toInt()}%)",
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

private suspend fun runOfflineEval(context: android.content.Context): List<EvalResult> {
    val json = context.assets.open("eval/sample_eval.json").bufferedReader().use { it.readText() }
    val root = JSONObject(json)
    val samplesArray = root.getJSONArray("samples")
    val samples = (0 until samplesArray.length()).map { i ->
        val obj = samplesArray.getJSONObject(i)
        EvalSample(
            id = obj.getString("id"),
            sender = obj.optString("sender").takeIf { it.isNotBlank() },
            body = obj.getString("body"),
            expectedCategory = obj.optString("expectedCategory").takeIf { it.isNotBlank() },
            expectedAction = obj.optString("expectedAction").takeIf { it.isNotBlank() },
        )
    }
    return samples.map { sample ->
        val result = DefaultSmsClassifier.classify(
            SmsInput(
                sender = sample.sender,
                body = sample.body,
                timestampMillis = System.currentTimeMillis(),
            ),
        )
        EvalResult(sample = sample, result = result)
    }
}
