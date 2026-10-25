"""Contact sheet of proof stills: python pipeline/contact.py build/stills out.png [cols]"""
import glob, os, sys
from PIL import Image, ImageDraw, ImageFont
src, out = sys.argv[1], sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 4
files = sorted(glob.glob(os.path.join(src, "*.png")))
W, H = 480, 270
sheet = Image.new("RGB", (cols * W, -(-len(files) // cols) * H), "black")
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    x, y = i % cols * W, i // cols * H
    sheet.paste(Image.open(f).convert("RGB").resize((W, H)), (x, y))
    d.text((x + 6, y + 4), os.path.basename(f)[:-4], fill="yellow")
sheet.save(out)
