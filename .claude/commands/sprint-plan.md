# /sprint-plan — Sprint Plan Oluştur

Deep dive araştırması SONRASI sprint planı oluştur. 

## ÖN KOŞUL
Bu skill SADECE deep dive yapıldıktan sonra çalıştırılmalı. Eğer mevcut conversation'da deep dive yapılmamışsa, önce /deep-dive çalıştır.

## Akış

1. **Deep dive bulgularını topla:**
   - Bu conversation'daki araştırma sonuçlarını özetle
   - Kritik sorunları, gap'leri, best practice farklarını listele

2. **Sprint'lere böl:**
   - Her sprint max 2-3 gün
   - Öncelik: CRITICAL → HIGH → MEDIUM
   - Bağımlılık sırası: infra → backend → frontend
   - Her sprint sonunda doğrulanabilir çıktı olmalı

3. **Her sprint için:**
   - Task listesi (checkbox format)
   - Değiştirilecek dosyalar (tam yol)
   - Yeni oluşturulacak dosyalar
   - Test planı (ne test edilecek, nasıl)
   - Definition of Done

4. **Plan dosyasına yaz:**
   - `.claude/plans/` altına markdown olarak kaydet
   - Kullanıcıya onay sor

## KURALLAR
- Deep dive olmadan plan yazma — kullanıcı bunu istemez
- Her task'ta dosya yolu ve ne değişeceği net olmalı
- "X yap" gibi vague task'lar yasak — "main.tf:252'deki kubernetes → ${var.keycloak_oidc_client_id} değiştir" gibi spesifik olmalı
- Test planı olmayan sprint plan kabul edilemez
- CLAUDE.md'deki "Zorunlu Kurallar" section'ındaki Definition of Done'a uymalı
