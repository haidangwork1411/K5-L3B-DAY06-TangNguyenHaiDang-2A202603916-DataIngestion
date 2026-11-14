# Báo cáo cá nhân — Day 6

**Học viên:** Tăng Nguyễn Hải Đăng  
**MSSV:** 2A202603916  
**Lớp:** K5-L3B  
**Kho lưu trữ:** `K5-L3B-DAY06-TangNguyenHaiDang-2A202603916-DataIngestion`  

---

## Dữ liệu và pipeline

### 1. Chủ đề, nguồn/quyền, số trang và quy tắc tính trang
- **Chủ đề tài liệu:** Báo cáo kinh tế vĩ mô và giáo dục đại học Việt Nam: *"Báo cáo Điểm lại, Tháng 8 năm 2022: Giáo dục để tăng trưởng (Taking Stock, August 2022: Educate to Grow)"* do Ngân hàng Thế giới (The World Bank) phát hành.
- **Nguồn & Bản quyền:** 
  - Nguồn truy cập trực tiếp: World Bank Open Knowledge Repository ([Handle 10986/37834](https://openknowledge.worldbank.org/handle/10986/37834)).
  - Bản quyền: Giấy phép mở quốc tế **Creative Commons Attribution 3.0 IGO (CC BY 3.0 IGO)**. Được phép trích dẫn, sao chép, phân phối và khai thác cho mục đích nghiên cứu, học tập kèm trích dẫn nguồn đầy đủ.
- **Quy tắc tính trang và số trang nội dung hữu ích:**
  - File PDF gốc gồm 68 trang vật lý (đánh chỉ số 1–68).
  - Quy tắc phân loại trang được ghi nhận chi tiết tại `data/manifest.json`: Loại trừ **16 trang không chứa nội dung phân tích**, gồm:
    - Bìa trước (trang 1) và bìa sau (trang 68).
    - Thông tin xuất bản, bản quyền (trang 2), trang tiêu đề lặp lại (trang 3), các trang trắng kỹ thuật (trang 4, 66, 67).
    - Mục lục và danh mục bảng biểu (trang 5, 6, 7).
    - Danh mục từ viết tắt (trang 8) và Lời cảm ơn (trang 9).
    - Các trang bìa lót ngăn cách chương chỉ chứa hình ảnh lớn (trang 10, 18, 44).
    - Tài liệu tham khảo (trang 65).
  - **Số trang nội dung hữu ích giữ lại:** **52 trang** (trang 11–17, 19–43, 45–64).
  - Phân bố theo 4 phần: `tong_quan` (7 trang: 11–17), `kinh_te_vi_mo` (28 trang: 19–43, 45–47), `giao_duc_dai_hoc` (16 trang: 48–63), `phu_luc` (1 trang: 64).

### 2. Chuẩn hóa, lỗi và giới hạn
- **Phương pháp đọc và chuẩn hóa:** Sử dụng thư viện `pypdf` để đọc nội dung từng trang và trích xuất chỉ số trang vật lý. Văn bản được chuẩn hóa Unicode theo định dạng NFKC, xử lý khoảng trắng thừa và dấu xuống dòng ngắt giữa từ. Tiêu đề đầu trang lặp lại (*"GIÁO DỤC ĐỂ TĂNG TRƯỞNG"*) và số trang in được loại bỏ để tránh gây nhiễu cho mô hình embedding.
- **Lỗi và giới hạn gặp phải:**
  - Các trang chứa bảng biểu hoặc biểu đồ phức tạp (ví dụ trang 20, 27) có phần chú thích (*"Nguồn: TCTK...", "Ghi chú: LLLĐ..."*) nằm xen kẽ vào luồng văn bản chính khi trích xuất text thuần. Các đoạn chú thích này có mật độ từ khóa kinh tế dày đặc, khiến mô hình embedding có xu hướng cho điểm tương đồng ngữ nghĩa cao hơn thực tế, làm giảm thứ hạng của đoạn văn phân tích cốt lõi (chi tiết được phân tích ở câu `q06`).

### 3. Embedding model, Vector store, Metric, Lệnh chạy và Chi phí
- **Embedding Model:** Google Gemini `gemini-embedding-001` (qua API Google Generative AI), số chiều vector: **768 dimensions**.
- **Vector Store:** **PostgreSQL 16 + pgvector 0.8.7** triển khai qua Docker Compose local (`127.0.0.1:55433`, database: `day6_lab`, bảng: `chunks`).
- **Chỉ mục tìm kiếm:** HNSW index với phép đo Cosine Distance (`vector_cosine_ops`), kết hợp chỉ mục GIN trên trường `metadata` kiểu `JSONB`.
- **Metric tính độ tương đồng:** Cosine Similarity: `score = 1 - (embedding <=> query_vector)`.
- **Lệnh thực thi pipeline:**
  ```bash
  cd starter
  python -m src.run
  ```
- **Chi phí & Lượt gọi API:**
  - Hệ thống tích hợp cơ chế lưu đệm vector (`PersistentCachedEmbedder` lưu tại `starter/results/embedding_cache.json`).
  - Toàn bộ ứng dụng ghi nhận tổng cộng **40 lượt gọi API** (`total_api_calls_made = 40` trong `results/summary_metrics.json`), với phân bổ chính xác như sau:
    + **Strategy A:** **10 lượt gọi batch** để embedding 230 chunks tài liệu (kích thước batch = 25 chunks).
    + **Strategy B:** **10 lượt gọi batch** để embedding 231 chunks tài liệu (kích thước batch = 25 chunks).
    + **Strategy C:** **0 lượt gọi** (tái sử dụng 100% vector chunks từ Strategy B).
    + **Bộ câu hỏi benchmark:** **20 lượt gọi riêng lẻ** cho 20 câu hỏi (`q01`–`q20`), vector được lưu đệm và dùng chung cho cả 3 chiến lược.
    + Tổng cộng có **481 vector 768 chiều** (230 A + 231 B + 20 query) được tạo và lưu đệm bền vững.
  - Về chi phí: Đợt thực nghiệm chạy trong định mức miễn phí của Google AI Studio (Free Tier), không ghi nhận phát sinh chi phí trên tài khoản. Khi chạy lại pipeline với cùng tập dữ liệu, hệ thống đọc trực tiếp từ bộ đệm trên đĩa giúp tiết kiệm quota. Khi áp dụng cho dữ liệu mới hoặc xóa cache, số lượt gọi và chi phí sẽ phụ thuộc vào biểu phí hiện hành của nhà cung cấp API.

### 4. Metadata bắt buộc và trường lọc bổ sung
- **Metadata bắt buộc:** `document_id` (`worldbank-vietnam-taking-stock-aug-2022`), `source` (tên tài liệu nguồn), `page` (chỉ số trang vật lý 11–64).
- **Trường lọc bổ sung (`section`):** Phân chia theo 4 khối nội dung chính: `tong_quan`, `kinh_te_vi_mo`, `giao_duc_dai_hoc`, `phu_luc`.
- **Lý do chọn:** Tài liệu gồm hai phần chuyên đề độc lập (tình hình kinh tế vĩ mô và giáo dục đại học). Trường `section` phản ánh ranh giới chủ đề tự nhiên, cho phép thu hẹp không gian tìm kiếm thông qua mệnh đề SQL `WHERE`, loại bỏ các đoạn văn nhiễu ở các chương không liên quan trước khi tính khoảng cách vector.

---

## Cấu hình và benchmark

### 1. Cấu hình ba chiến lược (A / B / C)
- **Strategy A (Fixed-size Chunking):** 
  - Phương pháp: Chia cửa sổ ký tự cố định `fixed_size`.
  - Tham số: `chunk_size = 800` ký tự, `overlap = 100` ký tự.
  - Lọc metadata: Không (`filter = none`).
  - Giả thuyết: Cửa sổ kích thước đồng đều kết hợp overlap 100 ký tự giúp giảm nguy cơ mất thông tin tại ranh giới cắt, nhưng có thể cắt ngang giữa câu hoặc làm rời rạc các ý trọn vẹn.
- **Strategy B (Paragraph Chunking):** 
  - Phương pháp: Phân đoạn theo đoạn văn `by_paragraph`.
  - Tham số: `max_size = 1000` ký tự, `overlap = 0`.
  - Lọc metadata: Không (`filter = none`).
  - Giả thuyết: Phân đoạn theo ranh giới đoạn văn tự nhiên giúp bảo toàn ngữ cảnh và tính mạch lạc của câu văn, giúp mô hình ngôn ngữ hiểu trọn vẹn ý của tác giả.
- **Strategy C (Paragraph Chunking + Metadata Filter):** 
  - Phương pháp: Tái sử dụng chính xác tập chunks và vector embeddings của **Strategy B** (`by_paragraph`, `max_size=1000`, `overlap=0`).
  - Lọc metadata: Áp dụng bộ lọc theo chuyên mục (`filter = section`).
  - **Khác biệt duy nhất B–C:** Strategy C kích hoạt điều kiện lọc trong truy vấn SQL (`WHERE metadata->>'section' = %s`) cho các câu hỏi có chỉ định filter. Strategy C không tạo thêm bảng hay vector mới trong cơ sở dữ liệu và không phát sinh lượt gọi API nào (thời gian nạp bổ sung = 0.00s).
  - Giả thuyết: Việc kết hợp phân đoạn theo đoạn văn với bộ lọc metadata sẽ thu hẹp phạm vi tìm kiếm, loại bỏ chunk gây nhiễu từ các chương khác và cải thiện độ chính xác ở Rank 1.

### 2. Bộ câu hỏi Benchmark và kiểm chứng Evidence
- Gồm **20 câu hỏi** được xây dựng trực tiếp từ 52 trang nội dung hữu ích, lưu tại `benchmark/questions.json`.
- Phân chia tập dữ liệu trước khi chạy thử nghiệm: **15 câu Dev** (`q01`–`q15`) và **5 câu Test độc lập (Hold-out)** (`q16`–`q20`).
- Phân loại câu hỏi:
  - 12 câu hỏi trực tiếp (`truc_tiep`): Tra cứu các dữ kiện, chỉ số kinh tế tường minh.
  - 5 câu hỏi diễn đạt lại (`dien_dat_lai`): Thay đổi cấu trúc diễn đạt và từ đồng nghĩa nhằm kiểm tra khả năng khớp ngữ nghĩa của vector embedding.
  - 3 câu hỏi điều kiện/ngoại lệ (`dieu_kien`): Đòi hỏi truy xuất đúng ngữ cảnh phạm vi hoặc điều kiện kèm theo.
- **Câu hỏi có Metadata Filter:** Gồm **5 câu** có gán metadata filter (chiếm 25%), gồm 3 câu trong tập Dev (`q05`, `q10`, `q14`) và 2 câu trong tập Test (`q18`, `q20`).
- **Kiểm chứng Evidence:** Mỗi câu hỏi đều được xác minh trực tiếp trên văn bản PDF gốc, đối chiếu đúng `gold_page` và trích dẫn nguyên văn `evidence_quote` trước khi tiến hành benchmark.

### 3. Tiêu chí chọn chiến lược theo quy trình phân tách Dev/Test
Theo thiết kế thử nghiệm độc lập, các tiêu chí lựa chọn chiến lược được xác lập dựa trên kết quả của tập Development (15 câu `dev`) và mẫu kiểm toán Coherence ban đầu, trước khi mở tập Test holdout (5 câu `test`):
1. **Tiêu chí 1 (Bắt buộc):** Evidence Hit@3 trên tập Dev phải đạt tối thiểu 90% (đảm bảo đoạn bằng chứng luôn xuất hiện trong top-3 để cung cấp ngữ cảnh cho mô hình tạo sinh).
2. **Tiêu chí 2 (Độ chính xác Rank 1):** Ưu tiên cấu hình có Hit@1 trên tập Dev cao hơn để xếp bằng chứng phù hợp lên vị trí đầu tiên.
3. **Tiêu chí 3 (Tính mạch lạc của Chunk):** Điểm Coherence trung bình trên tập mẫu ban đầu phải đạt mức hiểu được trọn vẹn (≥ 1.5/2.0), tránh cắt vụn câu chữ gây ảnh hưởng xấu tới khâu suy luận.
4. **Tiêu chí 4 (Chi phí và Khả năng triển khai):** Tiết kiệm số lượt gọi API và thời gian nạp dữ liệu.

---

## Kết quả

### Bảng 1: Chỉ số định lượng truy xuất và tài nguyên

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian nạp | Chi phí & Lượt gọi API |
|---|---|---|---|---|---|---|
| **Strategy A** | Dev | 11/15 (73.33%) | 15/15 (100.0%) | 230 | 225.17s | 0 USD (10 batch calls tài liệu) |
| Strategy A | Test | 4/5 (80.00%) | 5/5 (100.0%) | 230 | — | Đọc từ cache |
| Strategy A | **All** | **15/20 (75.00%)** | **20/20 (100.0%)** | **230** | **225.17s** | **Free Tier (10 doc calls + chia sẻ 20 query calls)** |
| **Strategy B** | Dev | 8/15 (53.33%) | 15/15 (100.0%) | 231 | 228.42s | 0 USD (10 batch calls tài liệu) |
| Strategy B | Test | 5/5 (100.0%) | 5/5 (100.0%) | 231 | — | Đọc từ cache |
| Strategy B | **All** | **13/20 (65.00%)** | **20/20 (100.0%)** | **231** | **228.42s** | **Free Tier (10 doc calls + chia sẻ 20 query calls)** |
| **Strategy C** | Dev | 9/15 (60.00%) | 15/15 (100.0%) | 231 | 0.00s *(tái sử dụng B)* | 0 USD (0 calls, tái sử dụng vector B) |
| Strategy C | Test | 5/5 (100.0%) | 5/5 (100.0%) | 231 | — | Đọc từ cache |
| Strategy C | **All** | **14/20 (70.00%)** | **20/20 (100.0%)** | **231** | **0.00s** | **0 USD (0 calls tài liệu + chia sẻ 20 query calls)** |

*(Ghi chú: Toàn bộ pipeline ghi nhận 40 lượt gọi API thực tế = 10 batch A + 10 batch B + 20 queries dùng chung, tương ứng 481 embeddings được lưu trong cache)*.

### Bảng 2: Đánh giá chất lượng và kiểm toán 5 khía cạnh

| Strategy | Coherence trung bình /2 (n=10) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 (n=5) |
|---|---|---|---|---|
| **Strategy A** | **0.70 / 2.0** (n=10) | 15/15 (100.0%) | N/A *(không dùng filter)* | Mức 0: 0, Mức 1: 0, Mức 2: 5 câu — **TB: 2.0 / 2.0** |
| **Strategy B** | **1.80 / 2.0** (n=10) | 15/15 (100.0%) | N/A *(không dùng filter)* | Mức 0: 0, Mức 1: 0, Mức 2: 5 câu — **TB: 2.0 / 2.0** |
| **Strategy C** | **1.80 / 2.0** (n=10) | 15/15 (100.0%) | **2/2 (100.0%)** | Mức 0: 0, Mức 1: 0, Mức 2: 5 câu — **TB: 2.0 / 2.0** |

---

### Đường dẫn minh chứng, Nhãn kiểm toán và Phương pháp chọn mẫu

- **Đường dẫn tệp kết quả và trace thực nghiệm:**
  - Traces chi tiết: `results/traces_strategy_A.json`, `results/traces_strategy_B.json`, `results/traces_strategy_C.json`.
  - Tóm tắt chỉ số định lượng: `results/summary_metrics.json`.
  - Nhật ký thí nghiệm: `artifacts/experiment_log.csv`.
  - Bộ đệm vector: `starter/results/embedding_cache.json` (481 vector 768 chiều).

#### 1. Mẫu đánh giá Chunk Coherence (10 vị trí chunk đầu trang)
- **Cách chọn mẫu:** Chọn chunk đầu tiên của 10 trang nội dung đầu tiên đã sắp xếp theo thứ tự trang vật lý: Trang 11, 12, 13, 14, 15, 16, 17, 19, 20, 21.
- **Thang điểm tham chiếu theo GUIDE:** 0 = cắt đứt giữa từ/ngang ý, thiếu chủ thể; 1 = hiểu một phần, thiếu ngữ cảnh trước/sau; 2 = tự hiểu được và bảo toàn trọn vẹn ý đoạn văn.
- **Xác nhận của học viên:** Học viên đã đối chiếu trực tiếp văn bản trích xuất từ PostgreSQL (bảng `chunks`) của toàn bộ 10 vị trí mẫu (Trang 11–21) với thang điểm của GUIDE và xác nhận các nhãn Coherence trong bảng dưới đây phản ánh chính xác tính mạch lạc thực tế của các chunk.

| Vị trí | Chunk Strategy A (Fixed 800) | Điểm A | Nhận xét mẫu Strategy A | Chunk Strategy B & C (Paragraph 1000) | Điểm B/C | Nhận xét mẫu Strategy B/C |
|:---:|---|:---:|---|---|:---:|---|
| **Trang 11** | `..._p11_f001` (800c) | **0** | Cắt đứt giữa từ: `...dự báo c` | `..._p11_b001` (1000c) | **1** | Cắt ở giới hạn 1000c: `...Trung Quốc d` |
| **Trang 12** | `..._p12_f001` (800c) | **1** | Cắt dở câu tiếp theo: `...Chính sách tiền tệ tiếp tụ` | `..._p12_b001` (773c) | **2** | Trọn vẹn đoạn văn: kết thúc ở `...Nhân dân tệ.` |
| **Trang 13** | `..._p13_f001` (800c) | **1** | Cắt giữa cụm số liệu: `...thặng dư nhỏ (0,2` | `..._p13_b001` (920c) | **2** | Trọn vẹn đoạn văn: kết thúc ở `...nguồn kiều hối dồi dào.` |
| **Trang 14** | `..._p14_f001` (800c) | **0** | Cắt đứt giữa từ: `...sẵn sàng chuy` | `..._p14_b001` (396c) | **2** | Trọn vẹn đoạn văn: kết thúc ở `...mục tiêu như hiện nay.` |
| **Trang 15** | `..._p15_f001` (800c) | **0** | Cắt đứt giữa từ: `...sự khác biệ` | `..._p15_b001` (514c) | **2** | Trọn vẹn đoạn văn: kết thúc ở `...kỹ năng cần thiết cho người dân.` |
| **Trang 16** | `..._p16_f001` (800c) | **0** | Cắt đứt giữa từ: `...quốc gia khá` | `..._p16_b001` (520c) | **2** | Trọn vẹn đoạn văn: kết thúc ở `...(ngoài CNTT - 68%).` |
| **Trang 17** | `..._p17_f001` (739c) | **2** | Trang ngắn, chunk trọn trang: `...thông tin hiện đại.` | `..._p17_b001` (739c) | **2** | Trọn vẹn đoạn văn kết thúc trang. |
| **Trang 19** | `..._p19_f001` (799c) | **1** | Cắt dở câu: `...kinh tế toàn cầu năm 2022 hiện` | `..._p19_b001` (999c) | **1** | Đoạn dài hơn 1000c, cắt dở ở `...euro trong năm` |
| **Trang 20** | `..._p20_f001` (800c) | **1** | Cắt dở chú thích hình: `...Hình 1.1... Phần A: 2021-` | `..._p20_b001` (740c) | **2** | Trọn vẹn đoạn văn: `...mức trước đại dịch.` |
| **Trang 21** | `..._p21_f001` (799c) | **1** | Cắt dở câu: `...tuy vẫn thấp hơn so với tốc` | `..._p21_b001` (683c) | **2** | Trọn vẹn đoạn phân tích: `...tại Trung Quốc.` |
| **Tổng / TB**| *Tổng điểm: 7 / 20* | **0.70** | *6/10 chunk bị đứt từ ngữ hoặc câu dở dang* | *Tổng điểm: 18 / 20* | **1.80** | *8/10 chunk hoàn chỉnh cấu trúc đoạn văn* |



#### 2. Kiểm toán Metadata Usefulness trên 5 câu Test (5 câu × Top-3 = 15 bản ghi)
- **Độ chính xác và đầy đủ (`source`, `page`, `section`):** 15/15 bản ghi (100.0%) của cả ba chiến lược đều ghi nhận đúng `document_id`, số trang vật lý nằm trong dải [11, 64] và gắn đúng `section` thực tế.
- **Tuân thủ bộ lọc (Filter compliance) trên các câu có filter trong tập Test:**
  - Tập Test có 2 câu yêu cầu lọc: `q18` (`section = 'kinh_te_vi_mo'`) và `q20` (`section = 'phu_luc'`).
  - **Strategy A & B:** Không áp dụng filter. Ở câu `q20`, kết quả top-3 bị lọt chunk từ chương giáo dục đại học (trang 51): Strategy B bị lọt ở **Rank 2** (chunk `..._p51_b004`), còn Strategy A bị lọt ở **Rank 3** (chunk `..._p51_f004`).
  - **Strategy C:** Tuân thủ **2/2 câu** (100.0%). Ở câu `q20`, toàn bộ 3/3 hits trong top-3 đều thuộc đúng phân đoạn `phu_luc` (trang 64).

#### 3. Đánh giá Grounding Quality trên 5 câu Test (Thang 0–2)
- **Thang điểm tham chiếu theo GUIDE:** 0 = không có bằng chứng; 1 = có bằng chứng nhưng thiếu ngữ cảnh hoặc điều kiện kèm theo; 2 = đầy đủ dữ kiện để trả lời và có thể truy ngược nguồn.
- **Xác nhận của học viên từ đối chiếu trace và tài liệu:**
  - **Câu q16 (Trang 15):** Cả A, B, C đều có Rank 1 chứa đoạn `...số năm đi học bình quân của Việt Nam là 10,2 năm, chỉ đứng sau Sing-ga-po trong Hiệp hội các Quốc gia Đông Nam Á (ASEAN)...` -> **Mức 2** (đủ dữ kiện số năm và thứ hạng, kèm số trang 15 để kiểm chứng).
  - **Câu q17 (Trang 24):** 
    - Strategy A: Rank 1 rơi vào trang 11 không có tỷ lệ khảo sát; tuy nhiên Rank 2 ở trang 24 chứa nguyên văn: `...Cứ năm doanh nghiệp được phỏng vấn thì có một doanh nghiệp cho biết đã tuyển dụng lao động mới trong quý I/2022...` -> Top-3 có bằng chứng đầy đủ: **Mức 2**.
    - Strategy B & C: Chunk ở trang 24 được xếp ở Rank 1 với ngữ cảnh trọn vẹn -> **Mức 2**.
  - **Câu q18 (Trang 43):** Cả A, B, C đều có Rank 1 chứa nguyên văn: `...Biện pháp hỗ trợ này có tổng quy mô 40 nghìn tỷ đồng (tương đương 1,7 tỷ USD hay 0,5% GDP) và sẽ có hiệu lực đến cuối năm 2023...` -> **Mức 2**.
  - **Câu q19 (Trang 61):** Cả A, B, C đều có Rank 1 chứa nguyên văn: `...có hai bộ khác nhau (Bộ Giáo dục và Đào tạo và Bộ Lao động, Thương binh và Xã hội) phụ trách quản lý nhà nước đối với giáo dục đại học và đào tạo nghề...` -> **Mức 2**.
  - **Câu q20 (Trang 64):** Cả A, B, C đều có Rank 1 chứa nguyên văn: `...Tại Hàn Quốc, 70% người dân ở độ tuổi từ 24 đến 35 đã hoàn thành chương trình giáo dục bậc cao...` -> **Mức 2**.
- **Tổng kết:** Trên 5 câu tập Test, học viên xác nhận cả ba chiến lược đều cung cấp bằng chứng đủ để trả lời trong top-3 (Mức 2, điểm trung bình: **2.0 / 2.0**).

---

## Phân tích và kết luận

### 1. So sánh chi tiết A–B và B–C
- **So sánh A–B (Tác động của phương pháp Chunking):**
  - **Tài nguyên và lưu trữ:** Strategy A (230 chunks, 225.17s) và Strategy B (231 chunks, 228.42s) có số lượng chunk và thời gian tạo embedding xấp xỉ nhau.
  - **Tính mạch lạc ngữ nghĩa:** Strategy B cho điểm Coherence cao hơn rõ rệt (**1.80/2.0** so với **0.70/2.0** của Strategy A). Do Strategy A chia theo kích thước cố định 800 ký tự nên có 6/10 chunk mẫu bị cắt đứt giữa từ hoặc câu dở dang, trong khi Strategy B giữ được cấu trúc đoạn văn nguyên vẹn.
  - **Độ chính xác truy xuất:** Trên tập Test, Strategy B đạt Hit@1 ở mức **5/5 (100.0%)**, cao hơn Strategy A (**4/5 = 80.0%**). Tuy nhiên, trên tập Dev, Strategy A lại có Hit@1 cao hơn B (73.33% so với 53.33%). Hiện tượng này xuất phát từ việc Strategy A sử dụng cơ chế overlap 100 ký tự và chia nhỏ văn bản, giúp giữ mật độ từ khóa ở ranh giới cắt cao hơn khi so khớp cosine với câu hỏi ngắn; trong khi Strategy B giữ cả đoạn văn dài (đến 1000 ký tự) khiến vector ngữ nghĩa bị phân tán bởi nhiều ý phụ. Mặc dù vậy, việc chunk bị đứt câu ở Strategy A là một nhược điểm nghiêm trọng cho giai đoạn sinh câu trả lời (generation) của hệ thống RAG thực tế.
- **So sánh B–C (Tác động của Metadata Filtering):**
  - Strategy C sử dụng lại toàn bộ chunks và vector của Strategy B, chỉ kích hoạt thêm bộ lọc metadata SQL (`section`).
  - **Hiệu quả thực tế:** Trên tập Dev, Strategy C nâng tỷ lệ Hit@1 từ **8/15 (53.33%) lên 9/15 (60.00%)**. Cụ thể tại câu `q05`, bộ lọc `section = 'kinh_te_vi_mo'` đã loại bỏ chunk tóm tắt ở trang 11 (thuộc `tong_quan`), đưa chunk chứa dữ liệu khảo sát chính xác tại trang 24 từ Rank 2 lên Rank 1.
  - Trên câu test `q20`, bộ lọc metadata giúp Strategy C ngăn các chunk từ chương giáo dục đại học lọt vào top-3 (loại bỏ chunk nhiễu trang 51 vốn xuất hiện ở Rank 2 của B và Rank 3 của A), đảm bảo toàn bộ 3/3 kết quả trả về đều nằm trong phân đoạn phụ lục (trang 64).
  - Thời gian và chi phí nạp thêm của C bằng 0 (không tốn tài nguyên gọi API và không tăng dung lượng lưu trữ).

### 2. Hai ví dụ sai thực tế có ID câu và nguồn trích dẫn
- **Ví dụ 1 — Câu `q06` (Tập Dev, Trang 27): Sai lệch do nhiễu bảng biểu và chú thích**
  - *Câu hỏi:* "Trong quý II năm 2022, số lượng lao động có việc làm tại Việt Nam tăng bao nhiêu phần trăm so với cùng kỳ năm trước?"
  - *Bằng chứng mục tiêu:* Tăng 1,4% (trang 27, section `kinh_te_vi_mo`).
  - *Hiện tượng lỗi:* Ở cả ba chiến lược A, B, C, kết quả xếp Rank 1 (Score ~0.7271) là chunk chứa chú thích biểu đồ của Hình 1.15 và Hình 1.16 (*"Hình 1.15. Thị trường lao động... Nguồn: TCTK... Ghi chú: LLLĐ = Lực lượng lao động..."*). Chunk chứa bằng chứng đúng bị đẩy xuống **Rank 3** (Score ~0.7055).
  - *Nguyên nhân:* Phần chú thích hình ảnh chứa mật độ từ khóa ("lao động", "việc làm", "thị trường") lặp lại nhiều lần, khiến phép đo Cosine Similarity đánh giá mức độ tương đồng cao hơn đoạn văn mô tả số liệu. Mặc dù vẫn đạt Hit@3, câu hỏi này bị tính trượt Hit@1 trên cả ba cấu hình.
- **Ví dụ 2 — Câu `q05` (Tập Dev, Trang 24): Khác biệt giữa tìm kiếm thuần và tìm kiếm có bộ lọc**
  - *Câu hỏi:* "Theo khảo sát của Ngân hàng Thế giới từ tháng 01 đến tháng 03/2022, tỷ lệ doanh nghiệp quay trở lại sản xuất kinh doanh đạt bao nhiêu phần trăm?"
  - *Bằng chứng mục tiêu:* Đạt 92,6% (trang 24, section `kinh_te_vi_mo`).
  - *Hiện tượng ở Strategy B (Không có filter):* Chunk ở Rank 1 (Score 0.8040) là đoạn tóm tắt ở trang 11 thuộc `tong_quan` (*"Các doanh nghiệp đang phục hồi nhưng còn yếu ớt Khi nền kinh tế được mở cửa trở lại..."*). Đoạn này có ngữ nghĩa chung về doanh nghiệp phục hồi nhưng không có con số khảo sát cụ thể, khiến đoạn chứa đáp án 92,6% ở trang 24 bị đẩy xuống **Rank 2** (Score 0.7760).
  - *Cách Strategy C khắc phục:* Nhờ áp dụng bộ lọc `section = 'kinh_te_vi_mo'`, Strategy C loại bỏ đoạn tóm tắt ở trang 11, đưa trực tiếp đoạn văn ở trang 24 lên **Rank 1**.

### 3. Chiến lược lựa chọn, Đánh đổi và Điều kiện áp dụng
- **Chiến lược lựa chọn:** **Strategy C (Phân đoạn theo đoạn văn kết hợp Lọc Metadata theo chuyên mục)** là cấu hình phù hợp nhất cho pipeline dữ liệu này.
- **Đánh đổi kỹ thuật (Trade-offs):**
  - Chunking theo đoạn văn phụ thuộc vào chất lượng phân tách cấu trúc văn bản. Với tài liệu PDF bị lỗi dính dòng hoặc mất định dạng đoạn, phương pháp này có thể sinh ra các chunk có độ dài không đều hoặc vượt ngưỡng cho phép, đòi hỏi giải pháp cắt phụ trợ.
  - Rủi ro từ bộ lọc metadata: Strategy C phụ thuộc vào việc truy vấn của người dùng hoặc bước phân loại của hệ thống xác định đúng giá trị metadata (`section`). Nếu gán sai metadata ở bước tiền xử lý câu hỏi, hệ thống sẽ lọc bỏ nhầm các tài liệu liên quan (false exclusion).
- **Điều kiện áp dụng:** Cấu hình này phù hợp nhất với các tài liệu báo cáo chuyên đề, chính sách hoặc tài liệu kỹ thuật có sự phân chia chương mục rõ ràng, nơi mỗi phần giải quyết một chủ đề chuyên biệt.

### 4. Hạn chế của nghiên cứu
- **Kích thước tập Test nhỏ:** Tập Test gồm 5 câu mang tính chất kiểm tra kiểm toán đại diện, chưa đủ lớn để đưa ra kết luận có ý nghĩa thống kê trên diện rộng ngoài phạm vi tài liệu này.
- **Nhiễu trích xuất văn bản từ PDF:** Thư viện `pypdf` trích xuất dạng văn bản thô khiến các thành phần phi văn bản (tiêu đề biểu đồ, chú thích nguồn) bị trộn lẫn vào mạch phân tích chính.
- **Đo lường thời gian thực thi:** Thời gian chạy phụ thuộc vào độ trễ mạng và giới hạn tốc độ xử lý của API tại thời điểm kiểm thử.

### 5. Đề xuất cải tiến khi mở rộng
1. **Tiền xử lý bảng biểu và đồ thị:** Tách riêng các bảng số liệu và chú thích biểu đồ thành cấu trúc bảng Markdown độc lập trước khi chunking và embedding, tránh để lẫn vào văn bản phân tích gây nhiễu ngữ nghĩa.
2. **Tìm kiếm kết hợp (Hybrid Search):** Kết hợp tìm kiếm từ khóa chính xác BM25 (đặc biệt hiệu quả với các số liệu cụ thể như "1,4%", "92,6%") với tìm kiếm vector ngữ nghĩa (pgvector), sau đó dung hợp thứ hạng bằng thuật toán Reciprocal Rank Fusion (RRF).
3. **Mô hình xếp hạng lại (Cross-Encoder Reranker):** Áp dụng mô hình reranker nhẹ trên top-k kết quả ban đầu để chấm điểm tương quan sâu hơn giữa câu hỏi và chunk trước khi chuyển cho mô hình ngôn ngữ lớn xử lý.

---

## Tuyên bố hỗ trợ AI và Liêm chính học thuật
- **Khai báo sử dụng AI:** Báo cáo này sử dụng Antigravity làm công cụ hỗ trợ đọc và trích xuất dữ liệu từ các file trace log, và đề xuất bảng nhãn kiểm toán sơ bộ (Coherence, Grounding) dựa trên rubric của Lab.
- **Tính xác thực của số liệu:** Toàn bộ số liệu định lượng (Hit@1, Hit@3, số lượng chunk, thời gian thực thi) trong báo cáo được trích xuất trực tiếp từ các file kết quả thực tế do ứng dụng ghi nhận (`results/summary_metrics.json` và `results/traces_strategy_*.json`), không có số liệu tự tạo hay chỉnh sửa.
- **Xác thực của học viên:** Học viên đã trực tiếp kiểm tra chéo các nhãn kiểm toán định tính (Coherence trên 10 chunk mẫu và Grounding trên 5 câu test) đối chiếu với văn bản trong PostgreSQL và PDF gốc, xác nhận tính chính xác của các nhãn này trước khi hoàn tất nộp bài.
