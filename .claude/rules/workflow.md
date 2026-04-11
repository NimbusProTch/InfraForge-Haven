# Sprint & Task Execution Kuralları

## Araştırma İstendiğinde
"Araştır", "kontrol et", "incele" dendiğinde:
1. Multi-agent (2-3 Explore agent paralel) çalıştır
2. Kodu satır satır oku — CLAUDE.md'ye güvenme
3. Best practices ile karşılaştır
4. Gap raporu ver (dosya:satır ile)
5. Plan sadece araştırma SONRASI yazılır
6. İlk seferde TÜM sorunları bul — kullanıcı tekrar hatırlatmak zorunda kalmamalı

## Sprint Task Sırası
Her task için sırayla:
1. Kodu oku + değiştir
2. Test yaz (bkz: rules/testing.md)
3. Lint kontrol
4. Commit (test count belirt)
5. Push + CI izle
6. CI green olmadan sonraki task'a geçme

## Sprint Bitişinde
- Tüm task'lar + testler tamamlandı
- CI ALL GREEN
- PR description'da test count öncesi/sonrası
- Architect agent review (blocking bug yok)
- SPRINT_BACKLOG.md güncellendi

## PR Kuralları
- Her PR'da architect review zorunlu
- Test yazmadan PR açma
- CI red iken merge yasak
- CI red iken sonraki sprint'e geçme
