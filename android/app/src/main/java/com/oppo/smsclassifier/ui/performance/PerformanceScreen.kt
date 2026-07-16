package com.oppo.smsclassifier.ui.performance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsInput
import com.oppo.smsclassifier.classifier.DefaultSmsClassifier
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.system.measureTimeMillis

data class LatencyStats(
    val count: Int,
    val p50Ms: Double,
    val p95Ms: Double,
    val p99Ms: Double,
    val throughputMsgPerSec: Double,
    val modelAvailable: Boolean,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PerformanceScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var stats by remember { mutableStateOf<LatencyStats?>(null) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

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
            Button(
                onClick = {
                    scope.launch {
                        loading = true
                        error = null
                        try {
                            stats = withContext(Dispatchers.Default) {
                                measureLocalLatency(context)
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
                Text(stringResource(R.string.performance_run))
            }
            if (loading) {
                CircularProgressIndicator()
            }
            error?.let {
                Text(text = it, color = MaterialTheme.colorScheme.error)
            }
            val s = stats
            if (s != null) {
                MetricRow(stringResource(R.string.performance_p50), "%.1f ms".format(s.p50Ms))
                MetricRow(stringResource(R.string.performance_p95), "%.1f ms".format(s.p95Ms))
                MetricRow(stringResource(R.string.performance_p99), "%.1f ms".format(s.p99Ms))
                MetricRow(
                    stringResource(R.string.performance_throughput),
                    "%.1f msg/s".format(s.throughputMsgPerSec),
                )
                Text(
                    text = stringResource(
                        if (s.modelAvailable) R.string.performance_model_on
                        else R.string.performance_model_off,
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
                Text(
                    text = stringResource(R.string.performance_budget_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            } else if (!loading) {
                Text(
                    text = stringResource(R.string.performance_placeholder_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
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

private suspend fun measureLocalLatency(context: android.content.Context): LatencyStats {
    DefaultSmsClassifier.init(context)
    DefaultSmsClassifier.warmUp(context)

    val samples = listOf(
        "您的验证码是 123456，请勿泄露。",
        "Limited offer! Click now to claim your free gift card.",
        "Pay me back now or I will keep calling you every hour.",
        "Your account is locked. Verify at http://secure-fake.example",
        "Pembayaran Anda sebesar Rp150000 telah diterima.",
        "आपका OTP 654321 है। साझा न करें।",
    )

    val times = mutableListOf<Long>()
    val wallMs = measureTimeMillis {
        repeat(20) { round ->
            for (body in samples) {
                val elapsed = measureTimeMillis {
                    DefaultSmsClassifier.classify(
                        context,
                        SmsInput(
                            sender = "10086",
                            body = body,
                            timestampMillis = System.currentTimeMillis(),
                        ),
                    )
                }
                // Skip first round as warm-up.
                if (round > 0) times += elapsed
            }
        }
    }

    times.sort()
    fun percentile(p: Double): Double {
        if (times.isEmpty()) return 0.0
        val idx = ((times.size - 1) * p).toInt().coerceIn(0, times.lastIndex)
        return times[idx].toDouble()
    }

    val totalMsgs = times.size.coerceAtLeast(1)
    val throughput = if (wallMs > 0) totalMsgs * 1000.0 / wallMs else 0.0
    val probe = DefaultSmsClassifier.classify(
        context,
        SmsInput(sender = "probe", body = "warm", timestampMillis = 0L),
    )
    val modelOn = probe.modelVersion.isNotBlank() &&
        probe.reasonCode != "NO_MODEL_LOW_CONFIDENCE"

    return LatencyStats(
        count = times.size,
        p50Ms = percentile(0.50),
        p95Ms = percentile(0.95),
        p99Ms = percentile(0.99),
        throughputMsgPerSec = throughput,
        modelAvailable = modelOn || probe.elapsedMs > 0,
    )
}
