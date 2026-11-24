package it.sonus.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

fun JSONObject.str(key: String, default: String = ""): String = if (isNull(key)) default else optString(key, default)
fun JSONObject.int(key: String, default: Int = 0) = optInt(key, default)
fun JSONObject.num(key: String, default: Double = 0.0) = optDouble(key, default)
fun JSONObject.flag(key: String, default: Boolean = false): Boolean = when (val value = opt(key)) { is Boolean -> value; is Number -> value.toInt() != 0; is String -> value.equals("true", true) || value == "1"; else -> default }
fun JSONObject.obj(key: String) = optJSONObject(key) ?: JSONObject()
fun JSONObject.list(key: String): List<JSONObject> = (optJSONArray(key) ?: JSONArray()).objects()
fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
fun json(vararg pairs: Pair<String, Any?>): JSONObject = JSONObject().apply { pairs.forEach { (key, value) -> put(key, value ?: JSONObject.NULL) } }
fun seconds(ms: Number): String { val total = ms.toLong().coerceAtLeast(0) / 1000; return "%d:%02d".format(total / 60, total % 60) }
fun ids(songs: List<JSONObject>) = JSONArray(songs.map { it.int("id") })
typealias Send = (String, JSONObject) -> Unit

@Composable fun SonusTheme(settings: JSONObject = JSONObject(), content: @Composable () -> Unit) {
    val colors = settings.obj("themeColors")
    fun color(key: String, fallback: String) = runCatching { Color(android.graphics.Color.parseColor(colors.str(key, fallback))) }.getOrDefault(Color(android.graphics.Color.parseColor(fallback)))
    // Same palette as the PC app (app/ui/theme.py: DEFAULT_COLORS and the derived ELEVATED/SUBTEXT tones)
    val accent = color("accent", "#1ED760")
    val background = color("background", "#121212")
    val panel = color("panel", "#181818")
    val text = color("text", "#FFFFFF")
    val onAccent = if (accent.luminance() > 0.45f) Color.Black else Color.White
    MaterialTheme(colorScheme = darkColorScheme(primary = accent, onPrimary = onAccent, secondaryContainer = mix(panel, text, .10f), onSecondaryContainer = text,
        background = background, surface = panel, surfaceVariant = mix(panel, text, .07f), surfaceContainer = panel, surfaceContainerHigh = mix(panel, text, .07f),
        onSurface = text, onBackground = text, onSurfaceVariant = mix(text, background, .30f), outline = mix(background, text, .10f)), content = content)
}

fun mix(first: Color, second: Color, amount: Float) = Color(
    first.red + (second.red - first.red) * amount, first.green + (second.green - first.green) * amount,
    first.blue + (second.blue - first.blue) * amount, 1f)

// Placeholder covers of the PC app (theme.placeholderCover): gradient + music note, chosen by the song id
private val PLACEHOLDER_COLORS = listOf(0xFF450AF5 to 0xFF8E8EE5, 0xFF1E3264 to 0xFF4F7BD6, 0xFF8C1932 to 0xFFE8115B, 0xFF056952 to 0xFF27856A,
    0xFFBA5D07 to 0xFFF59B23, 0xFF503750 to 0xFFAF2896, 0xFF283C46 to 0xFF477D95, 0xFF7D4B32 to 0xFFD84000)

@Composable fun Artwork(song: JSONObject, modifier: Modifier = Modifier.size(52.dp)) {
    val cover = song.str("cover").ifEmpty { song.str("image").ifEmpty { song.str("thumbnail") } }
    val (start, end) = PLACEHOLDER_COLORS[Math.floorMod(song.optInt("id", 0), PLACEHOLDER_COLORS.size)]
    Box(modifier.clip(RoundedCornerShape(4.dp)).background(Brush.linearGradient(listOf(Color(start), Color(end)))), contentAlignment = Alignment.Center) {
        if (cover.isNotEmpty()) AsyncImage(model = if (cover.startsWith("http")) cover else File(cover), contentDescription = null, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        else Text("♫", color = Color.White.copy(alpha = .85f), style = MaterialTheme.typography.headlineMedium)
    }
}

@Composable fun Title(text: String, subtitle: String = "") {
    Column(Modifier.padding(vertical = 10.dp)) {
        Text(text, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        if (subtitle.isNotEmpty()) Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable fun Action(label: String, enabled: Boolean = true, click: () -> Unit) {
    FilledTonalButton(onClick = click, enabled = enabled, modifier = Modifier.defaultMinSize(minHeight = 48.dp)) { Text(label) }
}

@Composable fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f).padding(end = 12.dp))
        Switch(checked, onCheckedChange = onChange)
    }
}

@Composable fun ValueSlider(label: String, value: Float, range: ClosedFloatingPointRange<Float>, display: String = "%.1f".format(value), onDone: (Float) -> Unit) {
    var draft by remember(value) { mutableFloatStateOf(value.coerceIn(range)) }
    Row { Text(label, Modifier.weight(1f)); Text(display, color = MaterialTheme.colorScheme.primary) }
    Slider(value = draft, onValueChange = { draft = it }, valueRange = range, onValueChangeFinished = { onDone(draft) })
}
