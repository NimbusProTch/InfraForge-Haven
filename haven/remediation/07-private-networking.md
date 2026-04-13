# Remediation #7 — privatenetworking

## Durum: **Investigation needed → potential Sprint H-net-private**

## Haven kriteri (v12.8.0 JSON output'tan alınan resmi ifade)

```json
{
  "Name": "privatenetworking",
  "Label": "Private networking topology",
  "Category": "Infrastructure",
  "Rationale": "Not directly exposing masters or workers to the public internet can increase the security of the cluster.",
  "Result": "NO"
}
```

## Canlı durum (baseline 2026-04-13)

iyziops prod cluster'daki her Hetzner server'ın hem public IPv4 hem public IPv6 adresi var:

```
$ kubectl get nodes -o wide
NAME               STATUS   INTERNAL-IP   EXTERNAL-IP
iyziops-master-0   Ready    10.10.1.10    178.105.13.192   ← public IP
iyziops-master-1   Ready    10.10.1.4     46.225.154.1
iyziops-master-2   Ready    10.10.1.3     178.105.5.156
iyziops-worker-0   Ready    10.10.1.5     178.104.184.163
iyziops-worker-1   Ready    10.10.1.7     178.104.186.15
iyziops-worker-2   Ready    10.10.1.6     178.104.183.210
```

Hetzner firewall her node'u kendi public IPv4'ünden erişilebilir yapıyor (SSH + k8s API + gateway). Private Hetzner Network (10.10.0.0/16) inter-node comm için kullanılıyor ama public interface kapatılmış değil.

## Neden Haven FAIL veriyor

Haven'ın Go kodu büyük ihtimalle her node'un `.status.addresses[]` listesinde `ExternalIP` type'ında entry olup olmadığına bakıyor. Bizde her node'da var. FAIL.

## Fix seçenekleri (trade-off)

### Option A — Hetzner Network-only (public IP removal)

- Her Hetzner server'dan public IP kaldır (`public_net` block'unu `enable_ipv4 = false`)
- Egress için NAT gateway (Hetzner Floating IP + NAT setup) ya da proxy
- Ingress için sadece Hetzner LB public IP'si (zaten var)
- SSH için: bastion host (jump box) veya Hetzner Console

**Artı**: Gerçek private cluster. Haven check PASS.
**Eksi**: NAT gateway complexity, egress maliyeti, operational overhead (SSH bastion)

### Option B — RKE2 `--node-ip` lockdown + firewall tightening

- RKE2 cloud-init'te `--node-ip=10.10.1.X` ekle (kubelet sadece private IP report etsin)
- Hetzner firewall'da tüm public inbound'ları kapat (hatta SSH bile)
- `ExternalIP` status'u kaldırılır çünkü kubelet private-only report ediyor
- SSH erişimi: Tailscale mesh VPN ya da Hetzner Cloud Console

**Artı**: Network topology değişmez, sadece K8s perspektifi. Daha az complexity.
**Eksi**: Tailscale/VPN setup zorunlu, operator onboarding gerekli.

### Option C — ACCEPT with documented justification

- Hetzner firewall'da operator_cidrs dışında her şey kapalı (halihazırda)
- Public IP expose ama sadece belirli CIDR'lere açık
- Haven check FAIL dönüyor ama compensating control var
- Bu geçici kabul yapılabilir, enterprise audit için dokümantasyon yeterli

**Artı**: Sıfır ek iş, mevcut state korunur.
**Eksi**: Pure Haven compliance achieved değil, skor 13/15'te takılı kalır.

## Tavsiye edilen yol

**Option B (kısa vade) + Option A (Phase 2)**:
1. Bu sprint sonrası **investigation sprint** aç: `privatenetworking` Haven CLI kodunu oku, exact check logic'ini netleştir
2. Option B'yi prototipleyin: `--node-ip` flag + Tailscale
3. Gerçek Haven check pass ediyor mu doğrula
4. Tailscale yoksa Option C ile kal, Phase 2 Cyso Cloud migration'da Option A'ya geç

## Sprint tahmini

- Kod okuma + kesin check logic: 0.25 sprint
- Option B prototype: 0.5 sprint
- Tailscale setup + operator docs: 0.5 sprint
- Haven check doğrulama: 0.25 sprint
- **Toplam: ~1.5 sprint** (Tailscale deploy yoksa +0.5)

## Bu plan kapsamı dışı

Bu sprint sadece `make haven` altyapısı + baseline run'ı kapsıyor. Private networking fix ayrı sprint'te gelecek.

## İlgili Haven kodu

Kaynak kod kontrolü için:
- https://gitlab.com/commonground/haven/haven/-/tree/main/haven/cli/pkg
- `privatenetworking` check implementation
