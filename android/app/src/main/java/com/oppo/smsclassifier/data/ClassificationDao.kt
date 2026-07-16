package com.oppo.smsclassifier.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update

@Dao
interface ClassificationDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(meta: ClassificationMeta)

    @Update
    suspend fun update(meta: ClassificationMeta)

    @Query("SELECT * FROM classification_meta WHERE messageUri = :messageUri LIMIT 1")
    suspend fun getByUri(messageUri: String): ClassificationMeta?

    @Query("SELECT * FROM classification_meta WHERE action = :action ORDER BY createdAt DESC")
    suspend fun listByAction(action: String): List<ClassificationMeta>

    @Query("SELECT * FROM classification_meta WHERE deliverKey = :deliverKey LIMIT 1")
    suspend fun getByDeliverKey(deliverKey: String): ClassificationMeta?
}
