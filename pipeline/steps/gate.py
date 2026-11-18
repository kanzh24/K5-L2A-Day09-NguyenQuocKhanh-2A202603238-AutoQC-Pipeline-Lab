"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems_set = set(image_stems)
    reviewed_set = set(reviewed) if reviewed else set()

    # 1. Đếm số lỗi bắt buộc (ERROR): không bao giờ được bỏ qua, kể cả ở ảnh đã reviewed
    n_errors = sum(1 for i in issues if i.severity == ERROR)

    # 2. Đếm số ẢNH khác nhau có cảnh báo (WARN)
    # Chỉ tính ảnh thuộc image_stems (loại <dataset>, data.yaml) và chưa được reviewed
    warn_images = {
        i.image for i in issues
        if i.severity == WARN and i.image in stems_set and i.image not in reviewed_set
    }
    n_warn_images = len(warn_images)
    n_images = len(image_stems)

    # Mẫu số là tổng số ảnh, tránh chia cho 0 nếu tập rỗng
    warn_ratio = round(n_warn_images / n_images, 4) if n_images > 0 else 0.0
    warn_ratio_hold = cfg.get("gate", {}).get("warn_ratio_hold", 0.10)

    reasons = []
    if n_errors > 0:
        decision = "Rework"
        reasons.append(f"Còn {n_errors} lỗi bắt buộc chưa được giải quyết")
    elif warn_ratio >= warn_ratio_hold:
        decision = "Hold"
        reasons.append(f"Tỉ lệ ảnh có cảnh báo {warn_ratio:.2%} ({n_warn_images}/{n_images} ảnh) >= ngưỡng {warn_ratio_hold:.2%}")
    else:
        decision = "Release"
        if n_images == 0:
            reasons.append("Tập dữ liệu rỗng (0 ảnh), không có lỗi")
        elif n_warn_images == 0:
            reasons.append(f"Không còn lỗi hay cảnh báo nào trên {n_images} ảnh")
        else:
            reasons.append(f"Tỉ lệ cảnh báo {warn_ratio:.2%} ({n_warn_images}/{n_images} ảnh) nằm trong ngưỡng an toàn < {warn_ratio_hold:.2%}")

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
