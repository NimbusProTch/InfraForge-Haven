# /deep-dive — Multi-Agent Deep Dive Research

Kullanıcı bir konuyu araştırmamı istiyor. ASLA yüzeysel plan yazma. Önce gerçek durumu anla.

## Zorunlu Akış

1. **3 Explore agent paralel başlat:**
   - Agent 1: Live koddaki gerçek durumu satır satır oku (dosya yolları + satır numaraları)
   - Agent 2: Best practices / industry standards araştır (web search + bilgi)
   - Agent 3: Güvenlik + yapısal sorunlar tara (cross-reference, bağımlılıklar, edge case'ler)

2. **Gap Analizi Raporu oluştur:**
   - Live durum vs Best practice karşılaştırma tablosu
   - Tüm sorunlar listesi (severity: CRITICAL / HIGH / MEDIUM / LOW)
   - Her sorun için: dosya yolu, satır numarası, ne yanlış, ne olmalı
   - Öneriler (actionable, somut)

3. **KURALLAR:**
   - CLAUDE.md'deki "✅ yapıldı" iddialarına güvenme — kodu oku
   - "Kod hazır" ≠ "doğru çalışır" — her iddiayı dosyada confirm et
   - İlk seferde TÜM sorunları bul — kullanıcı tekrar "bak bir daha" demek zorunda kalmamalı
   - Hardcoded değerler, TODO/FIXME, race condition, quorum riski gibi şeyleri ara
   - Rapor formatı net ve scannable olsun

4. **ASLA plan yazma bu aşamada.** Sadece araştırma raporu ver. Plan ayrı bir adım.

## Kullanım
```
/deep-dive kyverno multi-tenancy
/deep-dive infra haven compliance
/deep-dive build pipeline security
```

Argüman olarak verilen konu hakkında yukarıdaki akışı uygula. Argüman yoksa kullanıcıya sor.
