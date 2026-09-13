# ALGO TEAM Engineering Shorts

GitHub Actions ve ElevenLabs kullanarak 9:16 mühendislik Shorts videosu üretir.

## İlk sürüm

- Manuel olarak başlık, Türkçe anlatım metni ve kaynak bağlantısı alır.
- `ELEVENLABS_API_KEY` ile ses üretir.
- `ELEVENLABS_VOICE_ID` verilmemişse daha önce onaylanan Roger sesini (`CwhRBWXzGAHq8TQ4Fs17`) kullanır.
- ElevenLabs karakter zamanlarından senkron altyazı oluşturur.
- 1080x1920 H.264 MP4, ses dosyası, altyazı ve açıklama metnini GitHub Actions artifact'i olarak verir.
- Henüz YouTube'a otomatik yükleme yapmaz; önce üretilen videoyu birlikte onaylayacağız.

## GitHub ayarı

Repository secret:

- `ELEVENLABS_API_KEY` — zorunlu
- `ELEVENLABS_VOICE_ID` — isteğe bağlı; boşsa onaylanan Roger sesi seçilir

Workflow: **Actions > Generate engineering Short > Run workflow**

İlk kurulumda `.github/workflows/first-real-short.yml` yalnızca `master` dalına
eklendiği ilk push'ta çalışır. `github.run_attempt == 1` koruması nedeniyle ücretli
iş yeniden çalıştırılamaz. Sonraki videolar manuel workflow üzerinden üretilir.


## Yerel deneme

FFmpeg ve Python 3.11+ gerekir.

```bash
python -m pip install -r requirements.txt
python src/generate_short.py \
  --title "Yeraltı Madenlerinde Otonom Makineler" \
  --script "Otonom yeraltı makineleri yalnızca operatörü kabinden çıkarmıyor. Aynı zamanda çevrim süresini daha tutarlı hale getiriyor, üretim verisini sürekli topluyor ve riskli bölgelerde insan maruziyetini azaltıyor." \
  --source-url "https://www.algo-team.com" \
  --output-dir output \
  --offline-tone
```

`--offline-tone`, ElevenLabs kotası harcamadan yalnızca video işleme hattını dener.


## RevA pilot (Cat 798 AC)

`Generate RevA engineering Short` restores the selected RevA motion graphics and
approved narration. The episode is fixed: this animation is specific to the diesel-electric
Cat 798 AC explanation, not a renderer for arbitrary news scripts.

- Roger (`CwhRBWXzGAHq8TQ4Fs17`), Multilingual v2; speed 1.00, stability 0.50,
  similarity 0.75, style 0, speaker boost on. The numeric settings are recovered from
  the approved ElevenLabs export filename; matching settings do not guarantee an
  identical new performance.
- Six original 2D scenes, animated wheels/generator/flow/fan, sentence captions and
  the RevA algoTeam outro. Each new recording drives its own scene timing.
- Missing, mismatched or invalid provider alignment stops rendering; it never
  silently substitutes the 50.81-second reference timeline for new speech.
- Narration and timing are uploaded before rendering, so a rendering issue does not
  require another paid request. The render command does not use the API key.
- The API key is available only in the TTS step. No response bodies, request headers,
  environment dumps or arbitrary provider fields are written to logs or artifacts.
- PR CI uses an offline tone. The production workflow runs once when its reviewed
  workflow file reaches master, or on a new manual dispatch. Re-running the same
  Actions run is blocked. The older diagnostic workflows are now manual-only to
  prevent duplicate spending on this merge. Future workflow edits on master can
  create a new paid run; normal code changes do not.
- No YouTube upload or recurring publication is configured.

### Render a saved speech package (no paid request)

Extract the `reva-speech-<run_id>` artifact into `output/`, then run:

```bash
python -m pip install -r requirements.txt
python src/pilot01.py render --output-dir output
```

`--preview-only` on the render command makes a contact sheet without an MP4.

### Reproduce the preferred reference locally

```bash
python src/pilot01.py prepare --reference-audio /path/to/ElevenLabs_pilot01.mp3 --output-dir output-reference
python src/pilot01.py render --output-dir output-reference
```

The audio SHA-256 must match the original export. This is explicitly recorded as
`approved_elevenlabs_reference`, not as a new API call. The original MP3 and video
are not committed to this public repository.

### Fonts and provenance

Bundled Lato fonts are licensed under the SIL Open Font License; see
`assets/fonts/OFL.txt`. The graphics and timing originate from the user-provided
`AlgoTeam_Pilot01_Kurgu_Kaynaklari.zip`. The outro deliberately preserves the
selected RevA icon and adjoining algoTeam text. It is not the separate PNG wordmark.

Technical reference: [Caterpillar 798 AC](https://www.cat.com/en_AU/products/new/equipment/off-highway-trucks/mining-trucks/15970073.html).
API reference: [ElevenLabs speech with timing](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps).
