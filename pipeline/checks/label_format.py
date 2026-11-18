"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    issues = []
    lf_cfg = cfg.get("label_format", {})
    overflow_tol = lf_cfg.get("overflow_tol", 0.002)
    min_box_px = lf_cfg.get("min_box_px", 12)
    max_box_frac = lf_cfg.get("max_box_frac", 0.95)
    dup_box_iou = lf_cfg.get("dup_box_iou", 0.9)
    num_classes = len(ds.classes)

    for lab_path in ds.label_files():
        stem = lab_path.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue

        im_size = ds.image_size(stem)
        prev_boxes = []  # list of (cls_id, (cx, cy, w, h))

        for line_no, raw_line in lines:
            # 1. BAD_FORMAT
            try:
                cls_id, cx, cy, w, h = parse_yolo_line(raw_line)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng {line_no} sai định dạng: {e}", line=line_no))
                continue

            # 2. BAD_CLASS_ID
            if cls_id < 0 or cls_id >= num_classes:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls_id} ngoài 0..{num_classes - 1}", line=line_no))
                continue

            # 3. BOX_ZERO
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"kích thước w={w}, h={h} <= 0", line=line_no))
                continue

            # Dòng hợp lệ về cú pháp -> kiểm tra hình học
            box = (cx, cy, w, h)

            # 4. BOX_OUT_OF_IMAGE
            x1 = cx - w / 2.0
            y1 = cy - h / 2.0
            x2 = cx + w / 2.0
            y2 = cy + h / 2.0
            overflow = max(0.0, -x1, -y1, x2 - 1.0, y2 - 1.0)
            if overflow > overflow_tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"mép box tràn ảnh: {overflow:.4f}", line=line_no, extra={"overflow": overflow}))

            # 5. DUP_BOX (cùng lớp với dòng trước đó và IoU > dup_box_iou)
            for prev_cls, prev_box in prev_boxes:
                if prev_cls == cls_id and iou_xywh(box, prev_box) > dup_box_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"trùng box với dòng trước đó (IoU > {dup_box_iou})", line=line_no))
                    break
            prev_boxes.append((cls_id, box))

            # 6. BOX_TINY
            if im_size is not None:
                img_w, img_h = im_size
                short_side_px = min(w * img_w, h * img_h)
                if short_side_px < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"cạnh ngắn {short_side_px:.1f}px < {min_box_px}px", line=line_no))

            # 7. BOX_HUGE
            if w * h > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"diện tích {w * h:.3f} > {max_box_frac}", line=line_no))

    return issues
