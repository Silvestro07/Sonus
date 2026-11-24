# Sonus — contesto per chi lavora sul codice (persone o AI)

Leggi questo file prima di tutto: spiega cosa fa il codice, dove stanno le cose e le regole da rispettare,
così non serve rileggere tutto il repository da zero. Tienilo aggiornato quando cambi qualcosa di importante.

## Cos'è
Player musicale per Windows in stile Spotify (Python 3 + PySide6/Qt), più un port Android nella cartella `android/`.
Funzioni: libreria e playlist, ricerca e streaming/download da YouTube (yt-dlp), import da Spotify, testi
sincronizzati, video di sfondo, equalizzatore 10 bande, effetti (velocità, riverbero, bass boost), loop A-B, taglio
audio, "Ascolta insieme" (stanze via MQTT), playlist condivise, aggiornamenti automatici da GitHub Releases.
Testi dell'interfaccia e messaggi di log sono in italiano; commenti e nomi nel codice in inglese, camelCase.

## Avvio, build, test
- Avvio sviluppo: `python main.py` (dipendenze in `requirements.txt`).
- Build Windows: `sonus_build.py` / `INSTALLA_E_AGGIORNA.bat` (PyInstaller + Inno Setup `installer.iss`).
  Release: workflow `.github/workflows/release.yml` (push su `main`).
- Dati utente: `%APPDATA%\Sonus` (`library.db` SQLite, `settings.json`, `log.txt`, `temp/`, `stream_cache.json`).
  In test si usa `SONUS_DATA_DIR` (lo imposta `tests/conftest.py`).
- Test PC: `QT_QPA_PLATFORM=offscreen python -m pytest tests -q`.
  - I test di stanze/playlist condivise (`test_together`, `test_ui_together`, `test_session_link`, `test_room_files`,
    parte di `test_playlist_sync`) richiedono `mosquitto` nel PATH: senza, danno errore in setup (non è un bug).
    amqtt NON è un sostituto valido (fallisce anche sul codice originale).
  - `test_discord_presence::test_presenceTalksToDiscordPipe` fallisce su Windows (AF_UNIX): preesistente.
  - Con Python 3.14 + PySide6 6.11 l'esecuzione di `test_streaming.py` + `test_ui_streaming.py` nello stesso processo
    va in segfault a volte, anche sul `main` originale: è un problema dell'ambiente, non del codice. Esegui i file
    separatamente se succede.
- Test backend Android (senza SDK): `python android/tools/prepare_core.py --source . --output <dir>` poi
  `PYTHONPATH="android/app/src/main/python;<dir>" python -m pytest android/tests -q` (`:` invece di `;` su Linux).
- APK: workflow `.github/workflows/android.yml` (branch `android` e `Android-Sonus`), oppure in locale con JDK 17/21,
  Android SDK 35 e CPython 3.10 completo: `cd android && gradlew assembleDebug` (vedi `android/DEPENDENCIES.md`).

## Mappa del codice PC (`app/`)
| File | Cosa fa |
| --- | --- |
| `main.py` | Avvio: diagnostica/log, istanza singola, `MainWindow`. |
| `config.py` | Percorsi, `settings` (JSON con `DEFAULT_SETTINGS`), versione, `ffmpegExe()`/`denoExe()`. |
| `database.py` | SQLite: canzoni, playlist, loop, preferiti, ascolti. Canzoni in streaming hanno `path = "stream:<url o ytsearch1:...>"`. |
| `player.py` | `Player`: coda, shuffle/repeat, caricamento (file o stream risolto in background), prefetch delle prossime, errori/fallback, loop A-B, ripristino sessione. |
| `audio_engine.py` | `AudioEngine`: sostituto di QMediaPlayer. ffmpeg decodifica in PCM 16 bit in un `PcmStore`; il callback `sounddevice` applica EQ (scipy sosfilt), bass boost, riverbero (convoluzione a partizioni), fade, volume/bilanciamento, spettro, e mixa i "click" del sincronizzatore voci. Stream remoti scaricati a pezzi da 10 MB (`_Decoder._feed`). |
| `downloader.py` | yt-dlp: ricerca, `resolveStream` (link audio diretto, cache in memoria + `stream_cache.json`), `resolveVideoStream` (preso dalla stessa risposta dell'audio quando possibile), download, gestione anti-bot/IPv4. |
| `together.py` | "Ascolta insieme": stato della stanza (coda, indice, posizione, `at`, versione) via MQTT, `ClockSync` ping/pong, correzione drift, ritardo personale, file personali cifrati, **Sincronizza voci** (`startVoiceSync`, `voiceSyncTap`, `applyVoiceSync`). |
| `together_sync.py` | Funzioni pure: `expectedPosition`, `ClockSync`, chiavi brano. |
| `voice_sync.py` | Logica pura del sincronizzatore voci (piano dei click, misura dai tocchi, scelta dei ritardi). Il metodo è spiegato nel docstring. |
| `session_link.py` | Client MQTT (paho) con failover tra broker, codici `SONUS-XXXX-XXXX`, link `sonus://`. |
| `playlist_sync.py` | Playlist condivise (codici `SONUSP-…`). |
| `room_files.py` | Upload temporaneo cifrato dei file personali per la stanza. |
| `lyrics.py`, `metadata.py`, `audio_tools.py`, `spotify_import.py`, `discover.py`, `fast_net.py`, `video_proxy.py`, `updater.py`/`app_updater.py`, `discord_presence.py`, `media_keys.py`, `migration.py`, `diagnostics.py`, `workers.py` (`runInBackground` su QThreadPool) | Funzioni di supporto con il nome che dicono. |
| `ui/main_window.py` | Finestra principale: navigazione, collegamenti fra tutto, salvataggio sessione, video, tray, scorciatoie. |
| `ui/player_bar.py`, `ui/now_playing*.py`, `ui/views.py`, `ui/song_table.py`, `ui/dialogs.py`, `ui/equalizer_page.py`, `ui/effects*.py`, `ui/mix_dialog.py`, `ui/discover_page.py`, `ui/together_popup.py`, `ui/voice_sync_dialog.py`, `ui/video_controller.py`, `ui/theme.py` | Pagine e componenti. `theme.py` ha palette (DEFAULT_COLORS), icone e cache copertine (limitata). |

## Android (`android/`)
- UI Kotlin/Jetpack Compose (`android/app/src/main/java/it/sonus/mobile/`): `MobileUi.kt` (navigazione e pagine
  principali), `PlayerScreens.kt` (player, effetti, EQ, loop/taglio, testi), `OtherScreens.kt` (video, stanza,
  impostazioni), `VoiceSync.kt`, `UiSupport.kt` (tema = palette del PC, helper JSON).
- Il backend è **lo stesso codice Python del PC** eseguito con Chaquopy: `android/tools/prepare_core.py` copia
  `app/*.py` in `sonus_core` sostituendo solo i confini di piattaforma (import Qt → `sonus_mobile/runtime.py`,
  ffmpeg/QuickJS nativi, AudioTrack in `android_audio.py`). **Se cambi `app/audio_engine.py`, `downloader.py`,
  `config.py`, `playlist_sync.py` o `app_updater.py`, controlla che i punti sostituiti da `prepare_core.py` esistano
  ancora** (usa `_replace_required`, che fallisce se non li trova) e rigenera/esegui i test Android.
- `sonus_mobile/controller.py`: tutte le azioni dell'UI (`dispatch(action, payload)`) e lo snapshot JSON dello stato;
  contratto in `android/PORTING.md` e `android/ACTIONS.md`.
- `PlaybackService.kt`: servizio in primo piano con media session, notifica, audio focus, wake lock: la musica
  continua a schermo spento/app chiusa.
- Non toccare né guardare gli altri branch Android (`android`, `android-app`): il lavoro Android attuale è su
  `Android-Sonus`.

## Cose da sapere (decisioni già prese)
- **Avvio**: l'ultima canzone viene mostrata in pausa al suo punto (`Player.restoreSession` → `deferredPosition`),
  senza decodificarla e senza partire; il link YouTube viene cercato in anticipo. Play la carica da quel punto.
  La sessione (`lastQueue`, `lastSongId`, `lastPosition`, volume, modalità) si salva ogni 15 s e a ogni cambio.
- **Memoria**: `PcmStore` tiene in RAM al massimo 8 minuti (2 su Android) a blocchi da 5 s, il resto in
  `TEMP_DIR/pcm/decode_*.pcm`. Dopo 3 minuti di pausa (`IDLE_RELEASE_MS`) l'audio decodificato viene liberato
  (non in una stanza: `player.keepLoaded`). Il video di sfondo si scarica quando è fermo o l'app è ridotta a icona.
- **Velocità d'avvio**: una sola chiamata yt-dlp per canzone (audio + formati video), link riusati fino a 20 minuti
  prima della scadenza (`expire=` nel link), istanze yt-dlp riusate tra i thread, manifest HLS/DASH saltati,
  fade-in 0,25 s.
- **Sincronizza voci**: misura a ritmo (non a reazione) in 3 passi: prova con i propri click, turno di A, turno di B.
  Una voce in chiamata non può arrivare in anticipo, quindi la perfezione è possibile in una sola direzione: si sceglie
  "io sento lui a tempo", "lui sente me a tempo" o "a metà". Il risultato imposta i ritardi personali di entrambi e
  attiva la sincronizzazione precisa (tolleranza 120 ms invece di 700 ms, ping ogni 5 s). Messaggi MQTT `vsync_*`
  sul topic `msg` della stanza.
- Non cambiare il protocollo della stanza (`state`, `presence/…`, `msg`, `files/…`) in modo incompatibile: PC e
  Android di versioni diverse devono continuare a parlarsi.
- Branch: `Android-Sonus` contiene sia le ottimizzazioni PC sia il lavoro Android. I nomi dei branch git non possono
  contenere spazi.

## Cosa resta da verificare
- Build APK e test strumentali: solo in CI (in locale manca l'Android SDK). Prove reali su telefono (audio in
  background, Bluetooth, schermo spento, due persone in chiamata) non ancora fatte.
- Test di integrazione delle stanze con un vero `mosquitto`.
