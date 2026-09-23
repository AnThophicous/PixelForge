package com.brenno.pixelforge

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.IconButton
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val queue = mutableStateListOf<QueueItem>()
    private var running by mutableStateOf(false)
    private var status by mutableStateOf("Adicione imagens ou vídeos.")
    private val secretStore by lazy { SecretStore(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { PixelForgeTheme { PixelForgeScreen() } }
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun PixelForgeScreen() {
        val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris -> add(uris, false) }
        val videoPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris -> add(uris, true) }
        val envPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { importEnv(it) } }
        var scale by remember { mutableStateOf(4) }
        var showSettings by remember { mutableStateOf(false) }
        var layaKey by remember { mutableStateOf(secretStore.read().orEmpty()) }

        Scaffold(topBar = { TopAppBar(title = { Text("PixelForge") }, actions = { IconButton(onClick = { showSettings = !showSettings }) { Icon(Icons.Default.Settings, "Configurações") } }) }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp)) {
                Spacer(Modifier.height(12.dp))
                Text("Upscale local", style = MaterialTheme.typography.headlineMedium)
                Text("FSRCNN para imagens · vídeo em escala leve", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(16.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(onClick = { imagePicker.launch(arrayOf("image/*")) }, enabled = !running) {
                        Icon(Icons.Default.AddPhotoAlternate, null); Spacer(Modifier.padding(3.dp)); Text("Imagens")
                    }
                    Button(onClick = { videoPicker.launch(arrayOf("video/*")) }, enabled = !running) {
                        Icon(Icons.Default.Movie, null); Spacer(Modifier.padding(3.dp)); Text("Vídeos")
                    }
                }
                Spacer(Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Escala")
                    listOf(2, 3, 4).forEach { value -> FilterChip(selected = scale == value, onClick = { scale = value }, label = { Text("${value}×") }) }
                }
                if (showSettings) {
                    Spacer(Modifier.height(12.dp))
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(14.dp)) {
                            Text("Integração Laya", style = MaterialTheme.typography.titleMedium)
                            OutlinedTextField(value = layaKey, onValueChange = { layaKey = it }, label = { Text("LAYA_KEY") }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                                Button(onClick = { secretStore.write(layaKey.trim()); status = "Chave Laya salva com proteção do Android." }) { Text("Salvar chave") }
                                Button(onClick = { envPicker.launch(arrayOf("*/*")) }) { Text("Importar .env") }
                            }
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
                if (running) LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(status, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(vertical = 8.dp))
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(queue, key = { it.id }) { item -> QueueCard(item) }
                }
                Button(onClick = { process(scale) }, enabled = queue.any { it.state == QueueState.WAITING } && !running, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Default.PlayArrow, null); Spacer(Modifier.padding(3.dp)); Text("Processar fila, um por vez")
                }
                Spacer(Modifier.height(12.dp))
            }
        }
    }

    @Composable
    private fun QueueCard(item: QueueItem) {
        Card(Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(if (item.video) Icons.Default.Movie else Icons.Default.AddPhotoAlternate, null, tint = MaterialTheme.colorScheme.primary)
                Column(Modifier.padding(start = 12.dp)) {
                    Text(item.name, maxLines = 1)
                    Text(item.state.label, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }

    private fun add(uris: List<Uri>, video: Boolean) {
        uris.forEach { uri ->
            contentResolver.takePersistableUriPermission(uri, android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
            queue += QueueItem(uri, uri.lastPathSegment ?: "arquivo", video)
        }
        status = "${queue.count { it.state == QueueState.WAITING }} item(ns) aguardando."
    }

    private fun importEnv(uri: Uri) {
        val content = runCatching { contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() } }.getOrNull()
        val key = content?.lineSequence()?.map { it.trim() }?.firstOrNull { it.startsWith("LAYA_KEY=") }?.substringAfter('=')?.trim()?.trim('"', '\'')
        if (!key.isNullOrBlank()) {
            secretStore.write(key)
            status = "LAYA_KEY importada e protegida localmente."
        } else {
            status = "O arquivo não contém LAYA_KEY válida."
        }
    }

    private fun process(scale: Int) {
        if (running) return
        running = true
        lifecycleScope.launch {
            queue.filter { it.state == QueueState.WAITING }.forEach { item ->
                item.state = QueueState.RUNNING
                status = "Processando ${item.name}"
                runCatching {
                    withContext(Dispatchers.Default) {
                        if (item.video) withContext(Dispatchers.Main.immediate) { VideoUpscaler(this@MainActivity).process(item.uri, scale) }
                        else ImageUpscaler(this@MainActivity).process(item.uri, scale)
                    }
                }.onSuccess { item.state = QueueState.DONE }.onFailure { error ->
                    item.state = QueueState.ERROR
                    item.error = error.message ?: "falha desconhecida"
                }
            }
            running = false
            status = "Fila concluída."
        }
    }
}

enum class QueueState(val label: String) { WAITING("aguardando"), RUNNING("processando"), DONE("concluído"), ERROR("erro") }

class QueueItem(val uri: Uri, val name: String, val video: Boolean) {
    val id: String = uri.toString() + video
    var state by mutableStateOf(QueueState.WAITING)
    var error: String? = null
}

@Composable
private fun PixelForgeTheme(content: @Composable () -> Unit) {
    val blue = androidx.compose.material3.lightColorScheme(primary = androidx.compose.ui.graphics.Color(0xFF1769E0), secondary = androidx.compose.ui.graphics.Color(0xFF315FAF), tertiary = androidx.compose.ui.graphics.Color(0xFF006C76))
    MaterialTheme(colorScheme = blue, content = content)
}
