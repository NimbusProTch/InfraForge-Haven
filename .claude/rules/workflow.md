# Sprint & Task Execution Kuralları

## Araştırma İstendiğinde ("araştır", "deep dive", "kontrol et", "incele")
1. **HER ZAMAN** multi-agent (2-3 Explore agent paralel) çalıştır
2. Agent'lar şunları yapmalı:
   - Agent 1: Live koddaki gerçek durumu satır satır oku (dosya:satır numarası)
   - Agent 2: Best practices / industry standards araştır
   - Agent 3: Güvenlik + yapısal sorunlar tara
3. **Mevcut durum vs best practice** karşılaştırma tablosu oluştur
4. CLAUDE.md'deki "✅ yapıldı" iddialarına güvenme — kodu gerçekten oku
5. "Kod hazır" ≠ "doğru çalışır" — her iddiayı dosyada confirm et
6. İlk seferde TÜM sorunları bul — kullanıcı tekrar hatırlatmak zorunda kalmamalı
7. Plan sadece araştırma SONRASI yazılır

## Sprint Task Sırası (ASLA adım atlama)
Her task için sırayla:
1. Kodu oku + değiştir
2. **TEST YAZ** — rules/testing.md'ye bak, bu adım ATLANAMAZ
3. Lint kontrol (`ruff check . && ruff format --check .`)
4. Commit (test count belirt: "Tests: 1185 → 1192 (+7)")
5. Push + CI izle (self-hosted runner: [self-hosted, haven])
6. CI green olmadan sonraki task'a geçme

## Sprint Bitişinde
- Tüm task'lar + testler tamamlandı
- CI ALL GREEN (tüm workflow'lar)
- PR description'da test count öncesi/sonrası yazılı
- Architect agent review yapıldı (blocking bug yok)
- Tester agent review yapıldı (testler geçti, count artmış)
- docs/sprints/SPRINT_BACKLOG.md güncellendi

## PR Kuralları
- Her PR'da architect + tester agent review ZORUNLU
- Test yazmadan PR açma
- CI red iken merge yasak
- CI red iken sonraki sprint'e geçme
- Kullanıcı hatırlatmak zorunda kalmamalı — bu kurallar otomatik uygulanır
