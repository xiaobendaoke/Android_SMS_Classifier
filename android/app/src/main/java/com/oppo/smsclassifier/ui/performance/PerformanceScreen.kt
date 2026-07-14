package com.oppo.smsclassifier.ui.performance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PerformanceScreen() {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.tab_performance)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.performance_title),
                style = MaterialTheme.typography.headlineSmall,
            )
            MetricRow(stringResource(R.string.performance_p50), "— ms")
            MetricRow(stringResource(R.string.performance_p95), "— ms")
            MetricRow(stringResource(R.string.performance_p99), "— ms")
            MetricRow(stringResource(R.string.performance_throughput), "— msg/s")
            Text(
                text = stringResource(R.string.performance_placeholder_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.secondary,
            )
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Text(
        text = "$label: $value",
        style = MaterialTheme.typography.bodyLarge,
    )
}
