---
paths:
  - "api/**"
  - "ui/**"
---

# Test Yazma Kuralı (İhlal Edilemez)

Kod değişikliği yapıldığında test yazmadan commit YASAK.

## Neden?
Bu proje 342 Hollandalı belediyeye hizmet veren multi-tenant PaaS. Testler güvenlik ağı — 
test olmadan deploy edilen bir bug tüm belediyeler etkilenir.

## Akış
1. Kod değiştir
2. Mevcut testlerin geçtiğini doğrula
3. Değişiklik için YENİ test yaz
4. Test count artmalı — artmadıysa commit yapma
5. Commit mesajında test count belirt: "Tests: 1185 → 1192 (+7)"

## Konum
- Backend testleri: `api/tests/test_{module}.py`
- Frontend testleri: `ui/__tests__/` veya component yanında
- Playwright E2E: `tests/`
- Test çalıştırma: `cd api && pytest tests/ -q`
- Lint: `cd api && ruff check . && ruff format --check .`

## Test Yoksa
- Commit yapma
- PR açma
- Sprint bitti deme
- "Sonra yazarız" deme — test şimdi yazılır
