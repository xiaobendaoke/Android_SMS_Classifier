package com.oppo.smsclassifier.ui.review

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsClassifierApplication
import com.oppo.smsclassifier.data.SmsProviderRepository
import com.oppo.smsclassifier.ui.common.MessageListItem
import com.oppo.smsclassifier.ui.common.MessageListRow
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewScreen(onOpenDetail: (String) -> Unit) {
    val context = LocalContext.current
    var items by remember { mutableStateOf<List<MessageListItem>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        loading = true
        items = withContext(Dispatchers.IO) {
            val app = context.applicationContext as SmsClassifierApplication
            val dao = app.database.classificationDao()
            val smsRepo = SmsProviderRepository(context)
            val metas = dao.listByAction(SmsAction.REVIEW.name)
            val messages = smsRepo.queryRecentMessages(500)
                .associateBy { smsRepo.messageUriForId(it.id) }
            metas.mapNotNull { meta ->
                val msg = messages[meta.messageUri] ?: return@mapNotNull null
                MessageListItem(
                    messageUri = meta.messageUri,
                    address = msg.address,
                    body = msg.body,
                    date = msg.date,
                    meta = meta,
                )
            }
        }
        loading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.tab_review)) })
        },
    ) { padding ->
        when {
            loading -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }
            items.isEmpty() -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(R.string.review_empty)) }
            else -> LazyColumn(modifier = Modifier.fillMaxSize().padding(padding)) {
                items(items, key = { it.messageUri }) { item ->
                    MessageListRow(item = item, onClick = { onOpenDetail(item.messageUri) })
                }
            }
        }
    }
}
