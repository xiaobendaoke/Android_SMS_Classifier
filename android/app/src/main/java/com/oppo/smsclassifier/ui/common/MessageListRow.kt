package com.oppo.smsclassifier.ui.common

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.data.ClassificationMeta
import com.oppo.smsclassifier.data.SmsProviderRepository

data class MessageListItem(
    val messageUri: String,
    val address: String,
    val body: String,
    val date: Long,
    val meta: ClassificationMeta?,
)

@Composable
fun MessageListRow(
    item: MessageListItem,
    onClick: () -> Unit,
    trailing: @Composable (() -> Unit)? = null,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clickable(onClick = onClick),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = item.address.ifBlank { "未知号码" },
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = item.body,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            item.meta?.let { meta ->
                Text(
                    text = "${meta.category} · ${meta.action} · ${(meta.confidence * 100).toInt()}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            trailing?.invoke()
        }
    }
}

fun SmsProviderRepository.SmsMessageDisplay.toListItem(meta: ClassificationMeta?): MessageListItem =
    MessageListItem(
        messageUri = messageUriForId(id),
        address = address,
        body = body,
        date = date,
        meta = meta,
    )
