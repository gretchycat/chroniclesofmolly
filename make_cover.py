#!/usr/bin/env python3

import sys, os, yaml, re
from PIL import Image, ImageDraw, ImageFont
import cairosvg
import math

def hex_color(c, alpha=255):
    if isinstance(c, tuple): return c
    c = c.lstrip("#")
    lv = len(c)
    if lv == 6: return tuple(int(c[i:i+2], 16) for i in (0,2,4)) + (alpha,)
    if lv == 8: return tuple(int(c[i:i+2], 16) for i in (0,2,4,6))
    raise ValueError(f"Invalid color: {c}")

def color_svg(svg_path, output_path, color):
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_data = f.read()
    svg_data = re.sub(r'fill="[^"]*"', f'fill="{color}"', svg_data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_data)

def load_image(path, size=None):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.svg':
        png_path = path + '.tmp.png'
        cairosvg.svg2png(url=path, write_to=png_path, output_width=size[0], output_height=size[1])
        img = Image.open(png_path).convert("RGBA")
        os.remove(png_path)
    else:
        img = Image.open(path).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
    return img

def load_colored_svg(path, size, color_hex):
    temp_svg = path + ".color.svg"
    color_svg(path, temp_svg, color_hex)
    png_path = path + '.color.png'
    cairosvg.svg2png(url=temp_svg, write_to=png_path, output_width=size[0], output_height=size[1])
    img = Image.open(png_path).convert("RGBA")
    os.remove(temp_svg)
    os.remove(png_path)
    return img

def apply_texture(texture_path, size, mode='fill', alpha=1.0):
    tex = Image.open(texture_path).convert("RGBA")
    w, h = size
    if mode == "stretch":
        tex = tex.resize((w, h), Image.LANCZOS)
    elif mode == "fill":
        scale = max(w / tex.width, h / tex.height)
        tex = tex.resize((int(tex.width*scale), int(tex.height*scale)), Image.LANCZOS)
        x = (tex.width - w) // 2
        y = (tex.height - h) // 2
        tex = tex.crop((x, y, x + w, y + h))
    elif mode == "tile":
        timg = Image.new("RGBA", (w, h))
        for y in range(0, h, tex.height):
            for x in range(0, w, tex.width):
                timg.paste(tex, (x, y))
        tex = timg
    else:
        raise ValueError(f"Unknown texture mode: {mode}")
    if alpha < 1.0:
        alpha_mask = tex.split()[-1].point(lambda p: int(p * alpha))
        tex.putalpha(alpha_mask)
    return tex

def composite_colored_texture(canvas, mask, color, texture_path, tex_alpha=1.0, tex_mode='fill', position=(0,0)):
    w, h = mask.size
    color_img = Image.new("RGBA", (w, h), color)
    base = Image.new("RGBA", (w, h), (0,0,0,0))
    base.paste(color_img, (0,0), mask)
    tex = apply_texture(texture_path, (w, h), mode=tex_mode, alpha=tex_alpha)
    tex_masked = Image.new("RGBA", (w, h), (0,0,0,0))
    tex_masked.paste(tex, (0,0), mask)
    combined = Image.alpha_composite(base, tex_masked)
    layer = Image.new("RGBA", canvas.size, (0,0,0,0))
    layer.paste(combined, position, mask)
    return Image.alpha_composite(canvas, layer)

def fill_background(canvas, bg_img, mode, alpha=1.0):
    w, h = canvas.size
    layer = Image.new("RGBA", (w, h), (0,0,0,0))
    if mode == "stretch":
        img = bg_img.resize((w, h), Image.LANCZOS)
        layer.paste(img, (0, 0))
    elif mode == "tile":
        for y in range(0, h, bg_img.height):
            for x in range(0, w, bg_img.width):
                layer.paste(bg_img, (x, y))
    elif mode == "fill":
        scale = max(w / bg_img.width, h / bg_img.height)
        newsize = (int(bg_img.width * scale), int(bg_img.height * scale))
        img = bg_img.resize(newsize, Image.LANCZOS)
        x = (img.width - w) // 2
        y = (img.height - h) // 2
        img = img.crop((x, y, x + w, y + h))
        layer.paste(img, (0, 0))
    else:
        raise ValueError(f"Unknown background mode: {mode}")
    if alpha < 1.0:
        layer = layer.copy()
        layer.putalpha(int(255 * alpha))
    canvas.alpha_composite(layer)

def wrap_text(text, font, max_width, draw):
    # Word wrap: returns a list of lines fitting in max_width
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = current + (" " if current else "") + word
        width = draw.textlength(test, font=font)
        if width > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines

def render_justified_text_mask(text, font_path, initial_font_size, box, angle=0, spacing_mult=1.1):
    from PIL import Image, ImageDraw, ImageFont

    x, y, box_width, box_height = box

    # Helper: split text into lines, filling the width as much as possible.
    def fit_lines_to_width(text, font, box_width, draw):
        words = text.split()
        lines = []
        i = 0
        N = len(words)
        while i < N:
            j = i + 1
            last_good = j
            while j <= N:
                candidate = " ".join(words[i:j])
                w = draw.textlength(candidate, font=font)
                if w <= box_width:
                    last_good = j
                    j += 1
                else:
                    break
            lines.append(" ".join(words[i:last_good]))
            i = last_good
        return lines

    # Find font size to fit vertically
    font_size = initial_font_size
    while font_size >= 10:
        font = ImageFont.truetype(font_path, font_size)
        dummy_img = Image.new("L", (box_width, box_height), 0)
        dummy_draw = ImageDraw.Draw(dummy_img)
        lines = fit_lines_to_width(text, font, box_width, dummy_draw)
        # Line height by font, not image
        line_height = font.getmetrics()[0] + font.getmetrics()[1]
        total_height = int(len(lines) * line_height * spacing_mult)
        if total_height <= box_height:
            break
        font_size -= 2
    else:
        font = ImageFont.truetype(font_path, font_size)
        dummy_img = Image.new("L", (box_width, box_height), 0)
        dummy_draw = ImageDraw.Draw(dummy_img)
        lines = fit_lines_to_width(text, font, box_width, dummy_draw)
        line_height = font.getmetrics()[0] + font.getmetrics()[1]

    # Render
    mask = Image.new("L", (box_width, box_height), 0)
    y_cursor = 0
    for idx, line in enumerate(lines):
        hi_res_font = ImageFont.truetype(font_path, font.size * 2)
        # Buffer: wide and tall enough for any descenders.
        hi_w = box_width * 2
        hi_h = int((hi_res_font.getmetrics()[0] + hi_res_font.getmetrics()[1]) * 2)
        hi_img = Image.new("L", (hi_w, hi_h), 0)
        hi_draw = ImageDraw.Draw(hi_img)
        hi_draw.text((0, 0), line, font=hi_res_font, fill=255)
        # Crop actual text content (with pad)
        bbox_hi = hi_img.getbbox()
        if not bbox_hi:
            continue
        pad = 8
        l, t, r, b = bbox_hi
        l = max(l - pad, 0)
        t = max(t - pad, 0)
        r = min(r + pad, hi_w)
        b = min(b + pad, hi_h)
        hi_img = hi_img.crop((l, t, r, b))
        hi_line_w = hi_img.width

        # Last line: left-aligned, not stretched
        is_last_line = (idx == len(lines) - 1)
        if not is_last_line:
            # Scale to box_width exactly
            scaled_line = hi_img.resize((box_width, hi_img.height // 2), resample=Image.LANCZOS)
            mask.paste(scaled_line, (0, y_cursor))
        else:
            # Left-aligned, no scaling
            target_w = min(box_width, hi_img.width // 2)
            scaled_line = hi_img.resize((target_w, hi_img.height // 2), resample=Image.LANCZOS)
            mask.paste(scaled_line, (0, y_cursor))

        # Stack by font metrics, not image height
        line_height = font.getmetrics()[0] + font.getmetrics()[1]
        y_cursor += int(line_height * spacing_mult)

    if angle:
        mask = mask.rotate(angle, resample=Image.BICUBIC, center=(box_width // 2, box_height // 2))
    return mask

from PIL import Image, ImageDraw, ImageFont, ImageFilter

def draw_text_box(base_img, box_rect, text, font, font_color, box_cfg):
    # box_rect: (x, y, width, height)
    x, y, w, h = box_rect

    # Padding
    pad_x, pad_y = box_cfg.get('padding', [0, 0])

    # Calculate inner box for text (after padding)
    inner_box = (x + pad_x, y + pad_y, x + w - pad_x, y + h - pad_y)
    text_w = inner_box[2] - inner_box[0]
    text_h = inner_box[3] - inner_box[1]

    # Make box image for compositing
    box_img = Image.new("RGBA", (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(box_img)
    corner_radius = box_cfg.get('corner_radius', 0)

    # Draw background color (with alpha)
    bg = box_cfg.get('background', "#00000000")
    if isinstance(bg, str):
        bg_color = tuple(int(bg[i:i+2], 16) for i in (1, 3, 5)) + (int(bg[7:9], 16),) if len(bg)==9 else ImageColor.getrgb(bg) + (255,)
    else:
        bg_color = bg
    shape = [(0, 0), (w, h)]
    if corner_radius > 0:
        draw.rounded_rectangle(shape, fill=bg_color, radius=corner_radius)
    else:
        draw.rectangle(shape, fill=bg_color)

    # Draw texture (if present)
    if 'texture' in box_cfg:
        tex = Image.open(box_cfg['texture']).convert("RGBA")
        mode = box_cfg.get('texture_mode', 'tile')
        alpha = float(box_cfg.get('texture_alpha', 1.0))
        tex_box = Image.new("RGBA", (w, h), (0,0,0,0))
        if mode == 'tile':
            for i in range(0, w, tex.width):
                for j in range(0, h, tex.height):
                    tex_box.paste(tex, (i, j))
        elif mode == 'fill':
            tex_resized = tex.resize((w, h), Image.LANCZOS)
            tex_box.paste(tex_resized, (0,0))
        elif mode == 'stretch':
            tex_resized = tex.resize((w, h), Image.LANCZOS)
            tex_box.paste(tex_resized, (0,0))
        # Apply alpha to texture
        if alpha < 1.0:
            r, g, b, a = tex_box.split()
            a = a.point(lambda px: int(px * alpha))
            tex_box = Image.merge("RGBA", (r, g, b, a))
        # Composite texture onto the box (using box alpha)
        box_img = Image.alpha_composite(box_img, tex_box)

    # Draw border (on top of background+texture)
    if 'border_color' in box_cfg and box_cfg.get('border_width', 0) > 0:
        border_color = box_cfg['border_color']
        border_width = box_cfg['border_width']
        if corner_radius > 0:
            draw.rounded_rectangle(shape, outline=border_color, width=border_width, radius=corner_radius)
        else:
            draw.rectangle(shape, outline=border_color, width=border_width)

    # Paste box onto base image (RGBA compositing)
    base_img.alpha_composite(box_img, dest=(x, y))

    # Render text (assumes you've already wrapped/justified to fit text_w)
    draw_base = ImageDraw.Draw(base_img)
    draw_base.text((inner_box[0], inner_box[1]), text, font=font, fill=font_color)


def render_multiline_text_mask(text, font, w, h, y, line_spacing=1.2, angle=0):
    lines = text.splitlines()
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    total_height = sum(line_heights) + int(font.size * line_spacing) * (len(lines) - 1)
    current_y = y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        wtxt = bbox[2] - bbox[0]
        draw.text(((w - wtxt) // 2, current_y), line, font=font, fill=255)
        current_y += int(line_heights[i] * line_spacing)
    if angle:
        mask = mask.rotate(angle, resample=Image.BICUBIC, center=(w//2, h//2))
    return mask

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 make_cover.py <config.yaml>")
        sys.exit(1)
    config_path = sys.argv[1]
    with open(config_path) as f:
        config = yaml.safe_load(f)
    w, h = config.get('output_size', [1800, 2700])
    bg_color = config['background'].get('color', "#ffffff")
    canvas = Image.new("RGBA", (w, h), hex_color(bg_color, 255))

    # --- Background texture
    bg_cfg = config['background']
    if 'texture' in bg_cfg:
        bg_img = load_image(bg_cfg['texture'])
        bg_mode = bg_cfg.get("mode", "stretch")
        bg_alpha = bg_cfg.get("alpha", 1.0)
        fill_background(canvas, bg_img, bg_mode, bg_alpha)

    # --- Image layers
    for img_cfg in config.get('image', []):
        img_path = img_cfg['file']
        img_size = tuple(img_cfg['size'])
        img_color = img_cfg.get('color', "#ffffff")
        if img_path.lower().endswith('.svg') and img_color:
            img = load_colored_svg(img_path, img_size, img_color)
        else:
            img = load_image(img_path, img_size)
        px = int(w * img_cfg['position'][0] - img_size[0] // 2)
        py = int(h * img_cfg['position'][1] - img_size[1] // 2)
        mask = img.split()[-1]
        if 'texture' in img_cfg:
            canvas = composite_colored_texture(
                canvas,
                mask,
                hex_color(img_color, 255),
                img_cfg['texture'],
                img_cfg.get('texture_alpha', 1.0),
                img_cfg.get('texture_mode', 'fill'),
                (px, py)
            )
        else:
            temp_layer = Image.new("RGBA", canvas.size, (0,0,0,0))
            base = Image.new("RGBA", img.size, hex_color(img_color, 255))
            temp_layer.paste(base, (px, py), mask)
            canvas = Image.alpha_composite(canvas, temp_layer)

    # --- Text layers
    for txt_cfg in config.get('text', []):
        content = txt_cfg['content']
        font = ImageFont.truetype(txt_cfg['font_face'], txt_cfg['font_size'])
        color = txt_cfg.get('font_color', "#eedd99")
        angle = txt_cfg.get('angle', 0)

        # If a text box and wrapping/justify is requested, use advanced routine
        if ('box' in txt_cfg) and (txt_cfg.get('wrap') or txt_cfg.get('justify')):
            box = txt_cfg['box']
            box_x, box_y, box_w, box_h = box
            # For wrapping, use a dummy canvas to measure
            dummy_img = Image.new("L", (box_w, box_h), 0)
            dummy_draw = ImageDraw.Draw(dummy_img)
            lines = wrap_text(content, font, box_w, dummy_draw)
            # For justified: render at double width, then scale
            mask = render_justified_text_mask(
                txt_cfg['content'],
                txt_cfg['font_face'],
                txt_cfg['font_size'],
                txt_cfg['box'],
                angle=txt_cfg.get('angle', 0)
            )
            if 'texture' in txt_cfg:
                canvas = composite_colored_texture(
                    canvas,
                    mask,
                    hex_color(color, 255),
                    txt_cfg['texture'],
                    txt_cfg.get('texture_alpha', 1.0),
                    txt_cfg.get('texture_mode', 'fill'),
                    (box_x, box_y)
                )
            else:
                temp_layer = Image.new("RGBA", canvas.size, (0,0,0,0))
                color_img = Image.new("RGBA", (box_w, box_h), hex_color(color, 255))
                temp_layer.paste(color_img, (box_x, box_y), mask)
                canvas = Image.alpha_composite(canvas, temp_layer)
        else:
            # Fallback: Simple multiline rendering, centered
            px = int(w * txt_cfg['position'][0])
            py = int(h * txt_cfg['position'][1])
            mask = render_multiline_text_mask(content, font, w, h, py, angle=angle)
            if 'texture' in txt_cfg:
                canvas = composite_colored_texture(
                    canvas,
                    mask,
                    hex_color(color, 255),
                    txt_cfg['texture'],
                    txt_cfg.get('texture_alpha', 1.0),
                    txt_cfg.get('texture_mode', 'fill'),
                    (0, 0)
                )
            else:
                draw = ImageDraw.Draw(canvas)
                lines = content.splitlines()
                line_heights = []
                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    line_heights.append(bbox[3] - bbox[1])
                total_height = sum(line_heights) + int(font.size * 1.2) * (len(lines) - 1)
                current_y = py
                for i, line in enumerate(lines):
                    bbox = draw.textbbox((0, 0), line, font=font)
                    wtxt = bbox[2] - bbox[0]
                    xy = ((w - wtxt) // 2, current_y)
                    if angle:
                        text_img = Image.new("RGBA", (w, h), (0,0,0,0))
                        text_draw = ImageDraw.Draw(text_img)
                        text_draw.text(xy, line, font=font, fill=color)
                        text_img = text_img.rotate(angle, resample=Image.BICUBIC, center=(w//2, h//2))
                        canvas = Image.alpha_composite(canvas, text_img)
                    else:
                        draw.text(xy, line, font=font, fill=color)
                    current_y += int(line_heights[i] * 1.2)

    canvas.save(config['output'])
    print(f"Saved cover image to: {config['output']}")

if __name__ == "__main__":
    main()
