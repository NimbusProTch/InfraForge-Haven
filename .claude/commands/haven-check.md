# /haven-check — Haven 15/15 Compliance Verification

Haven compliance skorunu canlı doğrula. Her maddeyi gerçek kod ve (erişilebilirse) kubectl ile kontrol et.

## 15 Check Listesi

Her check için şu formatı kullan:

| # | Check | Doğrulama Yöntemi | Beklenen | Gerçek | Status |
|---|-------|-------------------|----------|--------|--------|

## Doğrulama Adımları

1. **Kod doğrulama** (her zaman):
   - İlgili dosyaları oku (main.tf, variables.tf, helm-values/, manifests/)
   - Değişkenler doğru set edilmiş mi?
   - Template'ler doğru render ediyor mu?
   - Hardcoded hatalar var mı?

2. **Cluster doğrulama** (kubeconfig erişimi varsa):
   ```bash
   KC=infrastructure/environments/dev/kubeconfig
   # Check 1: Multi-AZ
   kubectl --kubeconfig=$KC get nodes -L topology.kubernetes.io/zone
   # Check 2: Node count
   kubectl --kubeconfig=$KC get nodes
   # Check 3: K8s version
   kubectl --kubeconfig=$KC version
   # Check 4: OIDC
   kubectl --kubeconfig=$KC get pod -n kube-system -l component=kube-apiserver -o yaml | grep oidc
   # ... tüm 15 check
   ```

3. **Rapor:**
   - Skor: X/15
   - Her madde: ✅ PASS / ⚠️ KOD HAZIR / ❌ BROKEN
   - Broken maddeler için: ne yanlış, nasıl düzeltilir
   - Önceki skorla karşılaştırma (CLAUDE.md'deki ile)

## KURALLAR
- CLAUDE.md'deki skora güvenme — kodu oku, varsa cluster'ı kontrol et
- "Kod hazır" ile "canlıda çalışıyor" ayrımını net yap
- Her check için kaynak dosya ve satır numarası ver
