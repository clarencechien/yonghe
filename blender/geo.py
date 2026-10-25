"""Simplified geography of Yonghe, in metres (x = east, y = north).

The shapes are schematic, not survey-accurate (see research/sources.md §5):
the Xindian River wraps Yonghe's north-east side in an arc, and the
Wayao Creek (瓦磘溝) separates it from Zhonghe to the south-west.
"""

EXTENT = 3600.0          # half-size of the modelled square
TEX = 4096               # texture resolution for ground masks

# Xindian River centreline, south-east (upstream) to west (downstream).
RIVER = [(3600, -3300), (2700, -2300), (2050, -1200), (1700, -250), (1450, 600),
         (950, 1350), (150, 1800), (-750, 1850), (-1600, 1500), (-2500, 950),
         (-3600, 550)]
RIVER_HALF_WIDTH = 190.0   # water
FLOODPLAIN = 70.0          # riverside strip outside the water (levee zone)

# Wayao Creek / Zhonghe boundary, north-west to south-east.
CREEK = [(-2300, 1080), (-1450, 500), (-600, -80), (250, -680), (1100, -1280),
         (1950, -1880), (2600, -2250)]
CREEK_HALF_WIDTH = 5.0

# Chuanduan / Zhongzheng Bridge: Yonghe foot -> Taipei foot.
BRIDGE_A = (-300, 1580)
BRIDGE_B = (-260, 2080)
# Other bridges, shown only in the modern era (positions schematic).
YONGFU_A, YONGFU_B = (1260, 280), (1800, 430)     # 永福橋 -> 公館
FUHE_A, FUHE_B = (1600, -640), (2100, -560)       # 福和橋
XIULANG_A, XIULANG_B = (2000, -1700), (2470, -1560)  # 秀朗橋

# Wangxi ferry landing (網溪渡, end of today's Guangfu St.).
FERRY_A = (520, 1300)
FERRY_B = (760, 1760)

# The seven parks of the 1955 plan: centre, radius, fate, year converted.
# Positions follow today's successors (research/sources.md §3).
PARKS = [
    # id, (x, y), r, fate, convert_year, keep_fraction
    (1, (-450, 350), 170, "renai", 1972, 0.45),     # 仁愛公園 survives in part
    (2, (900, 150), 160, "school", 1968, 0.0),      # 福和國中
    (3, (250, -350), 150, "gov", 1966, 0.0),        # 區公所等機關
    (4, (-1000, 120), 165, "zhonghe", None, 1.0),   # 劃入中和，倖存
    (5, (1250, -950), 160, "school", 1970, 0.0),    # 秀朗國小
    (6, (250, 850), 140, "housing", 1975, 0.0),
    (7, (-1350, 780), 150, "housing", 1978, 0.0),
]

# Dachen New Village (大陳新村): low row houses beside the embankment.
DACHEN_CENTER = (800, 950)
DACHEN_SIZE = (300, 200)
DACHEN_ANGLE = 2.16  # radians, roughly parallel to the river here

# Arterial roads: (name, polyline, half_width, year_paved)
ARTERIALS = [
    ("永和路", [(-300, 1580), (-380, 900), (-520, 200), (-650, -50), (-900, -700)], 12, 1937),
    ("中正路", [(-280, 1560), (100, 1050), (450, 550), (800, -150), (1100, -700), (1450, -1200), (1650, -1650)], 11, 1958),
    ("福和路", [(-1600, 450), (-600, 330), (200, 220), (900, 150), (1300, -250), (1600, -640)], 11, 1965),
    ("竹林路", [(250, 1500), (300, 700), (250, -350), (150, -600)], 8, 1960),
    ("永貞路", [(-600, -60), (-200, -250), (250, -350), (700, -450), (1250, -950), (1500, -1350)], 8, 1965),
    ("中山路", [(-1450, 600), (-950, 650), (-450, 350), (50, 0), (250, -350)], 8, 1962),
    ("秀朗路", [(700, -1050), (1250, -950), (1750, -1050), (2000, -1700)], 7, 1966),
    ("永福路", [(450, 550), (900, 600), (1260, 280)], 8, 1968),
]

# Population of Yonghe (Wikipedia 永和區 table; 1946 & 1957 from 永和市誌).
POPULATION = [
    (1946, 7723), (1957, 24983), (1960, 38727), (1961, 44144), (1966, 69866),
    (1971, 97877), (1976, 150143), (1981, 213787), (1986, 238677),
    (1991, 247473), (1996, 230734), (2001, 229383), (2006, 235697),
    (2011, 232386), (2016, 223999), (2021, 214967), (2024, 214678),
]


def to_px(x, y, tex=TEX):
    """World metres -> texture pixel (col, row), row 0 = north."""
    u = (x + EXTENT) / (2 * EXTENT)
    v = (EXTENT - y) / (2 * EXTENT)
    return u * tex, v * tex
