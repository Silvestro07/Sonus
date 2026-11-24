package it.sonus.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import org.json.JSONObject

private const val FLASH_MS = 140L

/** Phase running at [now] (or the next one during a pause); null when every phase is over. */
fun voicePhaseAt(sync: JSONObject, now: Long): Pair<Int, JSONObject>? {
    val beatMs = sync.optLong("beatMs", 1000)
    sync.list("phases").forEachIndexed { index, phase ->
        val beats = phase.optJSONArray("beats") ?: return@forEachIndexed
        if (beats.length() > 0 && now < beats.optLong(beats.length() - 1) + beatMs) return index to phase
    }
    return null
}

fun voiceInstruction(sync: JSONObject, phase: JSONObject?, now: Long): String {
    val name = sync.str("partnerName", "il tuo amico")
    if (phase == null) return "Calcolo…"
    val first = phase.optJSONArray("beats")?.optLong(0) ?: now
    val text = when (phase.str("role")) {
        "click" -> "Prova: tocca il cerchio INSIEME ai click che senti"
        "sing" -> "Tocca a te: di' «TA» nel microfono a ogni click. $name tocca a tempo con la tua voce"
        else -> "Tocca a $name: ascolta la sua voce e tocca il cerchio a ritmo con i suoi «TA»"
    }
    if (now < first - 150) return "Tra ${((first - now + 999) / 1000).coerceAtLeast(1)}…  $text"
    return text
}

private fun describe(needMs: Int): String = if (abs(needMs) < 25) "perfettamente a tempo" else "${abs(needMs)} ms " + if (needMs > 0) "in ritardo" else "in anticipo"
private fun short(lateMs: Int): String = if (abs(lateMs) < 25) "a tempo" else (if (lateMs > 0) "+" else "") + "$lateMs ms"

/** "Sincronizza voci": the same three steps as the PC window (app/ui/voice_sync_dialog.py). */
@Composable fun VoiceSyncPanel(sync: JSONObject, send: Send) {
    val name = sync.str("partnerName", "il tuo amico")
    val status = sync.str("status")
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(status) { while (status == "running") { withFrameMillis { now = System.currentTimeMillis() } } }
    ElevatedCard(Modifier.fillMaxWidth().testTag("voice_sync")) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Sincronizza voci con $name", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            when (status) {
                "running" -> {
                    val current = voicePhaseAt(sync, now)
                    val phase = current?.second
                    val role = phase?.str("role").orEmpty()
                    current?.let { Text("Passo ${it.first + 1} di ${sync.list("phases").size}", color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    Text(voiceInstruction(sync, phase, now), Modifier.heightIn(min = 48.dp))
                    var level = 0f
                    if (phase != null && role != "listen") {
                        val beats = phase.optJSONArray("beats")
                        if (beats != null) for (i in 0 until beats.length()) {
                            val since = now - beats.optLong(i)
                            if (since in 0 until FLASH_MS) level = 1f - since.toFloat() / FLASH_MS
                        }
                    }
                    val enabled = phase != null && role != "sing"
                    val base = MaterialTheme.colorScheme.surfaceVariant
                    val accent = MaterialTheme.colorScheme.primary
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        Box(Modifier.size(220.dp).clip(CircleShape).background(mix(base, accent, level).copy(alpha = if (enabled) 1f else .5f))
                            .pointerInput(enabled) { if (enabled) detectTapGestures(onPress = { send("voice_sync_tap", json("at" to System.currentTimeMillis())) }) }
                            .testTag("voice_sync_tap"), contentAlignment = Alignment.Center) {
                            Text(if (enabled) "TOCCA" else "TA!", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = if (level > .5f) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface)
                        }
                    }
                    Text("Usate le cuffie se potete. Toccate a RITMO, non appena sentite il suono: così il tempo di reazione non conta.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
                    OutlinedButton(onClick = { send("voice_sync_cancel", json()) }, Modifier.fillMaxWidth()) { Text("Annulla") }
                }
                "waiting" -> { Text("Fatto! Aspetto il risultato di $name…"); LinearProgressIndicator(Modifier.fillMaxWidth()) }
                "done" -> {
                    val mine = sync.int("myNeed"); val theirs = sync.int("theirNeed")
                    Text("Tu senti la voce di $name ${describe(mine)}. $name sente la tua ${describe(theirs)}.")
                    Text("Una voce non può arrivare in anticipo: si può essere perfetti in una direzione sola. Scegli:", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    sync.list("choices").forEachIndexed { index, choice ->
                        val late = choice.optJSONArray("late")
                        val label = when (choice.str("mode")) { "me" -> "Io sento $name a tempo"; "them" -> "$name sente me a tempo"; else -> "A metà" }
                        val detail = "tu ${short(late?.optInt(0) ?: 0)}, $name ${short(late?.optInt(1) ?: 0)}"
                        val click = { send("voice_sync_apply", json("mode" to choice.str("mode"))) }
                        if (index == 0) Button(onClick = click, Modifier.fillMaxWidth().defaultMinSize(minHeight = 52.dp)) { Column { Text(label, fontWeight = FontWeight.Bold); Text(detail, style = MaterialTheme.typography.bodySmall) } }
                        else FilledTonalButton(onClick = click, Modifier.fillMaxWidth().defaultMinSize(minHeight = 52.dp)) { Column { Text(label, fontWeight = FontWeight.Bold); Text(detail, style = MaterialTheme.typography.bodySmall) } }
                    }
                    TextButton(onClick = { send("voice_sync_cancel", json()) }) { Text("Annulla") }
                }
                "applied" -> {
                    val delay = sync.obj("applied").int("delay")
                    Text("Voci sincronizzate. Il tuo ritardo: " + if (delay > 0) "+%.2f s".format(delay / 1000.0) else "nessuno")
                    Text("Da ora la stanza tiene le canzoni allineate al decimo di secondo.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    TextButton(onClick = { send("voice_sync_cancel", json()) }) { Text("Chiudi") }
                }
                else -> {
                    Text("Misura non riuscita. ${sync.str("error")}", color = MaterialTheme.colorScheme.error)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { send("voice_sync_start", json("peer" to sync.str("partner"))) }) { Text("Riprova") }
                        TextButton(onClick = { send("voice_sync_cancel", json()) }) { Text("Chiudi") }
                    }
                }
            }
        }
    }
}
