# 🎬 HƯỚNG DẪN BẮT BUỘC CHO AI AGENT (AUTO-LOADED WORKSPACE RULES)

Khi người dùng yêu cầu xử lý / làm video review cho một tập phim mới trong thư mục này (ví dụ: *"xử lý tập mới giúp tôi"*, *"chạy review tập X nhé"*), bạn **BẮT BUỘC** phải tuân thủ tuyệt đối quy trình kỹ thuật, cấu trúc **30s Mở Màn Thoại Gốc Cao Trào (Cold Open Dubbing)** và văn phong **Người Kể Chuyện (Storyteller)** dưới đây (xem chi tiết đầy đủ hơn trong `README.md`).

---

## 1. QUY TRÌNH THỰC THI TỰ ĐỘNG (END-TO-END WORKFLOW)

### Bước 1: Kiểm tra đầu vào & tùy chọn che sub
- File nguồn nằm trong `input/*.mp4` và `input/*.srt` (tất cả các script trong `pipeline/` đã tự động nhận diện file trong `input/` trên cả macOS lẫn Windows).
- Kiểm tra yêu cầu của người dùng:
  - Nếu người dùng nói **"không cần che mờ sub"** (hoặc mặc định không yêu cầu), đặt `BLUR_SUBS = False` trong `pipeline/assemble.py`.
  - Nếu người dùng **cần che mờ sub Trung**, đặt `BLUR_SUBS = True` trong `pipeline/assemble.py` (thuật toán `detect_all_seg_boxes` sẽ tự động dò hộp chữ 2D ôm sát từng câu thoại kết hợp nội suy tọa độ dọc `interp_y` từ file `.srt`).
- Luôn giữ mặc định trong `pipeline/assemble.py`:
  - `ORIG_VOL = 0.0` (tắt hoàn toàn tiếng video gốc ở phần Review, chỉ giữ 100% giọng lồng tiếng Việt; ở phần 30s mở màn có thể giữ tiếng động hiện trường đắt giá như tiếng tát/đập vỡ qua `sfx_lead_sec`).
  - `BURN_SUBS = False` (không chèn phụ đề tiếng Việt hay tiêu đề góc trên vào video; xuất phụ đề rời ra `output/review_vi.srt`).

### Bước 2: Chạy tiền xử lý (Chạy song song để tối ưu tốc độ)
1. Chạy rút gọn SRT và dò vùng sub cứng (hỗ trợ cả `zsh/bash` trên macOS và `PowerShell` trên Windows):
   ```bash
   # macOS (zsh/bash): export PYTHONIOENCODING=utf-8
   # Windows (PowerShell): $env:PYTHONIOENCODING="utf-8"
   python pipeline/condense_srt.py
   python pipeline/detect_subband.py
   ```
2. Chạy song song 3 tác vụ:
   - `python -u pipeline/asr.py` (chỉ quét Whisper `large-v3` trên các khoảng trống SRT > 40 giây).
   - `python -u pipeline/shots.py` (tách cảnh đa luồng 8 nhân `ProcessPoolExecutor`).
   - `python -u pipeline/contact_sheets.py` (xuất ~22 bảng ảnh tổng quan vào `work/sheets/`).
3. Sau khi `shots.py` hoàn tất, chạy `python -u pipeline/overlay_text.py` để lọc bỏ các cảnh dính thẻ tên nhân vật / chữ nổi ngoài vùng sub.

### Bước 3: Đọc toàn bộ cốt truyện & Viết kịch bản `pipeline/script_beats.py` (Gồm `INTRO_DUB` 30s + `BEATS` Review)
- Đọc toàn bộ `work/srt_condensed.txt`, `work/asr_gaps.txt` và xem các tấm ảnh trong `work/sheets/*.jpg` để nắm rõ nhân vật, diễn biến và cao trào.
- Lập **Bảng tên nhân vật Hán Việt chuẩn** và giữ thống nhất từ đầu đến cuối.
- Kịch bản trong `pipeline/script_beats.py` bắt buộc gồm **2 phần nối tiếp nhau**:
  1. **`INTRO_DUB` (~30 giây Mở màn Lồng tiếng Thoại gốc Cay nghiệt / Gay cấn – TUYỆT ĐỐI KHÔNG SPOIL KẾT QUẢ):**
     - **QUY TẮC CHỌN CẢNH (CẤM SPOIL KẾT CỤC):** Chọn phân cảnh **cay nghiệt, ức chế tột độ** (bị sỉ nhục, bị phản bội phũ phàng, bị vu oan giá họa, bị chà đạp kỷ vật...) hoặc phân cảnh **gay cấn đang bỏ lửng trước khi lật kèo**. **TUYỆT ĐỐI KHÔNG** lấy cảnh kết quả cuối phim (như cảnh phản diện đã bị trừng phạt phá sản hay cảnh lộ diện thân phận giải quyết xong xuôi) đưa lên 30s đầu vì sẽ làm mất sự tò mò của khán giả.
     - Gọt bỏ các đoạn thoại phụ rườm rà ở giữa để cô đọng các câu va chạm cay nghiệt/gay cấn nhất trong khoảng **28 – 35 giây** (`3 – 6` cụm cảnh gốc liền mạch `block_id`).
     - **QUY TẮC TÁCH VOICE NGẮT NGHỈ TỰ NHIÊN (BẮT BUỘC):** Tuyệt đối **KHÔNG gộp nhiều câu thoại thành 1 đoạn dài ngoằng** bắt TTS đọc liền một hơi. Chỗ nào trong `.srt` gốc nhân vật ngắt câu, lấy hơi hoặc chuyển ý thì **bắt buộc tách thành 1 phần tử riêng trong `INTRO_DUB`** (mỗi câu/vế ngắn chỉ **4 – 15 âm tiết**, dài **0.8 – 3.0 giây**, tổng cộng **12 – 16 câu thoại ngắn** cho 30 giây mở màn) để TTS đọc thành **một file voice mới riêng biệt**, kèm khoảng nghỉ `post_pause_sec` (`0.20s – 0.60s`) khớp với khẩu hình và nhịp chuyển góc máy trên màn hình.
     - Định dạng mỗi dòng trong `INTRO_DUB`:
       `(block_id, "h:mm:ss.s", sfx_lead_sec, post_pause_sec, "Câu thoại ngắn")`.
     - Ngay sau câu thoại cuối cùng của `INTRO_DUB` (điểm cắt Cliffhanger), `assemble.py` sẽ tự động chèn **0.55 giây khựng hình chuyển cảnh (Freeze Frame + Fade tối dần)** trước khi vào `BEATS`.
  2. **`BEATS` (Phần Review Người Kể Chuyện – Khoảng 112 – 120 beat, ~7.000 – 7.600 âm tiết):**
     - **Beat 1 – Beat 2 (Cầu nối Mở Vòng Lặp Tò Mò – Không Spoil Kết Cục):** Nối tiếp ngay sau điểm cắt 30s mở màn (bằng ngôi thứ ba Người Kể Chuyện) để xoáy sâu vào sự cay nghiệt/bất công vừa diễn ra và hé mở ẩn ý rằng kẻ phản diện thực dụng kia vừa tự tay đẩy mình vào bi kịch hoặc mở ra bước ngoặt đổi đời mà không hề hay biết (giữ kín kết cục cuối phim để dẫn dắt người xem theo dõi từ đầu).
     - **Beat 3 trở đi:** Kể tuyến tính toàn bộ câu chuyện theo phong cách Người Kể Chuyện ngôi thứ ba.
- Chạy lệnh kiểm tra tự động để đảm bảo **0 ký tự cấm** (`:`, `;`, `0-9`, `"`, `'`, `()`, chữ Hán) trong cả `INTRO_DUB` và `BEATS`:
  ```bash
  python -c "import sys,re; sys.path.insert(0,'pipeline'); import script_beats as sb; intro=getattr(sb,'INTRO_DUB',[]); beats=sb.BEATS; bad_i=[i+1 for i,x in enumerate(intro) if re.search(r'[:;0-9\x22\x27()\u4e00-\u9fff]', x[4])]; bad_b=[i+1 for i,(_,t) in enumerate(beats) if re.search(r'[:;0-9\x22\x27()\u4e00-\u9fff]', t)]; print('intro_lines:', len(intro), 'beats:', len(beats), 'syllables:', sum(len(t.split()) for _,t in beats), 'bad_intro:', bad_i, 'bad_beats:', bad_b)"
  ```
  *(Kết quả `bad_intro` và `bad_beats` bắt buộc phải là `[]`)*.

### Bước 4: Lồng tiếng qua MCP `dgt-auto-tts` (Giọng chuẩn `viet_rv_v2_dt6uCxVe`, `speed=1.0`)
1. Xóa sạch cache âm thanh cũ (`work/tts/narration/*.mp3` và `work/aud/*.wav`).
2. Xuất toàn bộ các câu ngắn của `INTRO_DUB` (`1 .. M`) nối tiếp với `BEATS` (`M+1 .. M+N`) ra file `work/tts/narration.srt` (mỗi câu thoại ngắn trong `INTRO_DUB` và mỗi beat trong `BEATS` là **1 entry SRT riêng biệt** để app tạo file voice mới cho từng câu, **tuyệt đối không nạp file `.txt`**):
   ```bash
   python pipeline/assemble.py make_srt
   ```
3. Gọi MCP `dgt-auto-tts`:
   - `get_status` / `list_voices` -> kiểm tra và chọn giọng chuẩn **`viet_rv_v2_dt6uCxVe`** (`voice_id: 73bbb225193b`). Nếu sang máy mới chưa có giọng này trong danh sách, gọi `clone_voice(voice_name="viet_rv_v2", language="Vietnamese", sample_path="<đường_dẫn_tuyệt_đối>/tools/voice_sample_v2.mp3", agree_terms=True, select=True)`.
   - Giữ nguyên tốc độ tự nhiên **`speed = 1.0`** và model **`speech-02-hd`** (`set_tts_settings(change_speed=False, speed=1.0, model="speech-02-hd")`). **TUYỆT ĐỐI KHÔNG** đẩy `speed=1.08` hay chỉnh sửa tốc độ giọng đọc.
   - `load_input(file_path="<đường_dẫn_tuyệt_đối>/work/tts/narration.srt")` -> kiểm tra `total_lines == len(INTRO_DUB) + len(BEATS)` và `short_lines == []`.
   - `start_tts(allow_long_lines=True, merge_short_lines=False)` -> chờ `done == total_lines` (nếu có dòng dừng ở `Retry: 25` do server full luồng `API 429/503`, gọi `start_tts` bồi tiếp cho đến khi đủ 100% các câu).

### Bước 5: Dựng video, Kiểm tra QA & Xuất Bộ SEO
1. Chạy `python -u pipeline/assemble.py audio plan` -> kiểm tra `beats with slow-motion fill: []` (nếu có beat bị làm chậm, mở rộng cửa sổ thời gian nguồn của beat đó trong `script_beats.py` rồi chạy lại `plan`). Bước `plan` tự động lưu `work/intro_meta.json` (`intro_dur`) và mốc `start_sec` / `end_sec` của từng beat trong `work/plan.json`.
2. Chạy `python -u pipeline/assemble.py beats final` để xuất `output/review_vi.mp4` (gồm 30s Intro Thoại + 0.55s Chuyển cảnh + Review), `output/review_vi.srt`, `output/kich_ban_review.txt`.
3. Chạy kiểm tra chất lượng:
   - `python -u pipeline/qa_tts.py 1 15 35 60 85 105 112` (kiểm tra phát âm tên riêng và câu chữ).
   - `python -u pipeline/qa_sheet.py` -> mở xem các ảnh `work/qa/qa_*.jpg` (đã tự động cộng độ lệch `intro_dur` để chụp đúng khung hình giữa mỗi beat). Nếu beat nào dính thẻ *"未完待续 / 完结"* hoặc lệch cảnh, chỉnh lại cửa sổ thời gian của beat đó rồi chạy lại `python -u pipeline/assemble.py plan beats final` (nhờ cache `.sig`, chỉ những beat sửa mới phải render lại, mất ~15 giây).
4. *(Tùy chọn)* Nếu cần xuất bộ 3 ảnh Thumbnail, chạy `python -u pipeline/make_thumbnails.py` ngay ở bước này (trước khi xóa `work/` và `input/`).
5. Tạo file `output/youtube_seo.txt` (gồm Top 5 Tiêu đề tối ưu CTR, Mô tả kèm ~10 mốc thời gian Chapters lấy từ trường `start_sec` trong `work/plan.json` đã cộng `intro_dur`, Thẻ Tags và Bình luận ghim) và gửi trực tiếp trong khung chat cho người dùng.

### Bước 6: Tự động dọn rác sau khi hoàn thành
- Sau khi đã kiểm tra xong thành phẩm trong `output/`, **BẮT BUỘC xóa sạch**:
  - Thư mục trung gian `work/`
  - Thư mục `pipeline/__pycache__/`
  - Các file `.mp4` và `.srt` trong `input/` (giữ lại `input/.gitkeep`).
- Chỉ để lại thư mục `output/` chứa thành phẩm cùng bộ code Core.

---

## 2. QUY TẮC MỞ MÀN 30S THOẠI GỐC (`INTRO_DUB`) & VĂN PHONG "NGƯỜI KỂ CHUYỆN" (`BEATS`)

### 2.1. Quy tắc Vàng cho 30 giây Mở màn Lồng tiếng Thoại gốc (`INTRO_DUB` – Cay Nghiệt / Kịch Tính nhưng Không Spoil Kết Quả)
- **Đồng nhất 1 giọng đọc duy nhất:** Sử dụng chính giọng đọc của kênh cho cả phần 30s thoại mở màn và phần Review để giữ sự đồng nhất xuyên suốt video.
- **Chọn Đỉnh Điểm Cay Nghiệt / Bỏ Lửng Trước Khi Lật Kèo (Cấm Spoil Kết Quả):**
  - Chỉ chọn những phân cảnh **cay nghiệt, ức chế nhất** (kẻ bội bạc chà đạp chân tình, tiểu tam ngông cuồng sỉ nhục, đám đông hùa nhau khinh miệt kỷ vật vô giá, tay sai bức tử nơi lãnh cung...) hoặc cảnh đối đầu đang ở thế ngàn cân treo sợi tóc **trước khi nhân vật chính tung đòn kết liễu**.
  - **CẤM** lấy cảnh kết quả cuối phim (khi kẻ ác đã quỳ gối phá sản, mọi chuyện đã ngã ngũ) làm 30s mở màn vì sẽ làm lộ hết kết cục.
- **Cắt Nhịp Nén & Khớp Cảnh Gốc 100%:**
  - Lấy trực tiếp các đoạn hình gốc (`block_id`, từ `3 – 6` cụm cảnh) nơi nhân vật đang nói và gọt bỏ các đoạn thoại phụ rườm rà ở giữa để gói gọn trong **28 – 35 giây**.
  - Nếu đầu cụm cảnh có hành động mạnh (như tiếng tát, tiếng hất đổ bánh kem/đập vỡ đồ), đặt `sfx_lead_sec` để giữ lại âm thanh hiện trường đắt giá đó trước khi câu thoại cất lên.
- **Tách từng câu ngắt nghỉ thành Voice mới (Cấm chạy 1 câu dài ngoằng):**
  - Trong `INTRO_DUB`, tuyệt đối không ghép 3–4 câu thoại thành một câu dài 30–40 chữ.
  - Cứ mỗi chỗ ngắt nghỉ trong `.srt` gốc (mỗi vế/câu ngắn **4 – 15 âm tiết**, dài **0.8 – 3.0 giây**, tổng cộng **12 – 16 câu thoại ngắn**), phải tách thành **1 dòng độc lập** để TTS tạo **1 file voice mới riêng biệt**, sau đó nghỉ `post_pause_sec` (`0.20s – 0.60s` tùy theo nhịp nhân vật ngừng lấy hơi hoặc nhịp chuyển góc máy) rồi mới phát file voice tiếp theo. Cách này giúp giọng đọc có nhịp ngắt tự nhiên như người thật đang thoại và khớp khẩu hình từng giây.
- **Hiệu ứng Chuyển cảnh 0.55s & Cầu nối sang Review:**
  - Kết thúc 30s mở màn ngay ở câu thoại phán quyết / thời khắc sinh tử căng thẳng nhất (Cliffhanger), tự động khựng hình `0.55s` (Freeze Frame + Fade tối dần) rồi chuyển sang giọng **Người Kể Chuyện (ngôi thứ ba)** ở `BEATS[0]` và `BEATS[1]` để dẫn dắt mượt mà về đầu phim.

### 2.2. Phần thân Review (`BEATS`): Tuyệt đối giữ ngôi thứ ba (Người Dẫn Chuyện)
- Từ `BEATS[0]` trở đi (sau 30s mở màn), chuyển hoàn toàn sang **ngôi thứ ba của Người Dẫn Chuyện**:
  - **CẤM:** Dùng dấu hai chấm (`:`), ngoặc kép (`"`), hoặc nhảy sang ngôi thứ nhất/ngôi thứ hai nhập vai đối thoại trực tiếp (*tôi, tao, mày, cậu, tớ, chúng ta*, hoặc xưng *em, con, mình* như lời thoại trực tiếp của nhân vật).
  - **ĐƯỢC PHÉP (CHUẨN NGÔI THỨ BA):** Chuyển hóa toàn bộ lời thoại thành **lời kể gián tiếp lột tả tâm lý, động cơ, sự mỉa mai và đòn phản kích**; sử dụng tự nhiên các đại từ ngôi thứ ba chỉ nhân vật (*anh, cô, hắn, ả, ông, bà, cậu bé...*) và các từ ghép tiếng Việt thông dụng (*giật mình, mình mẩy, đàn em, con người, con đường, bà con...*).

### 2.3. Giải phẫu 3 lớp cho mỗi Beat Review & Nhịp Ngắt Tự Nhiên (50–65 âm tiết/beat)
- Mỗi beat trong `BEATS` chia thành **4–5 vế ngắn gọn có nhịp thở tự nhiên** ngăn cách bởi **3–4 dấu phẩy `,`** (mỗi vế dài **10–16 âm tiết**), và khi xuất phụ đề `.srt` cũng tự động tách theo từng vế ngắn để không hiện 1 đoạn chữ dài ngoằng trên màn hình:
  1. **Lớp 1 – Trạng thái / Bối cảnh mở nhịp (8–14 âm tiết đầu + dấu phẩy `,`):** Đặt ngay tâm lý hoặc sự đối lập (*"Giữa tiếng xì xào bàn tán đầy phẫn nộ của quan khách,"*).
  2. **Lớp 2 – Hành động cốt lõi dùng động từ mạnh (25–35 âm tiết giữa, chia 2–3 vế bằng dấu phẩy `,`):** Thay các từ nhạt nhẽo (*nói, làm, đi*) bằng động từ giàu sức nặng (*vạch trần, dội một gáo nước lạnh, phủi sạch quan hệ, tống đạt, rút sạch vốn, lột trần bộ mặt thật, đập tan ảo tưởng*).
  3. **Lớp 3 – Điểm nhấn cảm xúc / Châm biếm cuối câu (12–16 âm tiết cuối sau dấu phẩy `,`):** Khép lại beat bằng một dư âm đắt giá (*"...đẩy kẻ ăn cháo đá bát từ đỉnh cao danh vọng xuống thẳng vực sâu vạn trượng."*).

### 2.4. Kỹ thuật Nén Hội Thoại & Đòn Đối Lập Kép
- Phim ngắn Trung Quốc thường có các màn cãi vã kéo dài 15–20 phút. Tuyệt đối không dịch lặp lại từng câu cãi nhau mà **gom thành các nấc thang xung đột** (Khiêu khích -> Vạch mặt bằng chứng -> Phản đòn pháp lý -> Sụp đổ).
- Thường xuyên đặt hai hình ảnh trái ngược vào chung một câu văn (*trong khi nữ chính đứng trên bục nhận giải thưởng trăm tỷ dưới ánh đèn rực rỡ, thì gã chồng cũ lại đang khoác tạp dề bê từng thùng nước trong cửa hàng tiện lợi*).

### 2.5. Quy tắc Âm học & Cân Bằng Nhịp Ngắt Tự Nhiên / Khóa Tốc Độ TTS
- Mọi con số phải viết bằng chữ tiếng Việt chuẩn (*ba năm*, *tám mươi triệu tệ*, *bốn mươi phần trăm*, *hai mươi tệ một giờ*).
- Đan cài các cụm từ 4 chữ giàu nhạc tính (*ăn cháo đá bát, được đằng chân lân đằng đầu, kim chi ngọc diệp, trở mặt nhanh hơn lật sách, trốn chui trốn lủi, đầu đường xó chợ, tiền mất tật mang*).
- **Xử lý âm thanh trong `pipeline/assemble.py` (`stage_audio`) – GIỮ NGUYÊN BẢN TỰ NHIÊN 100%:** chỉ cắt khoảng lặng đầu/cuối mỗi file TTS bằng `silenceremove` (`-48 dB`), ghép các câu ngắn trong `INTRO_DUB` theo đúng khoảng nghỉ tự nhiên `post_pause_sec` (`0.20s – 0.60s`), và ghép các beat trong `BEATS` cách nhau `PAUSE = 0.14s`. **CẤM** đổi tốc độ từng beat (`atempo`), **CẤM** cắt/ghép/nén khoảng nghỉ bên trong câu. Nhịp đọc do chính giọng TTS chuẩn `viet_rv_v2_dt6uCxVe` (`speed=1.0`, `speech-02-hd`) quyết định, và thời lượng đoạn hình của mỗi beat được tự động tính khớp 100% theo thời lượng file voice của beat đó.

### 2.6. Quy tắc Chọn Cửa Sổ Thời Gian (`spec`) Bám Sát Cảnh 100% & Không Bị Làm Chậm (`slow: []`)
- **Độ rộng cửa sổ chặt (Chuẩn Tập 15):**
  - Trung vị độ rộng cửa sổ mỗi beat trong `BEATS` chỉ khoảng **40 – 50 giây** (dao động trong khoảng **28 – 65 giây**, **TUYỆT ĐỐI KHÔNG vượt quá 85–90 giây**). Cấm đặt cửa sổ rộng 2–4 phút vì sẽ làm thuật toán lấy hình rải sang các cảnh chưa/đã xảy ra, gây lệch lời với hình.
  - Từ Beat 3 trở đi, hai beat liên tiếp **không được chồng lấn (`overlap`) quá 8–10 giây**.
- **Neo mốc thời gian trực tiếp vào hành động trên hình (`work/sheets/*.jpg` & `work/srt_condensed.txt`):**
  - Trước khi viết, bắt buộc kiểm tra 3–4 câu thoại đặc trưng ở đầu, giữa và cuối phim để chắc chắn mốc thời gian SRT không bị trôi so với hình.
  - Mỗi beat kể hành động nào (ví dụ: *tát lật mặt*, *ném xấp ảnh*, *đập vỡ lọ thuốc*, *cán bộ văn vật ập vào*) thì cửa sổ `h:mm:ss-h:mm:ss` phải đóng khung **đúng khoảnh khắc hành động đó diễn ra trên màn hình**.
  - Nếu 1 beat ghép 2 hành động ở hai thời điểm cách nhau hoặc có cảnh hồi tưởng xen giữa, bắt buộc tách thành **2 cửa sổ con cách nhau bằng dấu phẩy** (ví dụ `"0:38:20-0:38:43,0:38:45-0:39:25"`).
