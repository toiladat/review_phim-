# 🎬 HƯỚNG DẪN BẮT BUỘC CHO AI AGENT (AUTO-LOADED WORKSPACE RULES)

Khi người dùng yêu cầu xử lý / làm video review cho một tập phim mới trong thư mục này (ví dụ: *"xử lý tập mới giúp tôi"*, *"chạy review tập X nhé"*), bạn **BẮT BUỘC** phải tuân thủ tuyệt đối quy trình kỹ thuật và văn phong **Người Kể Chuyện (Storyteller)** dưới đây (xem chi tiết đầy đủ hơn trong `README.md`).

---

## 1. QUY TRÌNH THỰC THI TỰ ĐỘNG (END-TO-END WORKFLOW)

### Bước 1: Kiểm tra đầu vào & tùy chọn che sub
- File nguồn nằm trong `input/*.mp4` và `input/*.srt` (tất cả các script trong `pipeline/` đã tự động nhận diện file trong `input/`).
- Kiểm tra yêu cầu của người dùng:
  - Nếu người dùng nói **"không cần che mờ sub"**, đặt `BLUR_SUBS = False` trong `pipeline/assemble.py`.
  - Nếu người dùng **cần che mờ sub Trung**, đặt `BLUR_SUBS = True` trong `pipeline/assemble.py` (thuật toán `detect_all_seg_boxes` sẽ tự động dò hộp chữ 2D ôm sát từng câu thoại kết hợp nội suy tọa độ dọc `interp_y` từ file `.srt`).
- Luôn giữ mặc định trong `pipeline/assemble.py`:
  - `ORIG_VOL = 0.0` (tắt hoàn toàn tiếng video gốc, chỉ giữ 100% giọng lồng tiếng Việt).
  - `BURN_SUBS = False` (không chèn phụ đề tiếng Việt hay tiêu đề góc trên vào video; xuất phụ đề rời ra `output/review_vi.srt`).

### Bước 2: Chạy tiền xử lý (Chạy song song để tối ưu tốc độ)
1. Chạy rút gọn SRT và dò vùng sub cứng:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"
   python pipeline/condense_srt.py
   python pipeline/detect_subband.py
   ```
2. Chạy song song 3 tác vụ:
   - `python -u pipeline/asr.py` (chỉ quét Whisper `large-v3` trên các khoảng trống SRT > 40 giây).
   - `python -u pipeline/shots.py` (tách cảnh đa luồng 8 nhân `ProcessPoolExecutor`).
   - `python -u pipeline/contact_sheets.py` (xuất ~22 bảng ảnh tổng quan vào `work/sheets/`).
3. Sau khi `shots.py` hoàn tất, chạy `python -u pipeline/overlay_text.py` để lọc bỏ các cảnh dính thẻ tên nhân vật / chữ nổi ngoài vùng sub.

### Bước 3: Đọc toàn bộ cốt truyện & Viết kịch bản `pipeline/script_beats.py`
- Đọc toàn bộ `work/srt_condensed.txt`, `work/asr_gaps.txt` và xem các tấm ảnh trong `work/sheets/*.jpg` để nắm rõ nhân vật, diễn biến và cao trào.
- Lập **Bảng tên nhân vật Hán Việt chuẩn** và giữ thống nhất từ đầu đến cuối.
- Viết khoảng **115 – 123 beat** (tổng cộng **~7.000 – 7.800 âm tiết**, tương đương video review dài **24 – 26 phút**) vào `pipeline/script_beats.py`.
- Chạy lệnh kiểm tra tự động để đảm bảo **0 ký tự cấm** (`:`, `;`, `0-9`, `"`, `'`, `()`, chữ Hán):
  ```powershell
  python -c "import sys,re; sys.path.insert(0,'pipeline'); from script_beats import BEATS; bad=[i+1 for i,(_,t) in enumerate(BEATS) if re.search(r'[:;0-9\x22\x27()\u4e00-\u9fff]', t)]; print('beats:', len(BEATS), 'syllables:', sum(len(t.split()) for _,t in BEATS), 'bad:', bad)"
  ```
  *(Kết quả `bad` bắt buộc phải là `[]`)*.

### Bước 4: Lồng tiếng qua MCP `dgt-auto-tts`
1. Xóa sạch cache âm thanh cũ (`work/tts/narration/*.mp3` và `work/aud/*.wav`).
2. Xuất `BEATS` ra file `work/tts/narration.srt` (mỗi beat là 1 entry SRT riêng biệt, **tuyệt đối không nạp file `.txt`** để tránh app tự gộp dòng).
3. Gọi MCP `dgt-auto-tts`:
   - `get_status` -> kiểm tra giọng `viet_review_dt6Rssa4`, model `speech-02-hd`.
   - `set_tts_settings(change_speed=True, speed=1.08)`
   - `load_input(file_path="...\\work\\tts\\narration.srt")` -> kiểm tra `total_lines == len(BEATS)` và `short_lines == []`.
   - `start_tts(merge_short_lines=False)` -> chờ `done == len(BEATS)` rồi trả tốc độ về `set_tts_settings(change_speed=False, speed=1.0)`.

### Bước 5: Dựng video, Kiểm tra QA & Xuất Bộ SEO
1. Chạy `python -u pipeline/assemble.py audio plan` -> kiểm tra `beats with slow-motion fill: []` (nếu có beat bị làm chậm, mở rộng cửa sổ thời gian nguồn của beat đó trong `script_beats.py` rồi chạy lại `plan`).
2. Chạy `python -u pipeline/assemble.py beats final` để xuất `output/review_vi.mp4`, `output/review_vi.srt`, `output/kich_ban_review.txt`.
3. Chạy kiểm tra chất lượng:
   - `python -u pipeline/qa_tts.py 1 15 35 60 85 105 120` (kiểm tra phát âm tên riêng và câu chữ).
   - `python -u pipeline/qa_sheet.py` -> mở xem các ảnh `work/qa/qa_*.jpg`. Nếu beat nào dính thẻ *"未完待续 / 完结"* hoặc lệch cảnh, chỉnh lại cửa sổ thời gian của beat đó rồi chạy lại `python -u pipeline/assemble.py plan beats final` (nhờ cache `.sig`, chỉ những beat sửa mới phải render lại, mất ~15 giây).
4. Tạo file `output/youtube_seo.txt` (gồm Top 5 Tiêu đề tối ưu CTR, Mô tả kèm ~10 mốc thời gian Chapters tính chính xác từ `work/plan.json`, Thẻ Tags và Bình luận ghim) và gửi trực tiếp trong khung chat cho người dùng.

### Bước 6: Tự động dọn rác sau khi hoàn thành
- Sau khi đã kiểm tra xong thành phẩm trong `output/`, **BẮT BUỘC xóa sạch**:
  - Thư mục trung gian `work/`
  - Thư mục `pipeline/__pycache__/`
  - Các file `.mp4` và `.srt` trong `input/` (giữ lại `input/.gitkeep`).
- Chỉ để lại thư mục `output/` chứa thành phẩm cùng bộ code Core.

---

## 2. BÍ QUYẾT VĂN PHONG "NGƯỜI KỂ CHUYỆN" (STORYTELLER STYLE GUIDE)

Đây là linh hồn của kênh review. Mọi kịch bản trong `pipeline/script_beats.py` phải tuân thủ nghiêm ngặt 6 nguyên tắc sau:

### 2.1. Tuyệt đối giữ ngôi thứ ba (Người Dẫn Chuyện) – Cấm trích thoại trực tiếp
- **CẤM:** Dùng dấu hai chấm (`:`), ngoặc kép (`"`), hoặc nhảy sang ngôi thứ nhất/thứ hai (*tôi, mình, cậu, anh, em, con, chúng ta*).
- **CHUẨN:** Chuyển hóa toàn bộ lời thoại thành **lời kể gián tiếp lột tả tâm lý, động cơ, sự mỉa mai và đòn phản kích**.
  - *Sai:* `Cố Diễn Chi nói: một chiếc nhẫn thôi mà, cho Hàm Yên đeo thử thì mất miếng thịt nào đâu.`
  - *Đúng:* `Khi Vân Chiêu lên tiếng đòi lại công bằng, gã đàn ông bội bạc chẳng những không thấy hổ thẹn mà còn quay sang trách cô nhỏ nhen ích kỷ, lạnh lùng buông lời rằng chỉ là một chiếc nhẫn vô tri, cho cô em gái mồ côi đeo thử một chút thì có mất miếng thịt nào đâu.`

### 2.2. Giải phẫu 3 lớp cho mỗi Beat (3-Layer Beat Anatomy, 55–68 âm tiết/beat)
Mỗi beat phải là một câu văn dày dặn, giàu nhịp điệu gồm 3 lớp hòa quyện:
1. **Lớp 1 – Trạng thái / Bối cảnh mở nhịp (6–12 âm tiết đầu):** Đặt ngay tâm lý hoặc sự đối lập (*"Giữa tiếng xì xào bàn tán đầy phẫn nộ của quan khách,"*, *"Không để gia tộc chịu thêm bất kỳ sự sỉ nhục nào nữa,"*, *"Trớ trêu thay,"*, *"Đứng trước bản sao kê không thể chối cãi,"*).
2. **Lớp 2 – Hành động cốt lõi dùng động từ mạnh (25–35 âm tiết giữa):** Thay các từ nhạt nhẽo (*nói, làm, đi*) bằng động từ giàu sức nặng (*vạch trần, dội một gáo nước lạnh, phủi sạch quan hệ, tống đạt, rút sạch vốn, lột trần bộ mặt thật, đập tan ảo tưởng*).
3. **Lớp 3 – Điểm nhấn cảm xúc / Châm biếm cuối câu (15–20 âm tiết cuối):** Khép lại beat bằng một dư âm đắt giá (*"...đẩy kẻ ăn cháo đá bát từ đỉnh cao danh vọng xuống thẳng vực sâu vạn trượng."*, *"...khiến cả hội trường cười chê kẻ tự tay đập vỡ bát cơm vàng."*).

### 2.3. Kỹ thuật Mở màn (Hook 5–6 Beat đầu tiên)
- **Beat 1–3:** Đưa ngay tình huống ức chế/nghịch lý đỉnh điểm ở đầu phim (ví dụ: giấu thân phận 3 năm bị trao nhẫn đính hôn cho tiểu tam; 3 năm làm dâu bị tặng hàng khuyến mãi).
- **Beat 4–5:** Hé lộ thân phận thật sự của nhân vật chính (đại tiểu thư nghìn tỷ, nhà thiết kế thiên tài...) và nhá hàng cú vả mặt chấn động để giữ chân khán giả.
- **Beat 6:** Dùng cụm chuyển cảnh (*"Quay trở lại buổi sáng ngày diễn ra đại lễ..."*) để bắt vào mạch thời gian chính.

### 2.4. Kỹ thuật Nén Hội Thoại & Đòn Đối Lập Kép
- Phim ngắn Trung Quốc thường có các màn cãi vã kéo dài 15–20 phút. Tuyệt đối không dịch lặp lại từng câu cãi nhau mà **gom thành các nấc thang xung đột** (Khiêu khích -> Vạch mặt bằng chứng -> Phản đòn pháp lý -> Sụp đổ).
- Thường xuyên đặt hai hình ảnh trái ngược vào chung một câu văn (*trong khi nữ chính đứng trên bục nhận giải thưởng trăm tỷ dưới ánh đèn rực rỡ, thì gã chồng cũ lại đang khoác tạp dề bê từng thùng nước trong cửa hàng tiện lợi*).

### 2.5. Quy tắc Âm học cho TTS Tiếng Việt
- Mọi con số phải viết bằng chữ tiếng Việt chuẩn (*ba năm*, *tám mươi triệu tệ*, *bốn mươi phần trăm*, *hai mươi tệ một giờ*).
- Kiểm soát độ dài mỗi vế câu từ **8 – 22 âm tiết** ngăn cách bằng dấu phẩy `,` để giọng TTS ngắt nghỉ hơi tự nhiên như người thật.
- Đan cài các cụm từ 4 chữ giàu nhạc tính (*ăn cháo đá bát, được đằng chân lân đằng đầu, kim chi ngọc diệp, trở mặt nhanh hơn lật sách, trốn chui trốn lủi, đầu đường xó chợ, tiền mất tật mang*).

### 2.6. Quy tắc Chọn Cửa Sổ Thời Gian (`spec`) Không Bị Làm Chậm (`slow: []`)
- Ở tốc độ TTS `1.08`, giọng đọc phát âm khoảng `4,2 âm tiết/giây`. Một beat 60 âm tiết cần ~14,5 giây hình ảnh.
- Luôn đặt cửa sổ thời gian nguồn cho mỗi beat rộng tối thiểu **35 – 70 giây** (ví dụ `"0:03:41-0:04:35"`) để thuật toán chọn được những cú máy đẹp nhất, rải đều theo diễn biến mà không bao giờ phải làm chậm khung hình.

