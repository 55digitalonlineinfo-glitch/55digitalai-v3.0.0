#!/usr/bin/env python3
"""
make_example.py - fully fictional example input for scripts/feed_report_pdf.py.

Purpose
    Builds a placeholder brand ("Demo Brand", coffee machines), placeholder product images, a
    placeholder logo and a report_spec.json, so the PDF layout can be tested or shown without any
    real client data. All names, products and numbers are invented.

Usage
    .venv/bin/python feed-optimization/example/make_example.py
    .venv/bin/python scripts/feed_report_pdf.py feed-optimization/example/report_spec.json \
        --out "feed-optimization/example/Demo Brand - Google Shopping feed optimization.pdf"

Changelog
    2026-10-12  Initial version.
"""
import json, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
PRIMARY = (214, 137, 62)
BRAND = "Demo Brand"

os.makedirs(IMG, exist_ok=True)


def logo():
    im = Image.new("RGBA", (620, 88), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((4, 8, 76, 80), outline=PRIMARY + (255,), width=7)
    d.ellipse((26, 30, 54, 58), fill=PRIMARY + (255,))
    d.text((96, 14), BRAND.upper(), font=ImageFont.truetype(FONT, 58), fill=(255, 255, 255, 255))
    im.save(os.path.join(IMG, "logo.png"))


def product(fname, label, variant):
    """Abstract placeholder 'machine' shape - clearly a dummy image, not a real product photo."""
    w, h = 600, 464
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, w - 20, h - 20), 36, fill=(40, 35, 30, 255), outline=(90, 78, 66, 255), width=3)
    bw = 200 + variant * 22
    x0 = (w - bw) // 2
    d.rounded_rectangle((x0, 70, x0 + bw, 350), 22, fill=(70, 62, 54, 255))           # body
    d.rounded_rectangle((x0 + 24, 96, x0 + bw - 24, 150), 10, fill=(28, 24, 21, 255))  # panel
    for i in range(3):
        cx = x0 + 50 + i * ((bw - 100) // 2)
        d.ellipse((cx - 9, 114, cx + 9, 132), fill=PRIMARY + (255,))
    d.rectangle((w // 2 - 22, 180, w // 2 + 22, 222), fill=(28, 24, 21, 255))         # spout
    d.rounded_rectangle((w // 2 - 32, 258, w // 2 + 32, 326), 8, fill=(235, 225, 212, 255))  # cup
    d.rectangle((x0 - 10, 350, x0 + bw + 10, 366), fill=(55, 48, 42, 255))            # tray
    f = ImageFont.truetype(FONT, 30)
    tw = d.textlength(label, font=f)
    d.text(((w - tw) / 2, 392), label, font=f, fill=(200, 190, 178, 255))
    im.save(os.path.join(IMG, fname))


PRODUCTS = [
    # id, model, sales, key feature (stated in the old desc, so it's "on the page"), title tail
    ("101", f"{BRAND} A300 Milk", 184250, "automatic milk frother", "with milk frother"),
    ("102", f"{BRAND} A200", 141780, "ceramic grinder with 12 settings", "with ceramic grinder"),
    ("103", f"{BRAND} M1", 126400, "58 mm portafilter and pressure gauge", "with pressure gauge"),
    ("104", f"{BRAND} C1", 98320, "only 18 cm wide", "compact, 18 cm wide"),
]


def spec():
    prods = []
    for i, (pid, name, sales, feat, tail) in enumerate(PRODUCTS):
        product(f"{pid}.png", f"Demo product {i + 1}", i % 4)
        manual = name.endswith(" M1")
        lead = "Espresso machine with portafilter" if manual else "Bean to cup coffee machine with grinder"
        prods.append(dict(
            id=pid, name=name, sales=sales,
            old_title=f"{name} coffee machine",
            old_desc=f"{name} - brand new in our range! Meet the machine you'll love from the very first cup. {feat[0].upper() + feat[1:]}, 15 bar pressure...",
            new_title=f"{lead} {name} | {tail}, 15 bar",
            new_desc=(f"{lead} {name} is a 15 bar espresso machine for home. "
                      f"Key feature: {feat}. "
                      + ("A manual espresso machine for pulling espresso yourself. "
                         if manual else
                         "This coffee bean machine grinds fresh beans right before brewing. ")
                      + "Black finish."),
            image=f"img/{pid}.png",
        ))
    return {
        "client": f"{BRAND} (example)",
        "lang": "en",
        "currency": "€",
        "date_label": "October 2026",
        "product_noun": "coffee machines",
        "period": "01.10.2025 - 30.09.2026",
        "brand": {
            "primary": "#D6893E", "primary_light": "#F0B072",
            "bg": "#15120f", "bg2": "#1d1915", "secondary": "#8a7e70",
            "font": "Inter Tight", "logo": "img/logo.png",
            "source": "fictional example brand",
        },
        "kpis": {"terms": 48210, "conv_value": 1124600, "kp_terms": 12},
        "title_formula": {
            "chips": ["Best-selling phrase", "Brand and model", "Key feature"],
            "example": f"Bean to cup coffee machine with grinder {BRAND} A300 Milk | with milk frother, 15 bar",
        },
        "rules": [
            "The most important phrases go in the first ~50 characters, because that is usually all Google shows in a Shopping ad.",
            "The brand stays in the visible part of the title, but after the phrase that sells.",
            "Every title stays within the 150-character limit.",
            "Descriptions: main phrase first, supporting phrases once each, no promotional claims.",
        ],
        "keyword_planner": [
            ["coffee machine", 74000], ["espresso machine", 22200], ["bean to cup coffee machine", 18100],
            ["coffee machine with grinder", 9900], ["coffee machine for home", 6600], ["espresso machine with grinder", 5400],
            ["coffee machine with milk frother", 2900], ["demo brand", 2400], ["manual espresso machine", 2400],
            ["coffee bean machine", 1600], ["compact coffee machine", 720], ["15 bar espresso machine", 590],
        ],
        "kp_insights": [
            ["18 100", "“Bean to cup coffee machine” is the biggest phrase that describes exactly this type of product."],
            ["9 900", "“With grinder” is a feature customers actively search for."],
            ["2 400", "The brand itself is searched regularly, so it stays in the visible part of the title."],
        ],
        "kp_note": "Volume alone is not enough: a popular phrase doesn't necessarily sell. That's why step 2 checks which phrases actually brought in sales.",
        "themes": [
            ["bean to cup / automatic", 18420, 31.2, 82150, "Start of the title", "up"],
            ["with grinder", 15210, 24.6, 61340, "Right after “bean to cup”", "up"],
            ["portafilter / manual", 11080, 12.3, 33870, "Start of title (manual models)", "up"],
            ["milk frother / latte", 9640, 9.8, 24120, "In the title as a feature", "up"],
            ["for home", 6830, 6.2, 12480, "Added to descriptions", "mid"],
            ["compact / small", 4120, 3.1, 5210, "Not highlighted", "mid"],
        ],
        "ads_insights": [
            ["82 150 €", "“Bean to cup” brought in the most sales of all themes, more than plain “espresso machine”, despite lower volume."],
            ["4.5", "“With grinder” returned 4.5 € in sales for every euro spent."],
            ["12 480 €", "“For home” is how customers describe the machine in their own words, so it went into the descriptions."],
        ],
        "top_terms": [
            ["bean to cup coffee machine with grinder", 12.4, 38210],
            ["automatic coffee machine", 8.1, 24970],
            ["manual espresso machine for home", 5.2, 17340],
            ["coffee machine with grinder", 6.0, 15880],
            ["coffee bean machine", 2.1, 7260],
        ],
        "brand_share": {"brand_value": 874300, "generic_value": 250300},
        "changes": {
            "added": [
                "“bean to cup with grinder” and “portafilter” at the start of the title",
                "each model's key feature at the end of the title",
                "“for home” in the descriptions",
            ],
            "removed": ["promotional claims (“brand new”, “you'll love”) and anything not confirmed on the product page"],
        },
        "highlight": [
            "bean to cup coffee machine with grinder", "espresso machine with portafilter", "espresso machine for home",
            "manual espresso machine", "coffee bean machine", "with grinder", "milk frother", "portafilter",
        ],
        "labels": {"ba_sub": "Highlighted: phrases chosen based on steps 1 and 2. “Before” for the description is the start of the current product-page description."},
        "products": prods,
    }


if __name__ == "__main__":
    logo()
    s = spec()
    for p in s["products"]:
        assert len(p["new_title"]) <= 150, p["new_title"]
    with open(os.path.join(HERE, "report_spec.json"), "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    print("ok:", len(s["products"]), "products")
