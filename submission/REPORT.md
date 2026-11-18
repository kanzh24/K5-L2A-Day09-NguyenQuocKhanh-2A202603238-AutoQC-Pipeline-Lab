# Báo cáo Day 09 — Nguyen Quoc Khanh, 2A202603238

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10). Lô dữ liệu đầu vào gồm 224 ảnh, qua cửa vào intake loại 21 ảnh vi phạm, giữ lại 203 ảnh đưa vào kiểm tra và sửa nhãn; kết thúc quy trình xuất 203 ảnh sang dataset nháp `submission/export/clean_v1`. Lý do chính: Sau khi sửa tự động và người duyệt mô phỏng giải quyết hết các lỗi bắt buộc (`n_errors = 0`), vẫn còn 44 ảnh có cảnh báo chưa được duyệt do hàng đợi (130 ảnh) vượt quá ngân sách duyệt của người (80 ảnh); tỉ lệ ảnh còn cảnh báo là 21.67% (44/203 ảnh), vượt ngưỡng cho phép 10.00% của cửa chặn.

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (tổng hợp trên 203 ảnh được quét sau cửa vào):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| BAD_CLASS_ID | 6 dòng | Máy (autofix) | ID ngoài dải [0, 3], máy xoá dòng vi phạm an toàn |
| BAD_CLASS_NAME | 2 (data.yaml) | Máy (autofix) | Sai chuẩn tên lớp ('Person', 'Bus'), máy chuẩn hoá lại theo config |
| BAD_FORMAT | 3 dòng | Máy (autofix) | Thiếu cột hoặc chứa nan/inf, không thể cứu vãn nên máy xoá dòng |
| BAD_SIZE | 3 ảnh | Máy (intake) | Cạnh ngắn < 250px không đạt chuẩn intake, loại bỏ ảnh |
| BOX_OUT_OF_IMAGE | 8 dòng | Máy (autofix) | Box tràn viền được máy cắt xén về [0, 1] bảo toàn vật thể |
| BOX_ZERO | 4 dòng | Máy (autofix) | Chiều rộng hoặc cao <= 0 không có diện tích, máy xoá dòng |
| CORRUPT_IMAGE | 2 ảnh | Máy (intake) | File ảnh hỏng không mở được bằng thư viện ảnh, loại bỏ |
| DUP_BOX | 7 dòng | Máy (autofix) | Trùng lớp và toạ độ với box trước (IoU > 0.9), máy xoá dòng sau |
| DUP_IMAGE_EXACT | 8 ảnh | Máy (intake) | Trùng từng byte (md5), loại bỏ ảnh trùng lặp sau |
| DUP_IMAGE_NEAR | 3 ảnh | Máy (intake) | Trùng gần đúng qua perceptual hash (dist <= 8), loại bỏ |
| LEAK_TEST | 5 ảnh | Máy (intake) | Trùng với kho test/gold_val gây rò rỉ dữ liệu, loại bỏ ngay |
| MISSING_LABEL_FILE | 6 ảnh | Người (hàng đợi) | Máy không thể tự bịa nhãn; đánh dấu needs_label đẩy lên đầu hàng đợi người gán |
| BOX_HUGE | 3 dòng | Người (hàng đợi) | Cảnh báo box chiếm > 95% diện tích, cần người xem có phải gán bao cả nền không |
| BOX_TINY | 6 dòng | Người (hàng đợi) | Cảnh báo cạnh ngắn < 12px, cần người xác nhận vật có cần nhận diện không |
| CLASS_RARE | 4 cảnh báo | Máy (autofix gián tiếp) | Cảnh báo cấp dataset cho các ID lạ (-1, 4, 7, 93) có ít box; tự hết khi autofix xoá dòng BAD_CLASS_ID |
| EMPTY_LABEL | 12 ảnh | Người (hàng đợi) | File nhãn rỗng, cần người xác nhận là ảnh nền (background) hay sót nhãn |
| POSSIBLE_FALSE_POS | 25 dòng | Người (hàng đợi) | Nhãn không khớp dự đoán của model, cần người kiểm tra có gán thừa không |
| POSSIBLE_LOOSE_BOX | 31 dòng | Người (hàng đợi) | Box lệch/lỏng so với model (IoU < 0.5), cần người chỉnh lại viền |
| POSSIBLE_MISSING | 68 dòng | Người (hàng đợi) | Model phát hiện vật nhưng nhãn thiếu, cần người bổ sung box |
| POSSIBLE_WRONG_CLASS | 18 dòng | Người (hàng đợi) | Model nghi ngờ nhầm lẫn lớp (car/truck/bus/person), chỉ người mới quyết định đúng |

- **Vì sao `05_review_queue.csv` xếp ảnh đầu hàng như vậy?**: Hàng đợi được xếp theo điểm số ưu tiên `priority` tính từ trọng số các mã lỗi. Ảnh đầu hàng (`img_0020`, `img_0185`) có điểm cao nhất (> 10) vì vừa dính lỗi bắt buộc vừa có nhiều cảnh báo ngữ nghĩa nghiêm trọng. Ngay sau đó là 6 ảnh hoàn toàn thiếu file nhãn (`NEEDS_LABEL`: `img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219` với priority 10.0) vì nếu người không gán nhãn thì pipeline chắc chắn bị Rework. Tiếp theo là các ảnh có cảnh báo `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS` với độ tin cậy model cao.
- **Hiệu quả duyệt với ngân sách 80 ảnh**: Đối chiếu danh sách lỗi v1 với 80 ảnh được duyệt trong `06_review_log.csv`:
  * Người đã gán nhãn cho 100% ảnh thiếu nhãn (6/6 ảnh `NEEDS_LABEL`).
  * Về các cảnh báo ngữ nghĩa: người đã xem xét 18/18 lượt `POSSIBLE_WRONG_CLASS` (100%), 59/68 lượt `POSSIBLE_MISSING` (86.8%), 16/31 lượt `POSSIBLE_LOOSE_BOX` (51.6%), và 13/25 lượt `POSSIBLE_FALSE_POS` (52.0%).
  * Tổng cộng người đã rà soát **106 lượt cảnh báo ngữ nghĩa** (trên 80 ảnh đã duyệt). Lưu ý: đây là số lượt cảnh báo được mắt người kiểm tra, không đồng nghĩa với việc toàn bộ 106 lượt đều là lỗi thật.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 8 | 1.00 / 0.50 → 1.00 / 0.67 | Lỗi tự động xoá ảnh nên ưu tiên Precision 1.00 để không xoá nhầm ảnh sạch. Tăng dist lên 8 giúp tăng Recall từ 0.50 lên 0.67 (bắt thêm ảnh biến đổi mức 1). |
| `second_opinion.conf` | 0.25 | 0.50 | 0.50 / 1.00 → 0.57 / 1.00 *(xem đánh đổi)* | Tăng conf từ 0.25 lên 0.50 giúp tăng Precision của POSSIBLE_MISSING từ 0.50 lên 0.57 và giữ Recall 1.00 trên calib. Đánh đổi: Recall của POSSIBLE_LOOSE_BOX giảm từ 0.40 xuống 0.20. Ta chấp nhận vì cần ưu tiên giảm báo động giả tràn hàng đợi duyệt 80 ảnh. |

- **Một chỗ calibration có thể đánh lừa bạn (kèm bằng chứng)**:
  Tập calib chỉ có 39 ảnh nhân tạo. Trong bảng sweep, `duplicates.phash_dist = 16` cho kết quả đẹp nhất trên calib (Recall = 0.83, F1 = 0.91). Tuy nhiên, khi kiểm chứng trên dữ liệu thật (lô raw 224 ảnh), ngưỡng 16 coi các ảnh khác nhau là trùng (ví dụ `img_0011` có 1 người bị coi là trùng với `img_0008` có 2 người do khoảng cách phash = 16). Nguy hiểm hơn, nó đánh nhầm **6 ảnh train sạch** thành `LEAK_TEST` (`img_0013`, `img_0017`, `img_0021`, `img_0033`, `img_0038`, `img_0115`) dẫn đến việc tự động xoá oan mất 10 ảnh hữu ích của tập train. Vì vậy, tối ưu F1 trên tập calib nhỏ mà không kiểm chứng trên dữ liệu thật sẽ dẫn đến việc loại nhầm dữ liệu tốt.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
- **(a) Chứng minh gate chặn đúng**: Chạy thử nghiệm ngắt ngân sách người duyệt:
  `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`
  Kết quả: Do ngân sách duyệt bằng 0, 6 ảnh thiếu nhãn không có người gán nên lỗi `MISSING_LABEL_FILE` còn nguyên. Cửa chặn gate trả về kết luận **REWORK** (`Còn 6 lỗi bắt buộc chưa được giải quyết`), trả mã thoát 20, và pipeline thông báo `KHÔNG xuất: còn lỗi bắt buộc (Rework) — trả về bước 3`, thư mục `work/exp_nb` hoàn toàn không có dataset nào được tạo. Điều này chứng minh cửa chặn hoạt động độc lập và thực sự ngăn chặn dữ liệu hỏng lọt ra ngoài.
- **(b) 3 điểm mù pipeline không bắt được (kèm bằng chứng cụ thể)**:
  1. *Box lỏng nhẹ*: Với `iou_loose = 0.50`, box có IoU $\in [0.50, 0.60]$ không bị cảnh báo. Bằng chứng thực tế: Tại ảnh `img_0043` (lớp person), model dự đoán box person với conf 0.72 có IoU = 0.581 với nhãn. Do $0.581 \ge 0.50$, pipeline coi là đạt chuẩn và không gắn cờ `POSSIBLE_LOOSE_BOX`, dù viền box thực tế vẫn lệch đáng kể so với dự đoán của model.
  2. *Ảnh trùng bị biến đổi nặng*: Với `phash_dist = 8`, những ảnh biến đổi mạnh có khoảng cách Hamming phash > 8 sẽ bị bỏ sót. Bằng chứng thực tế: Trong tập calib, ảnh `calib_038` (biến đổi mức 4 từ `calib_024`) có khoảng cách phash là 18. Do $18 > 8$, bước intake bỏ sót hoàn toàn ca này.
  3. *Lỗi ngữ nghĩa tinh vi mà model cũng nhầm*: Phân biệt giữa xe tải nhỏ (pickup/truck) và xe con gầm cao (SUV/car). Bằng chứng thực tế: Nếu cả nhãn lẫn model yolo26l đều nhầm xe tải nhỏ thành `car` thì `second_opinion` thấy hai bên đồng thuận (`agreement`) và bỏ qua không gắn cờ.

## 5. Train: raw vs clean
Dán bảng kết quả thực tế từ `submission/results/comparison.md` (huấn luyện yolo26n, 20 epochs, 2 seeds ngẫu nhiên trên Google Colab T4):

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 203 | 2 | 0.695 ± 0.010 | 0.482 ± 0.007 | 0.726 ± 0.005 | 0.619 ± 0.016 |

Chênh mAP50 (clean − raw) = **-0.031**.

- **So sánh với độ lệch chuẩn giữa các seed**:
  Độ lệch chuẩn giữa các seed ở raw là $0.0002$, ở clean là $0.0095$. Chênh lệch mAP50 giảm $0.031$ ($3.1\%$) lớn hơn độ nhiễu ngẫu nhiên giữa các seed.
- **Kết luận trung thực và các giả thuyết giải thích**:
  Chưa thể kết luận dữ liệu clean kém hơn raw, mà sự chênh lệch này có thể đến từ các nguyên nhân cần kiểm chứng sau:
  1. *Giả thuyết 1 (Rò rỉ tập test)*: Báo cáo `01_intake.txt` cho thấy lô `raw` chứa **5 ảnh trùng hoàn toàn với tập test 100 ảnh** (`img_0049`, `img_0101`, `img_0167`, `img_0174`, `img_0221`). Việc rò rỉ 5% đề thi vào tập train có thể góp phần làm điểm mAP của raw cao hơn. Bản clean đã loại bỏ 5 ảnh này, trả về kết quả đánh giá khách quan hơn.
  2. *Giả thuyết 2 (Số lượng ảnh huấn luyện giảm 10%)*: Dataset clean chỉ còn 203 ảnh (ít hơn raw 21 ảnh bị loại ở intake). Trong tập dữ liệu quy mô nhỏ (~200 ảnh), việc mất 21 ảnh huấn luyện có thể làm giảm độ bao phủ của dữ liệu khi train 20 epoch.
  3. *Giả thuyết 3 (Kích thước tập test nhỏ)*: Tập test chỉ gồm 100 ảnh, khiến các chỉ số mAP nhạy cảm cao với biến động của từng ảnh riêng lẻ.
- **Cách kiểm chứng tiếp theo**: Đánh giá cả 2 model trên một tập test mở rộng hoàn toàn độc lập (không có bất kỳ ảnh nào trùng lặp với cả 2 tập), hoặc thu thập thêm dữ liệu sạch bù vào để clean có đủ 224 ảnh ngang bằng raw.

## 6. Quyết định và ghi chú AI
- **(a) Quyết định cuối cùng**: Giữ nguyên quyết định **HOLD**. Mặc dù dữ liệu đã sạch lỗi bắt buộc và loại bỏ rò rỉ tập test, tỉ lệ ảnh còn nghi vấn ngữ nghĩa chưa được duyệt là $21.67\% \ge 10.00\%$. Để chuyển thành **Release**, dự án cần cấp thêm ngân sách để người duyệt thêm tối thiểu **24 ảnh** trong số 44 ảnh còn lại: $(44 - 24) / 203 \approx 9.85\% < 10.00\%$ (với điều kiện xử lý hết cảnh báo của 24 ảnh đó và không phát sinh lỗi mới).
- **(b) Ghi chú dùng AI**:
  1. *Prompt chính*: Áp dụng mẫu 4 ý từ `docs/PROMPTING.md` (xác định định dạng YOLO, quy tắc phân loại ERROR/WARN, đọc ngưỡng từ `cfg` và cấm sửa dữ liệu gốc).
  2. *Cách kiểm tra*: Đọc lướt code để xác nhận không xoá/sửa file raw bừa bãi; chạy unit test riêng cho từng file và kiểm tra toàn bộ 79 tests với `pytest`.
  3. *Một lần AI sai và cách sửa*: Khi viết `autofix.py`, ban đầu nếu xoá dòng nhãn ngay khi gặp lỗi sẽ làm lệch số thứ tự `line_no` của các dòng bên dưới; đã sửa lại bằng cách gom toàn bộ lỗi theo file rồi ghi lại một lần duy nhất, kết hợp ưu tiên `drop_line` trước `clip_box`.
