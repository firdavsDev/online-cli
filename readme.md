## 📋 V1 Python-based Ngrok Alternative – Requirements

### 1. Umumiy maqsad

* Ishxonadagi developerlar localda ishlatayotgan web app’larini (frontend/backend) tezkor tarzda **publik URL** orqali boshqalarga ko‘rsatishlari kerak.
* Ngrok o‘rniga o‘zimizning ichki, oddiyroq tunneling servis bo‘ladi.
* Loyiha nomi: **online** (CLI command ham shu bo‘ladi).

---

### 2. Arxitektura

* **Server (public serverda ishlaydi)**

  * Bitta umumiy `online-server` app bo‘ladi.
  * Developer clientlari shu serverga ulanadi.
  * Server har bir client uchun **unikal port** ochib beradi (`http://SERVER_IP:5001`, `http://SERVER_IP:5002`, ...).
  * So‘rovlarni clientga forward qiladi.

* **Client CLI (developer localda ishlatadi)**

  * Terminaldan ishlatiladi:

    ```bash
    online --port 3000
    ```
  * Server bilan persistent ulanish qiladi.
  * Serverdan kelgan so‘rovlarni `localhost:3000` ga yuboradi va javobni qaytaradi.
  * Developerga ochilgan public URL ni chiqarib beradi.

---

### 3. Foydalanish ssenariysi

1. Admin **server.py** ni ishxonadagi public serverda run qiladi:

   ```bash
   python server.py
   ```

   → server `ws://0.0.0.0:8765` da kutadi.

2. Developer localda o‘z projectini ishga tushiradi (`http://localhost:3000`).

3. Developer terminaldan:

   ```bash
   pip install -e .

   online --port 3000
   ```

   → server bilan ulanadi, tunneling ochiladi.

4. Developerga **public link** chiqadi:

   ```
   ✅ Tunnel opened: http://SERVER_IP:5001
   ```

   → Boss yoki hamkasblar shu linkni browserda ochib ko‘rishi mumkin.

---

### 4. Minimal Functional Requirements

* [x] CLI orqali `--port` flagini qabul qilish.
* [x] Server bilan persistent ulanish (WebSocket).
* [x] Server har bir client uchun **public port** assign qiladi.
* [x] Trafikni client → local server → client → server → tashqi user oqimida forward qilish.
* [x] Multiple clients qo‘llab-quvvatlashi (bir nechta dev parallel ishlata oladi).
* [x] Error handling (agar local port ishlamasa → “Local server error” qaytarish).

---

### 5. Non-functional Requirements

* Oddiy va sodda arxitektura (ko‘p config kerak emas).
* Python 3.9+ ishlaydi.
* Asosiy kutubxonalar:

  * `websockets` (server-client communication)
  * `aiohttp` (local HTTP forward qilish uchun)
  * `argparse` (CLI uchun)
* Domain hozircha yo‘q → faqat `SERVER_IP:PORT` formatida ishlaydi.
* SSL/HTTPS yo‘q (faqat HTTP).

---
