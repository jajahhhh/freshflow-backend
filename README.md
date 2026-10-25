# FreshFlow Backend — คู่มือทำงานใน VS Code

โปรเจกต์ต้นแบบของ Student 2 สำหรับนำเข้า inventory, เรียกดูสต็อกต้นวันแยกตามสาขา, รับผลพยากรณ์, ทดสอบอากาศจำลอง และบันทึกคำแนะนำพร้อมหลักฐานข้อมูลที่ใช้ คำสั่งและการตั้งค่า VS Code เตรียมไว้ในโฟลเดอร์นี้แล้ว

สถานะที่เตรียมให้บนเครื่องนี้: เปิดโฟลเดอร์ใน VS Code แล้ว ติดตั้ง Python environment แล้ว และตั้งค่า `.env` ให้ใช้ **MySQL 8.4 ที่ 127.0.0.1:3307** ผ่าน Docker Desktop พร้อมข้อมูลอ้างอิง 128 snapshots และ mock integration data

การเปิดโฟลเดอร์หรือเตรียมข้อมูลไม่ได้เริ่ม API อัตโนมัติ เมื่อต้องการเริ่มระบบ ให้กด **F5 → FreshFlow: Debug API** รอข้อความ **Application startup complete** และ **Uvicorn running on http://127.0.0.1:8000** ใน terminal แล้วจึงเปิด `http://127.0.0.1:8000/docs` ใช้ admin key จาก `.env` ในปุ่ม Authorize ต้องเปิดเซสชันเซิร์ฟเวอร์นั้นค้างไว้ระหว่างใช้งาน หากระบบรันอยู่แล้วไม่ต้องเปิดซ้ำ

มี `.env.sqlite` เก็บค่าฐานข้อมูล SQLite สำหรับทดลองแบบ offline หากต้องการสลับกลับ ให้หยุด API แล้วคัดลอก `.env.sqlite` เป็น `.env` ไฟล์ทั้งสองมีข้อมูลลับและถูกเว้นไว้ใน Git แล้ว คู่มือด้านล่างครอบคลุมการติดตั้งใหม่และการเลือกฐานข้อมูลทั้งสองแบบ

## 1. เปิดโฟลเดอร์นี้ใน VS Code

1. เปิด **Visual Studio Code**
2. เลือก **File → Open Folder…**
3. เลือกโฟลเดอร์ `freshflow-backend` ที่มี README นี้ ไม่เลือกโฟลเดอร์แม่
4. ไปที่ **Extensions** ติดตั้ง **Python** และ **Python Debugger** ของ Microsoft
5. ติดตั้ง **REST Client** ของ Huachao Mao หากต้องการกดส่ง request จาก `requests.http` โดยตรง การทดลองผ่านหน้า `/docs` ไม่ต้องใช้ extension นี้
6. เปิด **Terminal → New Terminal** terminal ควรอยู่ในโฟลเดอร์ `freshflow-backend`

ตัวอย่างในคู่มือนี้ใช้ macOS และ Python 3.11 ขึ้นไป VS Code และ Python ต้องติดตั้งอยู่บนเครื่องก่อน ส่วน Docker ใช้เฉพาะเมื่อเลือก MySQL

บนเครื่องที่จัดเตรียมงานนี้ ตรวจพบแอป VS Code ใน Desktop พร้อม Microsoft Python extensions และเปิดโฟลเดอร์โปรเจกต์ให้แล้ว ขั้นตอนทั่วไปด้านบนยังใช้สำหรับเปิดงานอีกครั้งหรือย้ายไปเครื่องเพื่อน

## 2. เตรียม Python และค่าตั้งต้น

ถ้ามี `.venv` ที่เตรียมและติดตั้งแพ็กเกจให้แล้ว ให้ใช้ environment เดิม ไม่ต้องสร้างใหม่ ตรวจเวอร์ชัน Python ก่อน:

```bash
python3 --version
```

หากยังไม่มี environment ให้สร้างและติดตั้ง:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
```

`requirements.lock.txt` บันทึกเวอร์ชัน dependencies ที่ติดตั้งและใช้ทดสอบไว้ ให้ใช้ไฟล์นี้เมื่อต้องการติดตั้งรุ่นเดียวกัน ส่วน `requirements.txt` ระบุช่วงเวอร์ชันสำหรับการอัปเดต dependencies ในภายหลัง

กด **Command + Shift + P → Python: Select Interpreter → Enter interpreter path…** แล้วเลือก `.venv/bin/python` ของโปรเจกต์นี้ สถานะแถบล่างควรแสดง environment `.venv`

โปรเจกต์ที่จัดเตรียมให้นี้ใช้ `.env` สำหรับ MySQL มี `.env.mysql` สำหรับ Docker และ `.env.sqlite` สำหรับสลับกลับไปใช้ SQLite ไฟล์เหล่านี้เว้นไว้ใน `.gitignore` ให้ใช้ไฟล์เดิมโดยไม่แทนที่ด้วย template ตัวอย่างด้านล่างใช้เฉพาะการติดตั้งใหม่ที่เลือก SQLite ไม่ต้องเปลี่ยน DATABASE_URL ของเครื่องที่ตั้งค่า MySQL แล้ว:

```dotenv
DATABASE_URL=sqlite:///./freshflow.db
ADMIN_API_KEY=your_local_admin_key
STAFF_API_KEY=your_local_staff_key
SERVICE_API_KEY=your_local_service_key
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

ข้อความ `your_local_...` ด้านบนเป็นตัวอย่าง ไม่ใช่ key ที่ใช้กับระบบ หากยังไม่มี `.env`:

```bash
cp .env.example .env
```

จากนั้นเปลี่ยน API key ทั้งสามให้เป็นคนละค่าและคาดเดาได้ยาก อย่าใช้ข้อความ `replace_with_...` ใน template เป็น key จริง สามารถสร้างค่าใหม่ทีละค่าด้วย:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

คัดลอกค่าเข้า `.env` บนเครื่อง ไม่ใส่ key จริงใน README, `requests.http`, ภาพหน้าจอ หรือ Git ไฟล์ `.env` และฐานข้อมูล local ถูกเว้นไว้ใน `.gitignore` แล้ว

**API key ในต้นแบบนี้เป็นสิทธิ์ระดับบทบาทสำหรับการทดสอบ** ยังไม่ใช่บัญชีผู้ใช้รายบุคคล ไม่มี login, การจำกัด staff รายสาขา, การเปลี่ยนรหัสผ่าน หรือการเพิกถอน session สำหรับการใช้งานจริง

## 3. สร้างฐานข้อมูล นำเข้า และเติมข้อมูล demo

ไฟล์ `data/inventory_mock_2026-10-12.csv` เป็นสำเนาข้อมูลอ้างอิงสำหรับนำเข้า อย่าแก้ไฟล์ต้นฉบับใน `sources/` ของ ChatGPT project

รันทีละคำสั่งใน terminal ของ VS Code:

```bash
source .venv/bin/activate
python -m app.cli init-db
python -m app.cli import-csv data/inventory_mock_2026-10-12.csv
python -m app.cli seed-demo --date 2026-10-12
python -m app.cli verify-data
```

ความหมายของแต่ละคำสั่ง:

| คำสั่ง | สิ่งที่ทำ |
|---|---|
| `init-db` | สร้างตารางที่ยังไม่มีตาม schema ของแอป |
| `import-csv` | ตรวจข้อมูลและนำเข้า snapshot พร้อมประวัติไฟล์ |
| `seed-demo` | สร้างผลพยากรณ์และอากาศ **จำลอง** สำหรับทดสอบ |
| `verify-data` | ตรวจยอดข้อมูลจริงที่นำเข้ากับค่าที่คาดหวังของ CSV นี้ |

`init-db` ไม่ใช่เครื่องมือ migration ถ้าเปลี่ยนชนิดคอลัมน์หรือตารางเดิม ต้องทำ migration แยกสำหรับฐานข้อมูลที่มีข้อมูลแล้ว

อีกวิธีคือกด **Command + Shift + P → Tasks: Run Task → FreshFlow: Prepare demo** ซึ่งทำสี่ขั้นนี้ตามลำดับ ดูผลแต่ละขั้นใน terminal

เมื่อใช้ CSV ต้นฉบับ ค่าที่ตรวจสอบควรเป็น:

| รายการ | จำนวน |
|---|---:|
| วันที่ข้อมูล | 2026-10-12 |
| Inventory snapshots | 128 |
| สาขา | 4 |
| รหัสสินค้าที่ไม่ซ้ำ | 32 |
| สต็อกต้นวันรวม | 3,103 หน่วย |
| รายการสต็อกเป็นศูนย์ | 2 |
| รายการเหลืออายุ 0–2 วันและสต็อกมากกว่า 0 | 70 |

`seed-demo` เตรียม baseline prediction **3 หน่วยต่อวันเท่ากันทุกสินค้าและสาขา** สำหรับวันที่ 12 และ 13 ตุลาคม พร้อม weather สองสถานการณ์ `clear-demo` กับ `rain-demo` แยกตามสาขาและวัน และสร้าง recommendation runs 8 ชุด: 2 สถานการณ์ × 4 สาขา ชื่อสินค้า หมวด ราคา และ barcode ยังคงเป็น `null` ข้อมูลจำลองเหล่านี้สร้างสำหรับทดสอบ ไม่ได้มาจาก CSV หรือจากโมเดลที่ train แล้ว และไม่ใช่อากาศจริงของวันนั้น

## 4. เปิด API หรือ Debug ใน VS Code

**วิธีเปิด API ปกติ:**

กด **Command + Shift + P → Tasks: Run Task → FreshFlow: Run API** หรือรัน:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

รอข้อความ **Application startup complete** และ **Uvicorn running on http://127.0.0.1:8000** ก่อนเปิดหน้าเว็บ เก็บ terminal นี้ให้ทำงานต่อระหว่างใช้งาน API หยุดด้วย **Control + C** ใน terminal นั้น หากหน้าเว็บขึ้น **ERR_CONNECTION_REFUSED** ให้ตรวจว่าเซิร์ฟเวอร์เริ่มสำเร็จและยังไม่ถูกหยุด สำหรับ MySQL ต้องเปิด Docker Desktop และฐานข้อมูลด้วย

**วิธี Debug:**

1. เปิดไฟล์ Python ที่ต้องการตรวจ
2. กดตรงขอบซ้ายของบรรทัดเพื่อใส่ breakpoint
3. ไปที่ **Run and Debug** ทางซ้าย
4. เลือก **FreshFlow: Debug API**
5. กด **F5**
6. ส่ง request จาก Swagger หรือ `requests.http` โปรแกรมจะหยุดที่ breakpoint เมื่อ request วิ่งผ่านบรรทัดนั้น
7. ดูค่าใน **Variables** หรือเลื่อนเมาส์เหนือชื่อตัวแปร
8. กด **F10** เพื่อข้ามทีละบรรทัด หรือ **F5** เพื่อทำงานต่อ

Debug configuration ไม่เปิด auto reload เพื่อให้ breakpoint ติดตาม process เดียวได้ง่าย หยุด server เดิมก่อนเปิด Debug เพื่อไม่ให้ชน port 8000

## 5. ทดลองผ่าน Swagger ทีละขั้น

เปิด [Swagger UI](http://127.0.0.1:8000/docs) ขณะ server ทำงาน

1. เปิด `GET /health` → **Try it out → Execute** endpoint นี้ไม่ต้องใส่ key
2. กด **Authorize** มุมขวาบน
3. คัดลอก `ADMIN_API_KEY` จาก `.env` เข้าแบบฟอร์ม API key แล้วกด **Authorize** ใส่เฉพาะค่า key ไม่เติมคำว่า `Bearer`
4. ลองอ่าน inventory ตามตัวอย่างด้านล่าง
5. เมื่อต้องทดสอบ staff หรือ service ให้เปลี่ยนค่าที่ Authorize เป็น key บทบาทนั้น

อ่านข้อมูลทุกสาขา:

```text
GET /api/v1/inventory?date=2026-10-12&limit=200&offset=0
```

อ่านเฉพาะสาขา:

```text
GET /api/v1/inventory?date=2026-10-12&store_id=STORE_01&limit=200
```

กรองใกล้หมดอายุ:

```text
GET /api/v1/inventory?date=2026-10-12&max_days=2&in_stock_only=true&limit=200
```

`max_days=2` หมายถึง 0 ≤ days ≤ 2 รายการหมดอายุแล้วที่มีค่าติดลบไม่อยู่ในตัวกรองนี้ ไม่ใส่ `max_days` หากต้องการอ่าน snapshot โดยไม่ใช้ตัวกรองอายุ

วันที่ `2026-10-12` เป็นวันธุรกิจของ snapshot ไม่ใช่วันปัจจุบัน เปลี่ยนเป็นวันอื่นที่ไม่มีข้อมูลแล้วได้รายการว่างเป็นพฤติกรรมที่ถูกต้อง อย่าแก้ให้ระบบหยิบข้อมูลเก่ามาแสดงโดยไม่ระบุวัน

## 6. ทดลองนำเข้าไฟล์ผ่าน API

ใน Swagger เลือก `POST /api/v1/inventory/imports`:

1. Authorize ด้วย admin key
2. ตั้ง `dry_run=true`
3. เลือก `data/inventory_mock_2026-10-12.csv`
4. กด Execute และดูผล validation
5. เปลี่ยน `dry_run=false` เมื่อต้องการบันทึก

นโยบายการนำเข้า:

- ไฟล์เดิมที่เคยนำเข้าสำเร็จไม่สร้าง snapshots ซ้ำ
- key ของ snapshot คือวันที่ + สาขา + สินค้า
- key เดิมและค่าตรงกันข้ามได้ ส่วน key เดิมแต่ค่าต่างกันเป็น conflict
- แถวผิดต้องรายงานข้อผิดพลาด และไม่บันทึกไฟล์บางส่วนเงียบ ๆ
- `2.0` ในช่องจำนวนวันแปลงเป็น 2 ได้ แต่ `2.5` ไม่ควรถูกตัดเศษทิ้ง
- รหัสสินค้าและสาขาเก็บเป็นข้อความ

ตรวจ response และ HTTP status จาก Swagger เสมอ รูปแบบ schema ใน `/docs` มาจากแอปที่กำลังรัน จึงเป็นแหล่งอ้างอิงที่ตรงกับเวอร์ชันโค้ดปัจจุบัน

## 7. ทดลองสร้าง recommendation แบบครบสาขา

หลัง `seed-demo` สำเร็จ เปิด `POST /api/v1/recommendation-runs` แล้วส่งด้วย admin หรือ staff key:

```json
{
  "request_id": "demo-store01-20261012-rain-v1",
  "snapshot_date": "2026-10-12",
  "store_id": "STORE_01",
  "scenario_id": "rain-demo",
  "rule_version": "rules_v1",
  "prediction_source": "MOCK"
}
```

response มี `run_id`, `total_items`, `ready_count`, `not_ready_count` และ `review_count` เก็บ `run_id` ไว้อ่านผล:

```text
GET /api/v1/recommendation-runs/{run_id}
GET /api/v1/recommendations?date=2026-10-12&store_id=STORE_01
```

ผลต่อ snapshot ประกอบด้วยรายการ `actions`, สถานะการประมวลผล และสถานะการอนุมัติ:

| ฟิลด์/ค่า | ความหมาย |
|---|---|
| `READY` | มีข้อมูลพอประมวลผลตามกฎ |
| `DATA_NOT_READY` | ข้อมูลที่จำเป็นไม่ครบ ต้องดูเหตุผล |
| `REVIEW_REQUIRED` | ต้องตรวจนโยบาย เช่น สินค้าหมดอายุวันนี้ |
| `approval_status=PROPOSED` | ยังไม่มีการอนุมัติ |
| `APPROVED` / `REJECTED` | ผลการตัดสินใจของผู้มีสิทธิ์ |

อย่าตีความ `DATA_NOT_READY` เป็น `NO_ACTION` และอย่าแทน forecast ที่หายไปด้วยศูนย์

ลองเปรียบเทียบอากาศโดยสร้าง run อีกอัน ใช้ `request_id` ใหม่และ `scenario_id="clear-demo"` ข้อมูล snapshot เดิมแต่ input อากาศต่างกันจะตรวจผลของกฎได้

`request_id` ใช้ป้องกันการสร้างงานซ้ำ ส่ง ID เดิมกับ payload เดิมคืนรายการเดิม หากต้องการทดลอง input ใหม่ให้ใช้ ID ใหม่ ห้ามใช้ ID เดิมแทนข้อมูลคนละชุด

กฎ demo ใช้ baseline sales proxy และปรับอากาศตามกฎสมมติ ยังไม่มีการประเมินประสิทธิภาพการขายจริง การเติมสินค้าพิจารณาวันที่สินค้ามาถึงตาม lead time จึงไม่อ้างว่าการสั่งวันนี้แก้ของขาดก่อนสินค้ามาถึงได้

## 8. ทดลองส่ง ML และ weather เอง

ไฟล์ `requests.http` มี request เรียงตามลำดับ รวม forecast วันที่ D และ D+1, weather และการประมวลผล:

1. ติดตั้ง REST Client แล้วเปิดไฟล์
2. คัดลอกไฟล์เป็น `requests.local.http` ในโฟลเดอร์เดิมก่อนใส่ key จริง ไฟล์ชื่อนี้เว้นไว้ใน `.gitignore` แล้ว
3. ใส่ `adminKey`, `staffKey`, `serviceKey` ของเครื่อง
4. กด **Send Request** เหนือ request ที่จะทดลอง
5. อ่าน response ด้านขวา

ตัวอย่าง manual เตรียม forecast ให้เพียง `PROD_001` และใช้อากาศชื่อ `manual-rain-demo` ส่วน `seed-demo` ใช้ทดสอบครบทุกสินค้าได้ ค่าพยากรณ์และอากาศใน request เป็น mock ที่ระบุไว้ชัดเจน

ML contract ต้องระบุอย่างน้อย:

```json
{
  "request_id": "ml-store01-prod001-20261012-v1",
  "store_id": "STORE_01",
  "product_id": "PROD_001",
  "target_date": "2026-10-12",
  "predicted_units": 3.0,
  "prediction_kind": "BASELINE_SALES_PROXY",
  "model_version": "example_v1",
  "source": "MOCK",
  "contains_weather_effect": false
}
```

ใช้ `source="ML_MODEL"` เมื่อเป็นผลจากโมเดลจริง API รุ่นนี้รับเฉพาะ baseline ที่ `contains_weather_effect=false` และปฏิเสธผลที่รวมอากาศมาแล้ว เพื่อไม่ปรับอากาศซ้ำ ผลต้องตรงสินค้า สาขา วันที่ และหน่วย Forecast หลายวันที่ใช้คำนวณต้องไม่มีวันขาด

สำหรับ run ที่เลือก `prediction_source="ML_MODEL"` ระบบเลือกเฉพาะผลที่มี `input_cutoff_at` และ cutoff นั้นต้องอยู่ **ก่อน 00:00 ของวันที่ snapshot ของ run ตามเขตเวลาสาขา** เงื่อนไขนี้ใช้กับ forecast ทุกวันที่นำมาคำนวณ รวม D+1 ด้วย เช่น run วันที่ 12 ตุลาคม เวลา Bangkok ต้องใช้ข้อมูลตัดก่อนเริ่มวันที่ 12 ตุลาคม แม้ forecast จะเป็นของวันที่ 13 ตุลาคม ควรส่ง `input_cutoff_at` เป็น ISO 8601 พร้อม offset เช่น `2026-10-11T23:59:00+07:00` ผล `MOCK` ยกเว้นเงื่อนไข cutoff นี้และระบุแหล่งข้อมูลจำลองชัดเจน

`generated_at` คือเวลารับผลเข้าระบบ ไม่ใช่หลักฐานว่าโมเดลสร้างผลก่อนวันตัดสินใจ การรับ ML ย้อนหลังจึงเป็นการประมวลผลย้อนหลังตามข้อมูลที่ผู้ส่งระบุ ยังไม่ยืนยันว่าเป็น backtest ที่ควบคุมข้อมูลรั่วไหล หรือยืนยันแหล่งข้อมูลฝึกโมเดลแล้ว การตรวจสอบเหล่านี้ต้องทำในงาน ML เพิ่มเติม

## 9. รายการ API และสิทธิ์ของต้นแบบ

ใช้ header `X-API-Key` สำหรับ endpoint ภายใน

| API | งาน | สิทธิ์หลัก |
|---|---|---|
| `GET /health` | ตรวจ API/ฐานข้อมูล | สาธารณะ |
| `POST /api/v1/inventory/imports` | นำเข้า CSV | Admin |
| `GET /api/v1/inventory` | ค้น snapshot | บทบาทภายใน |
| `GET /api/v1/inventory/summary` | สรุปสต็อก | บทบาทภายใน |
| `GET /api/v1/stores` | รายชื่อสาขา | บทบาทภายใน |
| `GET /api/v1/products` | รายการสินค้า | บทบาทภายใน |
| `PATCH /api/v1/products/{product_id}` | ปรับ product master | Admin |
| `POST /api/v1/predictions` | รับผลพยากรณ์ | Admin / Service |
| `GET /api/v1/predictions` | อ่านผลพยากรณ์ | บทบาทภายใน |
| `POST /api/v1/weather/mock` | เพิ่มอากาศ mock | Admin / Service |
| `GET /api/v1/weather` | อ่านอากาศ | บทบาทภายใน |
| `POST /api/v1/recommendation-runs` | สร้างคำแนะนำ | Admin / Staff |
| `GET /api/v1/recommendation-runs/{id}` | ดู run | บทบาทภายใน |
| `GET /api/v1/recommendations` | อ่านคำแนะนำ | บทบาทภายใน |
| `PATCH /api/v1/recommendations/{id}/status` | อนุมัติ/ปฏิเสธ | Admin |
| `GET /api/v1/dashboard/summary` | Dashboard | บทบาทภายใน |
| `GET /api/v1/deals` | อ่านดีลที่ผ่านเงื่อนไข | สาธารณะ |
| `GET /api/v1/notifications` | แจ้งเตือนในระบบ | บทบาทภายใน |
| `PATCH /api/v1/notifications/{id}/read` | อ่านแล้ว | บทบาทภายใน |

Admin ในต้นแบบใช้แทนการอนุมัติของ manager การระบุตัวผู้อนุมัติรายบุคคลและการจำกัดสาขาต้องเพิ่มในระบบ login ภายหลัง การแจ้งเตือนที่สร้างเป็นรายการในฐานข้อมูล ไม่ส่ง email หรือ push ไปยังบุคคลภายนอก

CSV ไม่มีชื่อสินค้า หมวดหมู่ ราคา หรือ barcode ตาราง product จึงเก็บเป็น `null` จนมีข้อมูล mapping ที่ยืนยันได้ สินค้าไม่มีราคาต้องไม่แสดงราคาลดที่แต่งขึ้น หากต้องทดสอบดีลด้วยราคาจำลอง ให้ติดป้ายว่าเป็นสินค้าทดลองและแยกจากข้อมูล master จริง

Dashboard และ Deals เลือก run ล่าสุดของแต่ละสาขาและวันที่ เพื่อไม่รวมคำแนะนำซ้ำจากการรันใหม่หรือหลาย scenario ถ้าสร้าง run ใหม่ ผลจาก run เก่าอาจไม่อยู่ในหน้ารวมอีกต่อไป Dashboard ระบุ `run_id` เพื่อดู run ใดโดยเฉพาะได้

`GET /api/v1/deals` ที่ไม่ระบุ `date` ใช้วันที่ปัจจุบัน ไม่หยิบ CSV วัน demo มาอ้างว่าเป็นดีลวันนี้ หากต้องดูตัวอย่างย้อนหลังให้ระบุ `?date=2026-10-12` response จะมี `historical_preview` ตามวันที่ที่ขอและ `prototype_only=true` เสมอ ข้อมูล CSV ของงานนี้คงวันที่ `2026-10-12` และ product metadata ยังว่าง ดังนั้นหน้า deals ว่างก่อนเพิ่มข้อมูลและอนุมัติตามเงื่อนไขถือว่าถูกต้อง

## 10. โครงสร้างข้อมูลและ flow ที่ใช้จริง

```text
CSV → ตรวจข้อมูล → ประวัติ import + inventory snapshots
                                    │
Prediction (ML หรือ MOCK) ───────────┤
Weather mock แยก scenario/วัน/สาขา ───┤
                                    ↓
                    ตรวจวันที่/หน่วย/ความครบถ้วน
                                    ↓
                       Recommendation Engine
                                    ↓
           เก็บ run + input ที่ใช้ + actions + เหตุผล
                                    ↓
                    Approval → Dashboard / Deals
```

ข้อมูลสำคัญที่แยกจัดเก็บ:

- **Stores / Products:** ข้อมูล master ไม่มีการเดาชื่อหรือหมวดจากเลขรหัส
- **Import jobs / Inventory snapshots:** แหล่งไฟล์และสต็อกต้นวัน ใช้ unique key วันที่ + สาขา + สินค้า
- **Predictions:** ผลรายสาขา สินค้า วันที่ รุ่นโมเดล และแหล่งข้อมูล
- **Weather:** วัน สาขา scenario และแหล่ง mock
- **Recommendation runs / Recommendations:** รุ่นกฎ หลักฐาน input สถานะ และการอนุมัติ
- **Notifications:** รายการแจ้งเตือนภายในและสถานะอ่าน

ค่า `is_mock` ของคำแนะนำเป็น `true` หาก snapshot, prediction หรือ weather ที่ใช้มีแหล่งจำลอง แม้ส่ง prediction จาก ML จริง แต่ inventory ยังมาจาก CSV mock ผลรวมก็ยังเป็น mock การแจ้งเตือนและสถานะอ่านในต้นแบบใช้ร่วมกันตามบทบาท ยังไม่ได้แยกเป็นบัญชีและสถานะอ่านรายผู้ใช้

ดู schema ที่ใช้งานจาก model ของแอป เปลี่ยนแปลง schema ด้วย migration เมื่อต้องเก็บฐานข้อมูลเดิมต่อ

## 11. เปลี่ยนไปใช้ MySQL 8.4

ทำหลังจาก demo SQLite ทำงานแล้ว และหยุด API ก่อนเปลี่ยนฐานข้อมูล

1. ติดตั้งและเปิด Docker Desktop
2. ใช้ `.env.mysql` ที่จัดเตรียมไว้ หากติดตั้งใหม่และยังไม่มีไฟล์นี้จึงคัดลอก template:

   ```bash
   cp .env.mysql.example .env.mysql
   ```

3. ใช้ `MYSQL_PASSWORD` กับ `MYSQL_ROOT_PASSWORD` ที่สร้างไว้ หากเริ่มจาก template ให้ตั้งรหัสผ่านสองค่าให้ต่างกัน
4. ตรวจว่ารหัสผ่านใน `DATABASE_URL` ตรงกับ `MYSQL_PASSWORD` หากมีอักขระพิเศษ เช่น `@`, `:` หรือ `/` ต้อง percent-encode ส่วนรหัสผ่านใน URL
5. ใช้ API keys ที่เตรียมไว้ใน `.env.mysql` หากเริ่มจาก template ให้แทนค่า placeholder ด้วย keys ของ local demo
6. เปิดฐานข้อมูล:

   ```bash
   docker compose --env-file .env.mysql up -d db
   docker compose --env-file .env.mysql ps
   docker compose --env-file .env.mysql logs db
   ```

7. รอฐานข้อมูลพร้อมใช้งาน แล้วสำรอง `.env` เดิมไว้บนเครื่องและเปลี่ยน `.env` ให้มี `DATABASE_URL` กับ API keys/CORS จาก `.env.mysql` อย่า commit ไฟล์สำรองที่มี keys
8. รัน `init-db`, `import-csv`, `seed-demo`, `verify-data` ใหม่ตามขั้น 3
9. เปิด API และรันทดสอบการอ่านข้อมูลอีกครั้ง

`127.0.0.1:3307` คือ port ของ MySQL ที่เครื่องใช้เชื่อม ส่วน `3306` คือ port ภายใน container ไม่ต้องติดตั้ง MySQL server ซ้ำบนเครื่อง

ข้อมูล SQLite ไม่ย้ายเข้า MySQL อัตโนมัติ คำสั่งด้านบนสร้างฐานข้อมูลใหม่จาก CSV และ mock data อีกครั้ง MySQL เก็บข้อมูลใน volume `mysql_data` การเปลี่ยน password ใน env ไม่ได้แก้บัญชีเดิมใน volume ที่สร้างแล้ว หลีกเลี่ยงการลบ volume ที่มีข้อมูลซึ่งยังต้องใช้

## 12. ทดสอบใน VS Code

รันทดสอบใน terminal:

```bash
python -m pytest -q
```

หรือ **Tasks: Run Task → FreshFlow: Run tests** หรือกดไอคอน **Testing** ทางซ้ายแล้วเลือก Run Tests

ตรวจชุดทดสอบรอบส่งมอบด้วย `python -m pytest -q` แล้วผ่านครบ รันคำสั่งเดิมอีกครั้งหลังแก้โค้ดหรือเปลี่ยน dependencies เพราะจำนวนกรณีทดสอบอาจเพิ่มขึ้นได้

ควรตรวจอย่างน้อย:

- CSV จริงได้ 128 แถว และยอดรวมตรงค่าที่ตรวจสอบไว้
- นำเข้าซ้ำไม่สร้างข้อมูลซ้ำ และ conflict ไม่บันทึกไฟล์บางส่วน
- แถว stock ติดลบ ค่าว่าง key ซ้ำ และจำนวนวันมีเศษถูกจัดการ
- ไม่ปะปนสินค้าคนละสาขาหรือ prediction คนละวัน
- ข้อมูล forecast/weather ไม่ครบได้สถานะไม่พร้อม
- expiry เท่ากับ 0 เข้ากรณีตรวจนโยบาย
- การเติมใช้วันมาถึง ไม่ backorder ยอดขายที่เสียไปเอง
- request ID ป้องกันสร้าง run ซ้ำ
- staff/service เขียนข้อมูลที่ไม่มีสิทธิ์ไม่ได้
- ดีลไม่มีราคา หรือยังไม่ได้อนุมัติ ไม่ถูกเผยแพร่เป็นดีลพร้อมราคา

ผลจากการทดสอบ SQLite ยังไม่ยืนยันความเข้ากันได้ทุกกรณีกับ MySQL ควรทดสอบ integration บน MySQL ของทีมก่อนส่งมอบ ใช้ฐานข้อมูลทดสอบแยกจากฐาน demo เมื่อต้องล้างข้อมูล

## 13. เชื่อม Flutter และ Dashboard

แจ้งเพื่อน frontend ว่า:

```text
Base URL: http://127.0.0.1:8000
Swagger:  http://127.0.0.1:8000/docs
Demo date: 2026-10-12
Demo store: STORE_01
Header for internal demo: X-API-Key
```

อย่าใส่ admin key หรือ service key ในแอปที่แจกให้ลูกค้า สำหรับการเชื่อมบนเครื่องทดสอบแบบควบคุม staff key เป็นเพียงกลไก demo ก่อนแทนด้วย token รายผู้ใช้

Flutter Web ต้องใช้ origin ที่ตรงกับ `CORS_ORIGINS` รวม port หากเปิดเว็บคนละ port ให้เพิ่ม origin ของเว็บใน `.env` แล้ว restart Backend

Android Emulator มาตรฐานเข้าถึงเครื่องพัฒนาที่ `http://10.0.2.2:8000` ส่วนมือถือจริงต้องใช้ IP ภายในของเครื่องพัฒนาในเครือข่ายเดียวกันและเปิด API รับเครือข่ายตามความเหมาะสม การเปิด server ภายนอกเครื่องควรทำหลังตรวจสิทธิ์และการตั้งค่าแล้ว

Frontend ต้องแสดง “สต็อกต้นวัน” และวันที่ snapshot รวมทั้งสถานะ mock ให้ชัดเจน ค่า `null` ไม่เท่ากับศูนย์ และรายการว่างของวันที่ไม่มีข้อมูลไม่ใช่ server ล้มเหลว

## 14. หากเปิดไม่ได้ให้ตรวจตามอาการ

| อาการ | สิ่งที่ตรวจ |
|---|---|
| ไม่พบ `fastapi` หรือ `sqlalchemy` | เลือก interpreter `.venv/bin/python` แล้วติดตั้ง requirements ใน environment นี้ |
| ไม่พบ `.env` หรือใช้ฐานข้อมูลผิด | เปิดโฟลเดอร์ `freshflow-backend` เป็น workspace และรันจากโฟลเดอร์นี้ |
| API key ถูกปฏิเสธ | ใช้ค่าจาก `.env` ที่ server อ่านอยู่ ใส่ header `X-API-Key` แล้ว restart เมื่อแก้ค่า |
| `Address already in use` | หยุด server เดิมก่อนกด F5 หรือ Run task |
| inventory ว่าง | ตรวจว่านำเข้าแล้ว วันที่เป็น `2026-10-12` และใช้ฐานข้อมูลเดียวกับที่นำเข้า |
| `DATA_NOT_READY` | ดู reason ตรวจ prediction และ weather ให้ครบวันที่และ scenario |
| MySQL เชื่อมไม่ได้ | ดู container status/logs รอพร้อม ตรวจ port และ username/password |
| เว็บ frontend ถูก CORS ปฏิเสธ | เพิ่ม origin รวม scheme และ port ให้ตรงใน `.env` |
| Debug ไม่หยุด breakpoint | เปิดด้วย Debug configuration และส่ง request ที่วิ่งผ่านโค้ดนั้นจริง |

## 15. สิ่งที่ต้องทำต่อเมื่อจะใช้เป็นระบบจริง

ต้นแบบนี้ยังไม่มี live POS, stock movements, batch/lot, อากาศจากผู้ให้บริการจริง, โมเดลที่ train แล้ว, ระบบส่ง push/email, หรือระบบบัญชีผู้ใช้รายบุคคล ข้อมูลจำลองและกฎตัวอย่างช่วยพิสูจน์การเชื่อมระบบ ไม่ใช่หลักฐานการลดของเสียหรือเพิ่มกำไรจริง

ลำดับงานต่อของ Student 2:

1. ทำ product master mapping ที่มีแหล่งข้อมูลยืนยันได้
2. ตกลง ML contract และแทน mock ด้วยผลโมเดลจริง
3. เพิ่มพิกัดสาขาและบริการ weather โดยรักษาวันอ้างอิงให้ตรง
4. ยืนยันกฎนับวันขาย วันหมดอายุ และ lead time กับทีม
5. เพิ่ม authentication รายผู้ใช้และสิทธิ์รายสาขา
6. เพิ่ม batch และ movement หากต้องแสดงสต็อกปัจจุบัน
7. ทำ migration และทดสอบ MySQL ครบ flow
8. จัดทำ ER diagram, data dictionary, API contract, rule specification และผลทดสอบสำหรับ thesis
