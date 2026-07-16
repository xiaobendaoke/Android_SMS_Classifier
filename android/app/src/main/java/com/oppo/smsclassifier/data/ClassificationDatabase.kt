package com.oppo.smsclassifier.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [ClassificationMeta::class],
    version = 2,
    exportSchema = false,
)
abstract class ClassificationDatabase : RoomDatabase() {
    abstract fun classificationDao(): ClassificationDao

    companion object {
        @Volatile
        private var instance: ClassificationDatabase? = null

        fun getInstance(context: Context): ClassificationDatabase {
            return instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    ClassificationDatabase::class.java,
                    "classification_meta.db",
                )
                    // Demo DB: schema additions (deliverKey) — wipe local meta on upgrade.
                    .fallbackToDestructiveMigration()
                    .build()
                    .also { instance = it }
            }
        }
    }
}
