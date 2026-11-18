"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_IMAGE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def fix(ds, issues, cfg):
    fixes = []
    # Chỉ xử lý các lỗi bắt buộc (severity == ERROR)
    err_issues = [i for i in issues if i.severity == ERROR]
    if not err_issues:
        return fixes

    removed_stems = set()
    needs_label_stems = set()
    renamed_yaml = False

    # 1. Xử lý xoá ảnh (remove_image)
    for i in err_issues:
        if i.code in REMOVE_IMAGE_CODES or i.code.startswith("DUP_IMAGE_"):
            stem = i.image
            if stem not in removed_stems:
                removed_stems.add(stem)
                img_p = ds.image_path(stem)
                if img_p and img_p.exists():
                    img_p.unlink()
                lab_p = ds.label_path(stem)
                if lab_p.exists():
                    lab_p.unlink()
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "remove_image",
                    "before": f"tồn tại ({i.code})",
                    "after": "(đã xoá)",
                })

    # 2. Xử lý ảnh thiếu file nhãn (needs_label)
    for i in err_issues:
        if i.code == "MISSING_LABEL_FILE":
            stem = i.image
            if stem not in removed_stems and stem not in needs_label_stems:
                needs_label_stems.add(stem)
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 3. Xử lý cập nhật tên lớp trong data.yaml (rename_classes)
    for i in err_issues:
        if i.code == "BAD_CLASS_NAME" and not renamed_yaml:
            renamed_yaml = True
            old_names = ds.yaml_names()
            d = {}
            if ds.yaml_path.exists():
                d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            d["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": str(old_names),
                "after": str(cfg["classes"]),
            })

    # 4. Gom và xử lý các lỗi cấp dòng trong file nhãn (drop_line, clip_box)
    line_issues_by_stem = defaultdict(lambda: defaultdict(list))
    for i in err_issues:
        if i.image in removed_stems or i.line is None:
            continue
        if i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE":
            line_issues_by_stem[i.image][i.line].append(i)

    # Duyệt theo từng file để sửa một lần, tránh lệch chỉ số dòng
    for stem, issues_by_line in line_issues_by_stem.items():
        lab_p = ds.label_path(stem)
        if not lab_p.exists():
            continue

        raw_lines = lab_p.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = []

        for line_no, raw_line in enumerate(raw_lines, 1):
            if line_no not in issues_by_line:
                new_lines.append(raw_line)
                continue

            current_issues = issues_by_line[line_no]
            has_drop = any(ci.code in DROP_CODES for ci in current_issues)
            has_clip = any(ci.code == "BOX_OUT_OF_IMAGE" for ci in current_issues)

            if has_drop:
                # Xoá dòng ưu tiên hơn cắt box
                fixes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": raw_line,
                    "after": "(xoá dòng)",
                })
            elif has_clip:
                # Cắt box về [0, 1]
                try:
                    cls_id, cx, cy, w, h = parse_yolo_line(raw_line)
                    x1 = cx - w / 2.0
                    x2 = cx + w / 2.0
                    y1 = cy - h / 2.0
                    y2 = cy + h / 2.0

                    nx1 = max(0.0, min(1.0, x1))
                    nx2 = max(0.0, min(1.0, x2))
                    ny1 = max(0.0, min(1.0, y1))
                    ny2 = max(0.0, min(1.0, y2))

                    nw = nx2 - nx1
                    nh = ny2 - ny1

                    if nw <= 0.0 or nh <= 0.0:
                        # Box nằm hoàn toàn ngoài ảnh -> xoá dòng
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": raw_line,
                            "after": "(xoá dòng)",
                        })
                    else:
                        ncx = (nx1 + nx2) / 2.0
                        ncy = (ny1 + ny2) / 2.0
                        clipped_line = f"{cls_id} {ncx:.6f} {ncy:.6f} {nw:.6f} {nh:.6f}"
                        new_lines.append(clipped_line)
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": raw_line,
                            "after": clipped_line,
                        })
                except Exception:
                    fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": raw_line,
                        "after": "(xoá dòng)",
                    })
            else:
                new_lines.append(raw_line)

        # Ghi lại nội dung file nhãn sau khi sửa
        lab_p.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")

    return fixes
