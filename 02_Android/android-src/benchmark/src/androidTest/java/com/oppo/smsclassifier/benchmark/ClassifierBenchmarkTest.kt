package com.oppo.smsclassifier.benchmark

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.oppo.smsclassifier.ByteEncoder
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ClassifierBenchmarkTest {
    @Test
    fun byteEncoder_fixedLength_onDevice() {
        val ids = ByteEncoder().encode("benchmark")
        assertEquals(512, ids.size)
    }
}
