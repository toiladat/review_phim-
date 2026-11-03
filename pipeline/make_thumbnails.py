# -*- coding: utf-8 -*-
"""Generate YouTube 16:9 thumbnails and 9:16 vertical cover in output/.
Configure THUMB1_CFG, THUMB2_CFG, and THUMB_V_CFG for each new episode.
"""
import glob
import json
import os
import cv2
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)
_inp = os.path.join(ROOT, "input")
_cands = sorted(glob.glob(os.path.join(_inp, "*.mp4")))
SRC_MP4 = os.path.join(_inp, "1.mp4") if os.path.exists(os.path.join(_inp, "1.mp4")) else (_cands[0] if _cands else os.path.join(ROOT, "1.mp4"))

# ------------------------------------------------------------------------------
# Episode Thumbnail Config (update per episode)
# ------------------------------------------------------------------------------
THUMB1_CFG = {
    "left_beat": 61,
    "right_beat": 4,
    "badge": "3 NĂM LÀM DÂU HÀO MÔN",
    "line1": "TẶNG VỢ HÀNG KHUYẾN MÃI?",
    "line2": "LY HÔN THÀNH TỶ PHÚ!",
}

THUMB2_CFG = {
    "left_src_sec": 3718.0,
    "mid_beat": 13,
    "right_beat": 33,
    "badge": "VẢ MẶT 60 TỶ TỆ",
    "line1": "TIỂU TAM ĂN CẮP BẢN VẼ",
    "line2": "TỔNG TÀI RA MẶT BẢO VỆ!",
}


def enhance_img(pil_img, contrast=1.14, sat=1.18, sharp=1.35, bright=1.04):
    pil_img = ImageEnhance.Brightness(pil_img).enhance(bright)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(contrast)
    pil_img = ImageEnhance.Color(pil_img).enhance(sat)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(sharp)
    return pil_img


def load_vn_font(size):
    for fp in [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
    ]:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def draw_text_with_stroke(
    canvas,
    xy,
    text,
    font,
    fill,
    stroke_fill=(0, 0, 0),
    stroke_width=8,
    shadow_offset=(5, 6),
):
    sx, sy = xy[0] + shadow_offset[0], xy[1] + shadow_offset[1]
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    sd.text(
        (sx, sy),
        text,
        font=font,
        fill=(0, 0, 0, 215),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 215),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=5))
    canvas.alpha_composite(shadow_layer)
    d = ImageDraw.Draw(canvas)
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def draw_badge(canvas, text, x=28, y=24, bg_color=(215, 20, 25, 245)):
    if not text:
        return
    font_badge = load_vn_font(33)
    d_tmp = ImageDraw.Draw(canvas)
    tw = d_tmp.textlength(text, font=font_badge)
    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle(
        [x, y, int(x + tw + 44), y + 66],
        radius=14,
        fill=bg_color,
        outline=(255, 225, 0, 255),
        width=4,
    )
    canvas.alpha_composite(badge)
    draw_text_with_stroke(
        canvas,
        (x + 22, y + 12),
        text,
        font_badge,
        fill=(255, 255, 255),
        stroke_width=4,
        shadow_offset=(2, 3),
    )


def main():
    plan = json.load(open(os.path.join(ROOT, "work", "plan.json"), encoding="utf-8"))
    cap_src = cv2.VideoCapture(SRC_MP4)
    cap_out = cv2.VideoCapture(os.path.join(OUT, "review_vi.mp4"))

    t_acc = 0.0
    mids = {}
    for p in plan:
        mids[p["i"] + 1] = t_acc + p["dur"] * 0.5
        t_acc += p["dur"]

    def get_src_frame(t):
        cap_src.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, img = cap_src.read()
        if not ok:
            raise RuntimeError(f"Failed to read 1.mp4 at {t}s")
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def get_beat_frame(b):
        cap_out.set(cv2.CAP_PROP_POS_MSEC, mids[b] * 1000.0)
        ok, img = cap_out.read()
        if not ok:
            raise RuntimeError(f"Failed to read review_vi.mp4 at beat {b}")
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    W, H = 1280, 720

    # ==============================================================================
    # THUMBNAIL 1 (1280x720): Split 2-panel
    # ==============================================================================
    f_left = Image.fromarray(get_beat_frame(THUMB1_CFG["left_beat"]))
    f_right = Image.fromarray(get_beat_frame(THUMB1_CFG["right_beat"]))
    fw, fh = f_left.size
    crop_h = int(fh * 0.54) if fh > fw else fh

    left_crop = enhance_img(
        f_left.crop((0, int(fh * 0.03), fw, crop_h)).resize((680, 720), Image.LANCZOS)
    )
    right_crop = enhance_img(
        f_right.crop((0, int(fh * 0.01), fw, crop_h)).resize((680, 720), Image.LANCZOS),
        bright=1.06,
        sat=1.22,
    )

    thumb1 = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    thumb1.paste(left_crop, (0, 0))

    mask_r = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask_r)
    md.polygon([(645, 0), (W, 0), (W, H), (575, H)], fill=255)
    mask_r = mask_r.filter(ImageFilter.GaussianBlur(radius=4))
    right_full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    right_full.paste(right_crop, (600, 0))
    thumb1 = Image.composite(right_full, thumb1, mask_r)

    slash = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(slash)
    sd.line([(645, -10), (575, H + 10)], fill=(255, 70, 30, 220), width=14)
    slash = slash.filter(ImageFilter.GaussianBlur(radius=6))
    thumb1.alpha_composite(slash)
    sd2 = ImageDraw.Draw(thumb1)
    sd2.line([(645, -10), (575, H + 10)], fill=(255, 235, 120, 255), width=5)

    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(H - 295, H):
        p = (y - (H - 295)) / 295.0
        a = int(238 * (p ** 1.35))
        gd.line([(0, y), (W, y)], fill=(8, 6, 12, a))
    thumb1.alpha_composite(grad)

    draw_badge(thumb1, THUMB1_CFG["badge"])

    font_l1 = load_vn_font(65)
    font_l2 = load_vn_font(74)
    t1, t2 = THUMB1_CFG["line1"], THUMB1_CFG["line2"]
    d_tmp = ImageDraw.Draw(thumb1)
    w1 = d_tmp.textlength(t1, font=font_l1)
    w2 = d_tmp.textlength(t2, font=font_l2)
    draw_text_with_stroke(
        thumb1,
        (int((W - w1) // 2), 500),
        t1,
        font_l1,
        fill=(255, 230, 0),
        stroke_width=10,
        shadow_offset=(5, 7),
    )
    draw_text_with_stroke(
        thumb1,
        (int((W - w2) // 2), 592),
        t2,
        font_l2,
        fill=(255, 255, 255),
        stroke_fill=(190, 15, 20),
        stroke_width=11,
        shadow_offset=(5, 7),
    )
    thumb1.convert("RGB").save(os.path.join(OUT, "thumbnail_yt_1.jpg"), "JPEG", quality=94)

    # ==============================================================================
    # THUMBNAIL 2 (1280x720): 3-panel Plot Twist
    # ==============================================================================
    f_shock = Image.fromarray(get_src_frame(THUMB2_CFG["left_src_sec"]))
    f_mom = Image.fromarray(
        get_beat_frame(THUMB2_CFG["mid_beat"])
        if "mid_beat" in THUMB2_CFG
        else get_src_frame(THUMB2_CFG["mid_src_sec"])
    )
    f_b14 = Image.fromarray(get_beat_frame(THUMB2_CFG["right_beat"]))

    p1 = enhance_img(
        f_shock.crop((0, int(fh * 0.05), fw, crop_h)).resize((430, 720), Image.LANCZOS),
        sat=1.15,
    )
    p2 = enhance_img(
        f_mom.crop((0, int(fh * 0.05), fw, crop_h)).resize((430, 720), Image.LANCZOS),
        contrast=1.18,
    )
    p3 = enhance_img(
        f_b14.crop((0, int(fh * 0.02), fw, crop_h)).resize((440, 720), Image.LANCZOS),
        sat=1.22,
        bright=1.08,
    )

    thumb2 = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    thumb2.paste(p1, (0, 0))
    thumb2.paste(p2, (425, 0))
    thumb2.paste(p3, (845, 0))

    div = ImageDraw.Draw(thumb2)
    div.line([(425, 0), (425, H)], fill=(255, 215, 0, 255), width=5)
    div.line([(845, 0), (845, H)], fill=(255, 215, 0, 255), width=5)
    thumb2.alpha_composite(grad)

    draw_badge(thumb2, THUMB2_CFG["badge"], bg_color=(200, 15, 20, 245))

    t2_1, t2_2 = THUMB2_CFG["line1"], THUMB2_CFG["line2"]
    font2_l1 = load_vn_font(60)
    font2_l2 = load_vn_font(72)
    w2_1 = d_tmp.textlength(t2_1, font=font2_l1)
    w2_2 = d_tmp.textlength(t2_2, font=font2_l2)
    draw_text_with_stroke(
        thumb2,
        (int((W - w2_1) // 2), 505),
        t2_1,
        font2_l1,
        fill=(255, 255, 255),
        stroke_width=10,
        shadow_offset=(5, 7),
    )
    draw_text_with_stroke(
        thumb2,
        (int((W - w2_2) // 2), 592),
        t2_2,
        font2_l2,
        fill=(255, 230, 0),
        stroke_fill=(185, 10, 15),
        stroke_width=11,
        shadow_offset=(5, 7),
    )
    thumb2.convert("RGB").save(os.path.join(OUT, "thumbnail_yt_2.jpg"), "JPEG", quality=94)

    # ==============================================================================
    # THUMBNAIL 3 (1080x1920): Vertical Cover for Shorts / TikTok / Reels
    # ==============================================================================
    VW, VH = 1080, 1920
    top_half = enhance_img(
        f_left.crop((0, int(fh * 0.03), fw, crop_h)).resize((VW, 960), Image.LANCZOS)
    )
    bot_half = enhance_img(
        f_right.crop((0, int(fh * 0.01), fw, crop_h)).resize((VW, 960), Image.LANCZOS),
        bright=1.06,
        sat=1.22,
    )

    thumb_v = Image.new("RGBA", (VW, VH), (0, 0, 0, 255))
    thumb_v.paste(top_half, (0, 0))
    thumb_v.paste(bot_half, (0, 960))

    vgrad = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    vgd = ImageDraw.Draw(vgrad)
    for y in range(740, 1200):
        dist = abs(y - 965) / 225.0
        a = int(max(0, 242 * (1.0 - dist ** 1.4)))
        vgd.line([(0, y), (VW, y)], fill=(10, 5, 12, a))
    thumb_v.alpha_composite(vgrad)

    font_v1 = load_vn_font(58)
    font_v2 = load_vn_font(68)
    vw1 = d_tmp.textlength(t1, font=font_v1)
    vw2 = d_tmp.textlength(t2, font=font_v2)
    draw_text_with_stroke(
        thumb_v,
        (int((VW - vw1) // 2), 880),
        t1,
        font_v1,
        fill=(255, 230, 0),
        stroke_width=10,
        shadow_offset=(5, 7),
    )
    draw_text_with_stroke(
        thumb_v,
        (int((VW - vw2) // 2), 972),
        t2,
        font_v2,
        fill=(255, 255, 255),
        stroke_fill=(190, 15, 20),
        stroke_width=11,
        shadow_offset=(5, 7),
    )
    thumb_v.convert("RGB").save(os.path.join(OUT, "thumbnail_doc_9x16.jpg"), "JPEG", quality=94)
    print("Generated 3 UTF-8 thumbnails in output/")


if __name__ == "__main__":
    main()
