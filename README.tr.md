<p align="left">
  <a href="./README.md"><img alt="Read in English" src="https://img.shields.io/badge/Language-English-1f6feb?style=for-the-badge"></a>
  <a href="./README.tr.md"><img alt="Türkçe oku" src="https://img.shields.io/badge/Dil-Türkçe-e11d48?style=for-the-badge"></a>
  <a href="./README.ru.md"><img alt="Читать на русском" src="https://img.shields.io/badge/Язык-Русский-6d28d9?style=for-the-badge"></a>
</p>

# r-offcall

> Sınıflar, bölümler, laboratuvarlar ve ofisler için hesapsız, bulutsuz, yerel ağ odaklı görüntülü toplantılar.

**r-offcall**, aynı güvenilir yerel ağı paylaşan kişiler için geliştirilmiş hafif bir toplantı uygulamasıdır. Bir bilgisayar host olur; yakındaki cihazlar onu mDNS ile bulur ve masaüstü uygulamasından ya da modern bir tarayıcıdan katılır. Kamera ve mikrofon trafiği WebRTC üzerinden katılımcılar arasında doğrudan akar; host yalnızca oda durumunu ve bağlantı kurulumunu yönetir.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Platforms" src="https://img.shields.io/badge/Platformlar-macOS%20%7C%20Windows%20%7C%20Linux-111827">
  <img alt="Network" src="https://img.shields.io/badge/Ağ-Yerel%20ağ%20odaklı-0f766e">
  <img alt="Media" src="https://img.shields.io/badge/Medya-WebRTC-ef4444">
</p>

## Neden var?

Üniversiteler, ofisler ve laboratuvarlar kendi ağlarında hızlı toplantı başlatmak isteyebilir: kullanıcı hesabı açmadan, öğrenci verisini üçüncü taraf bir servise taşımadan ve ders sırasında internete bağımlı kalmadan.

r-offcall bu net kullanım alanına odaklanır: **küçük, güvenilir ve aynı ağdaki toplantılar**. Kurumsal yönetim katmanlarından çok hızlı kurulum ve yerel kontrolü önceler.

## Nerede kullanılır?

| Senaryo | Sağladığı fayda |
|---|---|
| Üniversite sınıfı | Öğretmen oda açar; öğrenciler aynı Wi‑Fi üzerinden IP yazmadan katılır. |
| Bölüm veya fakülte toplantısı | Küçük ekipler hesap ya da bulut takvimi olmadan görüşme başlatır. |
| Bilgisayar laboratuvarı / atölye | Katılımcılar kamera, mikrofon ve desteklenen istemcilerde ekran paylaşımı kullanır. |
| İzole kurum ağı | Yerel ağ çalıştığı sürece dış servisler erişilemezken de toplantı yapılabilir. |
| Geçici saha iş birliği | Host şifreli bir oda açar ve aktif oturumdaki katılımcıları yönetir. |

## Özellikler

- **Yerel ağda otomatik keşif:** Host’lar mDNS/Zeroconf ile ilan edilir, masaüstü istemcileri onları bulur.
- **Doğrudan WebRTC medyası:** Ses ve görüntü peer-to-peer gider; host medya aktarmak zorunda değildir.
- **Hesap ve bulut zorunluluğu yok:** Oda, katılımcı ve moderasyon verileri yalnızca çalışan host sürecinde tutulur.
- **Masaüstü uygulaması ve tarayıcı katılımı:** macOS, Windows ve Linux’ta çalışır; tarayıcıdan `http://<host-ip>:7800` adresi kullanılabilir.
- **Basit oda kontrolü:** Şifreli oda, canlı katılımcı listesi, susturma, odadan çıkarma ve aktif host oturumunda engelleme.
- **Sınıf odaklı roller:** Öğretmen/öğrenci rolleri ve isteğe bağlı fakülte bilgisi katılımcıları ayırt etmeyi kolaylaştırır.

## Mimari

```text
                         yerel ağ

              mDNS keşfi + HTTP/WebSocket sinyalleşme
┌───────────────────────────────────────────────────────────────────┐
│ Host bilgisayar                                                    │
│ aiohttp + Socket.IO · oda durumu · host keşfi · port 7800         │
└───────────────────────────────┬───────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
     ┌────▼────┐           ┌────▼────┐           ┌────▼────┐
     │İstemci A│◄─────────►│İstemci B│◄─────────►│İstemci C│
     └─────────┘  WebRTC   └─────────┘  WebRTC   └─────────┘
```

| Trafik | Yol | Açıklama |
|---|---|---|
| Keşif | mDNS / Zeroconf | Çoklu yayın destekleyen aynı ağda host’u bulur. |
| Sinyalleşme | İstemci ↔ host | Oda üyeliği, WebRTC offer/answer, ICE adayları ve moderasyon olayları. |
| Kamera / mikrofon | Katılımcı ↔ katılımcı | Peer-to-peer WebRTC medyası; host olmak medyayı otomatik almaz. |
| Ekran paylaşımı | Katılımcı ↔ katılımcı | Linux Qt6 masaüstü uygulaması ve uyumlu tarayıcılarda desteklenir. |

## Artılar ve eksiler

| Artılar | Eksiler / sınırlar |
|---|---|
| Hesap sistemi, harici SaaS veya bulut medya aktarıcısı gerekmez. | Kimlik sağlayıcısı, SSO, denetim kaydı ve kalıcı kullanıcı yönetimi yoktur. |
| WebRTC medyası peer-to-peer olduğu için host yükü düşüktür. | Mesh WebRTC küçük gruplar içindir; büyük dersler için SFU temelli bir çözüm değildir. |
| mDNS, yakındaki host’u kolayca buldurur. | VLAN, misafir Wi‑Fi izolasyonu, VPN veya multicast engeli keşfi bozabilir. |
| Oda şifresi ve moderasyon hafif bir erişim katmanı sağlar. | Şifreler ve oda durumu host belleğindedir; kurumsal düzeyde erişim kontrolü değildir. |
| Aynı LAN’daki görüşmeler internetsiz çalışabilir. | Google STUN isteğe bağlı yardımcıdır; ağlar arası görüşmeler kapsam dışıdır. |
| Masaüstü arayüzü macOS, Windows ve Linux’ta çalışır. | Linux ekran paylaşımı Qt6 WebEngine ister; gömülü macOS WKWebView `getDisplayMedia` desteklemez. |
| Tarayıcı katılımı kolay paylaşılır. | Bazı tarayıcılar düz HTTP LAN adresinde kamera/mikrofonu engeller; masaüstü uygulaması veya HTTPS gerekir. |

## Güvenlik ve gizlilik sınırı

r-offcall **güvenilir yerel ağlar** içindir; herkese açık ya da güvenilmeyen ağlar için tasarlanmamıştır.

- WebRTC medya aktarımı DTLS-SRTP ile korunur; ancak yerleşik sinyalleşme sunucusunda HTTP kullanılır, TLS/SSO/sertifika yönetimi yoktur.
- Host’a ulaşabilen herkes odaya bağlanmayı deneyebilir. Kurum ağı, oda şifresi ve uygun güvenlik duvarı kuralları kullanın.
- Oda adı, şifre, engel listesi ve üyelik durumu bellektedir. Host yeniden başlarsa silinir.
- Engeller isim temellidir; kişi başka bir görünen adla tekrar katılabilir.
- `7800` portunu doğrudan internete açmayın. TURN, güçlendirilmiş kimlik doğrulama ve üretim operasyon modeli içermez.

Güvenlik problemi bildirmek için [SECURITY.md](./SECURITY.md) dosyasına bakın.

## Gereksinimler ve kurulum

- Python **3.10+**
- Aynı erişilebilir yerel ağdaki cihazlar
- Otomatik keşif için multicast destekli LAN
- Medya yayınlayacak masaüstü istemcilerde kamera/mikrofon izni

```bash
git clone <depo-adresiniz>
cd r-offcall
python -m venv .venv
```

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

| Platform | Çalıştırma | Not |
|---|---|---|
| macOS | `python src/main.py` | İstendiğinde kamera/mikrofon izni verin. Yerleşik WKWebView ekran paylaşımını desteklemez; bunun için uyumlu tarayıcı kullanın. |
| Windows | `python src/main.py` | Windows 10/11 WebView2 sağlamalıdır. Medya reddedilirse Gizlilik ve Güvenlik ayarlarından masaüstü uygulaması erişimini açın. |
| Linux | `python src/main.py` | Gereksinimler Qt6 WebEngine’i kurar. Arayüz açılmazsa dağıtımınızın Qt/XCB çalışma zamanı paketlerini kurun. Ekran paylaşımı desteklenir. |

## İlk toplantı

1. Uygulamayı hedef ağdaki bir bilgisayarda başlatın.
2. Kısa bir beklemeden sonra host bulunamazsa o bilgisayar `7800` portunda host olur.
3. Açılış ekranında izinleri verin, adınızı ve rolünüzü girin.
4. İsteğe bağlı şifreli bir oda oluşturun.
5. Diğer kişiler uygulamayı açarak veya `http://<host-ip>:7800` adresine giderek katılır.

> **Tek bilgisayarda test:** İkinci katılımcı olarak tarayıcı sekmesi kullanın. Birden fazla masaüstü örneği cihaz izinlerini paylaşır ve host portuyla çakışabilir.

## Yapılandırma, doğrulama ve yol haritası

| Öğe | Mevcut davranış |
|---|---|
| Host portu | `7800` — `src/discovery.py` |
| İstemci yerel arayüz portu | `7801`’den başlar; masaüstü sayfasını loopback güvenli bağlamında çalıştırır |
| STUN | `stun.l.google.com:19302` |
| Kalıcılık | Yok; host yeniden başlarsa tüm oda durumu silinir |
| TURN / internet toplantısı | Yok |
| TLS / HTTPS | Yok |

```bash
python scripts/verify.py
```

Komut Python kaynaklarını derler, yerel statik sunucuyu kontrol eder ve Linux Qt ekran-seçim yolunu kamera ya da ekran gerektirmeden test eder.

Kurum ihtiyaçları büyürse sonraki adımlar HTTPS, manuel host adresi, yerel kimlik/SSO, kalıcı politika ve denetim kaydı, TURN/SFU ve imzalı masaüstü paketleri olabilir.

## Katkı ve lisans

Katkı kuralları için [CONTRIBUTING.md](./CONTRIBUTING.md) dosyasına bakın. Henüz açık kaynak lisansı seçilmedi; bir lisans eklenene kadar kod varsayılan olarak **tüm hakları saklıdır** ve sahibinin izni olmadan yeniden kullanılamaz veya dağıtılamaz.
