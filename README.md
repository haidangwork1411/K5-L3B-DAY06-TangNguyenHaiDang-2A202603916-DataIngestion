# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.

---

## Hướng dẫn thiết lập và tái lập kết quả (Reproducibility Guide)

### 1. Thiết lập môi trường Python
Thực hiện các lệnh sau từ thư mục `starter/`:
```bash
cd starter
python3 -m venv .venv
source .venv/bin/activate
# Trên Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường (`starter/.env`)
Tạo file `.env` từ file mẫu `.env.example`:
```bash
cp .env.example .env
```
Thiết lập các biến môi trường trong `starter/.env`:
- `DATABASE_URL`: Đường dẫn kết nối PostgreSQL local (mặc định dùng cho Docker Compose: `postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab`).
- `GEMINI_API_KEY`: API key cá nhân từ Google AI Studio dùng cho embedding model (không commit file `.env` chứa khóa xác thực).

### 3. Khởi động cơ sở dữ liệu và kiểm tra kết nối
```bash
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```
*Kỳ vọng: Hệ thống báo thông tin phiên bản PostgreSQL, pgvector và thông báo `Setup OK`.*

### 4. Thực thi Pipeline và Đánh giá Benchmark
Từ thư mục `starter/` khi môi trường ảo đã được kích hoạt:
```bash
python -m src.run
```
*Ghi chú về bộ đệm vector: Hệ thống lưu cache vector tại `starter/results/embedding_cache.json`. Các lượt chạy lại với cùng dữ liệu chunk và câu hỏi đã cache sẽ đọc trực tiếp từ tệp này để tránh gọi lại API không cần thiết và tiết kiệm thời gian. Khi có dữ liệu mới hoặc cache miss, hệ thống sẽ thực hiện gọi Gemini API theo hạn mức và biểu phí của nhà cung cấp.*

### 5. Kiểm tra cấu trúc kết quả và báo cáo
- Trace truy xuất top-3: `results/traces_strategy_A.json`, `results/traces_strategy_B.json`, `results/traces_strategy_C.json`
- Tổng hợp chỉ số định lượng: `results/summary_metrics.json`
- Báo cáo cá nhân: `report/individual/2A202603916_TangNguyenHaiDang.md`
- Nhật ký thí nghiệm: `artifacts/experiment_log.csv`
- Dữ liệu manifest: `data/manifest.json`
- Bộ câu hỏi benchmark: `benchmark/questions.json`

