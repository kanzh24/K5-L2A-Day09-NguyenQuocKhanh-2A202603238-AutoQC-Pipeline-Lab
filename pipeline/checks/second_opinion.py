"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg.get("second_opinion", {})
    conf_thresh = so_cfg.get("conf", 0.5)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.1)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.5)

    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem

        # Bỏ qua ảnh không có file nhãn hoặc không có trong preds
        if not ds.label_path(stem).exists() or stem not in preds:
            continue

        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue

        im_size = ds.image_size(stem)
        img_w, img_h = im_size if im_size is not None else (1, 1)

        # Lấy danh sách các dòng nhãn hợp lệ (giữ số dòng gốc)
        valid_labels = []
        for line_no, raw_line in raw_lines:
            try:
                cls_id, cx, cy, w, h = parse_yolo_line(raw_line)
            except ValueError:
                continue
            if 0 <= cls_id < len(ds.classes) and w > 0 and h > 0:
                valid_labels.append((line_no, cls_id, (cx, cy, w, h)))

        img_preds = preds.get(stem, [])

        # 1. Lọc các dự đoán cho kiểm tra MISSING / LOOSE_BOX / WRONG_CLASS
        # conf >= conf VÀ diện tích px >= min_area_px
        filtered_preds = []
        for r in img_preds:
            p_cls, p_conf, p_cx, p_cy, p_w, p_h = r
            area_px = (p_w * img_w) * (p_h * img_h)
            if p_conf >= conf_thresh and area_px >= min_area_px:
                filtered_preds.append(r)

        # Kiểm tra từng dự đoán theo thứ tự trong preds[stem]
        for r in filtered_preds:
            p_cls, p_conf, p_cx, p_cy, p_w, p_h = r
            p_box = (p_cx, p_cy, p_w, p_h)

            # Tìm các nhãn ứng viên có IoU >= iou_missing
            cands = []
            for line_no, l_cls, l_box in valid_labels:
                iou = iou_xywh(p_box, l_box)
                if iou >= iou_missing:
                    cands.append((iou, l_cls, line_no, l_box))

            if not cands:
                # Không có box nhãn nào khớp
                issues.append(Issue(
                    check="second_opinion",
                    severity=WARN,
                    code="POSSIBLE_MISSING",
                    image=stem,
                    message=f"model dự đoán {ds.classes[p_cls]} (conf={p_conf:.2f}) nhưng nhãn thiếu",
                    line=None,
                    extra={"conf": p_conf, "class": p_cls},
                ))
            else:
                same_cands = [c for c in cands if c[1] == p_cls]
                if same_cands:
                    best_same_iou = max(c[0] for c in same_cands)
                    if best_same_iou < iou_loose:
                        # Đúng lớp nhưng box lỏng/lệch
                        issues.append(Issue(
                            check="second_opinion",
                            severity=WARN,
                            code="POSSIBLE_LOOSE_BOX",
                            image=stem,
                            message=f"box lỏng/lệch so với model (IoU={best_same_iou:.2f} < {iou_loose})",
                            line=None,
                            extra={"conf": p_conf, "iou": round(best_same_iou, 4), "class": p_cls},
                        ))
                    # Nếu best_same_iou >= iou_loose: nhãn đúng lớp đã phủ vật này -> không cờ
                else:
                    diff_cands = [c for c in cands if c[1] != p_cls]
                    best_diff_iou = max(c[0] for c in diff_cands)
                    if best_diff_iou >= iou_match:
                        # Khác lớp và khớp rõ ràng
                        issues.append(Issue(
                            check="second_opinion",
                            severity=WARN,
                            code="POSSIBLE_WRONG_CLASS",
                            image=stem,
                            message=f"nghi ngờ sai lớp: model đoán {ds.classes[p_cls]} (conf={p_conf:.2f}), nhãn lớp khác (IoU={best_diff_iou:.2f})",
                            line=None,
                            extra={"conf": p_conf, "iou": round(best_diff_iou, 4), "pred_class": p_cls},
                        ))
                    # Nếu best_diff_iou nằm trong [iou_missing, iou_match): mơ hồ -> không cờ

        # 2. Kiểm tra POSSIBLE_FALSE_POS cho từng dòng nhãn
        # Lọc dự đoán: conf >= fp_conf (KHÔNG lọc diện tích min_area_px)
        fp_preds = [r for r in img_preds if r[1] >= fp_conf]

        for line_no, l_cls, l_box in valid_labels:
            matched = any(iou_xywh(l_box, (r[2], r[3], r[4], r[5])) >= iou_missing for r in fp_preds)
            if not matched:
                issues.append(Issue(
                    check="second_opinion",
                    severity=WARN,
                    code="POSSIBLE_FALSE_POS",
                    image=stem,
                    message=f"nhãn dòng {line_no} không khớp dự đoán nào của model (conf >= {fp_conf})",
                    line=line_no,
                    extra={"line": line_no},
                ))

    return issues
