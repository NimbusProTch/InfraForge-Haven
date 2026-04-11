# /sprint — Sprint Execution Checklist

Her sprint task'ı için bu checklist ZORUNLU. Adım atlamak yasak.

## Her Task İçin (sırayla)

### 1. Kod Yaz
- [ ] Mevcut kodu oku (dosya + satır numarası)
- [ ] Değişikliği yap
- [ ] Lint kontrol: `ruff check . && ruff format --check .` (Python) veya `npm run lint` (UI)

### 2. Test Yaz (ZORUNLU — ATLAMA!)
- [ ] Mevcut ilgili testleri bul (`grep -r "test.*{değişen_fonksiyon}" tests/`)
- [ ] Yeni test yaz — değişikliğin doğruluğunu kanıtlayan test
- [ ] Test FAIL etmeli (kodu geri al → test fail → kodu geri koy → test pass)
- [ ] Test count artmalı (öncesi vs sonrası)

### 3. Testleri Çalıştır
- [ ] `pytest tests/ -q` — tüm testler geçmeli
- [ ] Yeni testler geçmeli
- [ ] Eski testler kırılmamış olmalı

### 4. Commit
- [ ] Commit mesajında: ne değişti + hangi testler eklendi
- [ ] Test count belirt: "Tests: 1185 → 1192 (+7)"

### 5. Push + CI
- [ ] Push et
- [ ] CI pipeline'ı izle — ALL GREEN olmalı
- [ ] Fail varsa → düzelt → tekrar push

## Sprint Bitişinde
- [ ] Tüm task'lar tamamlandı
- [ ] Test count artmış (sprint başı vs sprint sonu)
- [ ] CI ALL GREEN
- [ ] PR description'da test count yazılı
- [ ] Architect agent review (blocking bug yok)

## KURALLAR
- Test yazmadan commit YAPMA
- Test yazmadan PR AÇMA
- Test yazmadan "sprint bitti" DEME
- CI red iken Sprint 3'e GEÇME
- Kullanıcı hatırlatmak zorunda kalmamalı — bu checklist otomatik uygulanır
