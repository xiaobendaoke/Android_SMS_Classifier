package com.oppo.smsclassifier.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "classification_meta")
data class ClassificationMeta(
    @PrimaryKey val messageUri: String,
    val messageId: Long?,
    val threadId: Long?,
    val category: String,
    val action: String,
    val confidence: Float,
    val reasonCode: String,
    val ruleIdsJson: String,
    val modelVersion: String,
    val rulesVersion: String,
    val createdAt: Long,
)
