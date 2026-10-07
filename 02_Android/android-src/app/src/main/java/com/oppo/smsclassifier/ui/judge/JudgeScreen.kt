package com.oppo.smsclassifier.ui.judge

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.ClassificationResult
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsCategory
import com.oppo.smsclassifier.SmsInput
import com.oppo.smsclassifier.classifier.DefaultSmsClassifier
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JudgeScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var sender by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    var result by remember { mutableStateOf<ClassificationResult?>(null) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.tab_judge)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedTextField(
                value = sender,
                onValueChange = { sender = it },
                label = { Text(stringResource(R.string.judge_sender)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = body,
                onValueChange = { body = it },
                label = { Text(stringResource(R.string.judge_body)) },
                minLines = 4,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        val text = body.trim()
                        if (text.isEmpty()) {
                            error = context.getString(R.string.judge_body_required)
                            return@Button
                        }
                        scope.launch {
                            loading = true
                            error = null
                            result = null
                            try {
                                result = withContext(Dispatchers.IO) {
                                    DefaultSmsClassifier.classify(
                                        context,
                                        SmsInput(
                                            sender = sender.trim().takeIf { it.isNotBlank() },
                                            body = text,
                                            timestampMillis = System.currentTimeMillis(),
                                        ),
                                    )
                                }
                            } catch (e: Exception) {
                                error = e.message
                            } finally {
                                loading = false
                            }
                        }
                    },
                    enabled = !loading,
                ) {
                    Text(stringResource(R.string.judge_run))
                }
                OutlinedButton(
                    onClick = {
                        sender = ""
                        body = ""
                        result = null
                        error = null
                    },
                    enabled = !loading,
                ) {
                    Text(stringResource(R.string.judge_clear))
                }
            }
            if (loading) {
                CircularProgressIndicator()
            }
            error?.let {
                Text(text = it, color = MaterialTheme.colorScheme.error)
            }
            result?.let { r ->
                JudgeResultCard(r)
            }
        }
    }
}

@Composable
private fun JudgeResultCard(r: ClassificationResult) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = stringResource(R.string.judge_result_title),
                style = MaterialTheme.typography.titleMedium,
            )
            ResultRow(stringResource(R.string.detail_category), categoryLabel(r.category))
            ResultRow(stringResource(R.string.detail_action), actionLabel(r.action))
            ResultRow(
                stringResource(R.string.detail_confidence),
                "${(r.confidence * 100).toInt()}%",
            )
            ResultRow(
                stringResource(R.string.judge_elapsed),
                String.format("%.1fms", r.elapsedMs),
            )
            ResultRow(stringResource(R.string.detail_reason), r.reasonCode)
            ResultRow(
                stringResource(R.string.detail_rules),
                r.ruleIds.joinToString(", ").ifBlank { "—" },
            )
            ResultRow(stringResource(R.string.detail_model_version), r.modelVersion)
        }
    }
}

@Composable
private fun categoryLabel(category: SmsCategory): String = when (category) {
    SmsCategory.TRANSACTION -> stringResource(R.string.category_transaction)
    SmsCategory.AD -> stringResource(R.string.category_ad)
    SmsCategory.HARASS -> stringResource(R.string.category_harass)
    SmsCategory.FRAUD -> stringResource(R.string.category_fraud)
}

@Composable
private fun actionLabel(action: SmsAction): String = when (action) {
    SmsAction.INBOX -> stringResource(R.string.action_inbox)
    SmsAction.SUSPECT -> stringResource(R.string.action_suspect)
    SmsAction.REVIEW -> stringResource(R.string.action_review)
}

@Composable
private fun ResultRow(label: String, value: String) {
    Text(
        text = "$label: $value",
        style = MaterialTheme.typography.bodyMedium,
    )
}
