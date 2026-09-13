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
