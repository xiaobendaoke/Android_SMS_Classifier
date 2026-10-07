package com.oppo.smsclassifier.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsClassifierApplication
import com.oppo.smsclassifier.data.ClassificationMeta
import com.oppo.smsclassifier.data.SmsProviderRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MessageDetailScreen(messageUri: String) {
    val context = LocalContext.current
    var meta by remember { mutableStateOf<ClassificationMeta?>(null) }
    var address by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }

    LaunchedEffect(messageUri) {
        withContext(Dispatchers.IO) {
            val app = context.applicationContext as SmsClassifierApplication
            meta = app.database.classificationDao().getByUri(messageUri)
            val smsRepo = SmsProviderRepository(context)
            val messageId = messageUri.substringAfterLast('/').toLongOrNull()
            if (messageId != null) {
                smsRepo.queryRecentMessages(500).firstOrNull { it.id == messageId }?.let { msg ->
                    address = msg.address
                    body = msg.body
                }
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.detail_title)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(text = address, style = MaterialTheme.typography.titleLarge)
            Text(text = body, style = MaterialTheme.typography.bodyLarge)
            meta?.let { m ->
                DetailRow(stringResource(R.string.detail_category), m.category)
                DetailRow(stringResource(R.string.detail_action), m.action)
                DetailRow(
                    stringResource(R.string.detail_confidence),
                    "${(m.confidence * 100).toInt()}%",
                )
                DetailRow(stringResource(R.string.detail_reason), m.reasonCode)
                DetailRow(stringResource(R.string.detail_rules), formatRuleIds(m.ruleIdsJson))
                DetailRow(stringResource(R.string.detail_model_version), m.modelVersion)
                DetailRow(stringResource(R.string.detail_rules_version), m.rulesVersion)
            } ?: Text(stringResource(R.string.detail_no_meta))
            Text(
                text = stringResource(R.string.detail_safety_note),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.secondary,
            )
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Text(
        text = "$label: $value",
        style = MaterialTheme.typography.bodyMedium,
    )
}

private fun formatRuleIds(json: String): String {
    return try {
        val arr = JSONArray(json)
        (0 until arr.length()).joinToString(", ") { arr.getString(it) }.ifBlank { "—" }
    } catch (_: Exception) {
        "—"
    }
}
