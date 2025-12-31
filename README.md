# titck-duyurular — RSS oluşturucu

Bu proje T.C. Türkiye İlaç ve Tıbbi Cihaz Kurumu (TİTCK) duyurular sayfasından duyuruları çekip `feed.xml` (RSS 2.0) oluşturan bir betik içerir.

Özet:
- `scripts/generate_feed.py` : Liste sayfasını (varsayılan https://titck.gov.tr/duyuru?page=1) tarar, duyuru sayfalarını çeker ve `feed.xml` oluşturur.
- `.github/workflows/update-feed.yml` : Saatlik olarak betiği çalıştırır ve `feed.xml` değiştiyse commit eder.

Kurulum & Çalıştırma (lokal):
1. Python 3.8+ kurulu olmalı.
2. Sanal ortam oluşturun (önerilir):
   python -m venv .venv
   source .venv/bin/activate   # Linux/Mac
   .venv\Scripts\activate      # Windows
3. Bağımlılıkları yükleyin:
   pip install -r requirements.txt
4. Betiği çalıştırın:
   python scripts/generate_feed.py --url "https://titck.gov.tr/duyuru?page=1" --output feed.xml

GitHub Actions:
- Workflow otomatik olarak `feed.xml`'i oluşturur ve değişiklik varsa repoya commit eder.
- Workflow çalışması için ekstra secret gerekmez; Action otomatik `GITHUB_TOKEN` kullanır.

Notlar:
- Site yapısı değişirse CSS selector'ları güncellemeniz gerekebilir.
- Eğer içerik JavaScript ile yükleniyorsa (AJAX), requests yerine Playwright/Selenium gerekebilir.
- İlk PR/branch oluşturma için repository'nin boş olmaması (en az bir commit) gerekli.

Contributing / Lisans
- İsterseniz ben bu dosyaları bir dalda (add-rss-feed) oluşturup PR açayım — fakat depo şu an boş olduğu için önce bir başlangıç commit'i olmalı. İsterseniz başlangıç commit'ini siz atın veya ben nasıl yapacağınızı adım adım gösteririm.
