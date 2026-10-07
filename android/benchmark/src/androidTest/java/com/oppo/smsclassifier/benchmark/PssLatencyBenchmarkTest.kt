package com.oppo.smsclassifier.benchmark

import android.app.ActivityManager
import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.oppo.smsclassifier.DefaultSmsClassifier as SdkDefaultSmsClassifier
import com.oppo.smsclassifier.SmsClassifier
import com.oppo.smsclassifier.SmsInput
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale
import kotlin.math.roundToLong

@RunWith(AndroidJUnit4::class)
class PssLatencyBenchmarkTest {

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

    private fun syntheticSamples(count: Int): List<SmsInput> {
        val short = listOf(
            "【测试】您的验证码是 123456，5 分钟内有效。",
            "【测试】本月流量剩余 2.3GB，话费余额 18.5 元。",
            "【测试】商城 618 大促，全场满 300 减 50。",
            "【测试】您的包裹已到达驿站，取件码 8-6-2。",
            "【测试】冒充客服要求转账到安全账户。",
        )
        val medium = listOf(
            "【测试】尊敬的客户，您尾号 4118 的信用卡本月账单已出，应还金额 3276.42 元，请在还款日前完成还款。",
            "【测试】您关注的商品已降价，点击链接查看优惠详情，满 199 减 30，限时三天。",
            "【测试】最后通知：您名下借款已逾期，请今日内处理，否则将影响征信并联系紧急联系人。",
            "【测试】您的账号在异地登录，如非本人操作请点击链接立即验证，否则账号将被冻结。",
            "【测试】您上月新增积分 165 分已到账，可用积分 2163 分，回复数字即可兑换语音包。",
        )
        val long = listOf(
            "【测试】尊敬的客户，感谢您使用本服务。您的订单已发货，物流单号为 TEST202608060001，预计三天内送达，请保持电话畅通，凭取件码到驿站取件。",
            "【测试】本店周年庆回馈新老客户，全场商品低至五折，充值满 1000 送 300，名额有限先到先得，详情请咨询门店客服或点击链接查看。",
            "【测试】您已多次逾期未还，我司将依法对您名下账户进行冻结处理，并将欠款情况上报征信系统，请立即联系客服协商还款方案，否则后果自负。",
            "【测试】您的中奖信息已通过审核，奖品为最新款手机一部，请在二十四小时内点击链接填写收货信息并缴纳手续费后领取，逾期视为自动放弃。",
            "【测试】尊敬的客户，您名下银行卡于今日发生一笔消费交易，金额 1999.00 元，如非本人操作请立即联系发卡行核实，本短信仅供提示。",
        )
        val pool = short + medium + long
        val inputs = ArrayList<SmsInput>(count)
        var index = 0
        while (inputs.size < count) {
            val body = pool[index % pool.size] + " #${index % 7}"
            inputs.add(
                SmsInput(
                    sender = "10086",
                    body = body,
                    timestampMillis = System.currentTimeMillis(),
                ),
            )
            index += 1
        }
        return inputs
    }

    private fun percentile(sorted: List<Double>, p: Double): Double {
        if (sorted.isEmpty()) return 0.0
        val idx = ((sorted.size - 1) * p).toInt().coerceIn(0, sorted.lastIndex)
        return sorted[idx]
    }

    @Test
    fun pssAndLatency_onDevice() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val classifier = buildClassifier(context)
        classifier.warmUp()
        val samples = syntheticSamples(500)

        val pssBefore = currentPssKb(context)
        val times = ArrayList<Double>(samples.size)
        for ((round, sample) in samples.withIndex()) {
            val result = classifier.classify(sample)
            times.add(result.elapsedMs)
            if (round == samples.lastIndex) {
                // Keep the model warm for a realistic steady-state measurement.
                classifier.classify(sample)
            }
        }
        val pssAfter = currentPssKb(context)
        val sorted = times.sorted()
        val p50 = percentile(sorted, 0.50)
        val p95 = percentile(sorted, 0.95)
        val p99 = percentile(sorted, 0.99)
        val totalMs = times.sum()
        val throughput = if (totalMs > 0.0) samples.size * 1000.0 / totalMs else 0.0

        val report = JSONObject()
        report.put("device", android.os.Build.MODEL)
        report.put("sdk", android.os.Build.VERSION.SDK_INT)
        report.put("sample_count", samples.size)
        report.put("p50_ms", round1(p50))
        report.put("p95_ms", round1(p95))
        report.put("p99_ms", round1(p99))
        report.put("throughput_msg_per_sec", round1(throughput))
        report.put("pss_kb_after_warmup", pssBefore)
        report.put("pss_kb_after_run", pssAfter)
        report.put("model_available", pssAfter > 0 || times.isNotEmpty())
        report.put("note", "Engineering emulator measurement; not a 4GB/6GB formal device report.")

        val dir = File(context.getExternalFilesDir(null), "benchmark")
        dir.mkdirs()
        val out = File(dir, "emulator_pss_latency.json")
        out.writeText(report.toString(2))

        assertTrue("p99 should be recorded", p99 > 0.0)
        assertTrue("report file should exist", out.exists())
    }

    private fun currentPssKb(context: Context): Long {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memoryInfo = am.getProcessMemoryInfo(intArrayOf(android.os.Process.myPid()))[0]
        return memoryInfo.totalPss.toLong()
    }

    private fun round1(value: Double): Double {
        return (value * 10.0).roundToLong() / 10.0
    }
}
