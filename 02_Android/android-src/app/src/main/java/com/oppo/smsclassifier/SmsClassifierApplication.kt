package com.oppo.smsclassifier

import android.app.Application
import com.oppo.smsclassifier.classifier.DefaultSmsClassifier
import com.oppo.smsclassifier.data.ClassificationDatabase

class SmsClassifierApplication : Application() {
    val database: ClassificationDatabase by lazy { ClassificationDatabase.getInstance(this) }

    override fun onCreate() {
        super.onCreate()
        DefaultSmsClassifier.init(this)
        DefaultSmsClassifier.warmUp(this)
    }
}
