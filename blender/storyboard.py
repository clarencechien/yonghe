"""Storyboard: narration (Traditional Chinese), on-screen text and camera work.

Every factual line is sourced in research/sources.md. Shot length comes
from the narration audio when it exists (build/audio/<id>.wav), otherwise
from an estimate of ~4.3 characters per second.

Coordinates are metres in the model (x east, y north); see geo.py.
"""
import json
import os
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "..", "build", "audio")

DEFAULTS = dict(year=2024.0, bp=0.0, reveal=0.0, ghost=0.0, night=0.0)

DAY = dict(sun=(38, 215), sky=0.02, sun_energy=2.0, fog=0.00025, fog_color=(0.11, 0.13, 0.16))
MORNING = dict(sun=(16, 115), sky=0.025, fog=0.00020, fog_color=(0.095, 0.09, 0.085),
               sun_color=(1.0, 0.85, 0.66), sun_energy=1.9)
GOLDEN = dict(sun=(9, 255), sky=0.03, fog=0.00022, fog_color=(0.12, 0.085, 0.06),
              sun_color=(1.0, 0.70, 0.42), sun_energy=1.9)
OVERCAST = dict(sun=(55, 200), sky=0.035, fog=0.00028, fog_color=(0.10, 0.105, 0.11),
                sun_energy=0.7, sun_color=(0.95, 0.96, 1.0))
DUSK = dict(sun=(0.5, 260), sky=0.06, fog=0.00025, fog_color=(0.035, 0.04, 0.06),
            sun_energy=0.0, exposure=0.6)
BLUEPRINT = dict(sun=(60, 200), sky=0.015, fog=0.00010, fog_color=(0.01, 0.02, 0.035),
                 sun_energy=1.2, exposure=0.0)

SHOTS = [
    # ------------------------------------------------------------ 開場
    dict(id="S01", chapter="今日",
         text="新北市永和區。五點七平方公里的土地上，住著二十一萬多人；每平方公里超過三萬七千人，是全台灣人口最密集的地方。",
         look=DUSK, night=0.9, year=2024.0,
         cam=[(0, (2600, -2700, 900)), (1, (1500, -1500, 560))],
         target=[(0, (0, 400, 0)), (1, (-100, 450, 0))], lens=40,
         overlay=[dict(kind="caption", t=(0.05, 0.95), text="新北市永和區　2024")]),
    dict(id="S02", chapter="今日",
         text="但在七十年前，這片土地曾經被畫成一座花園城市。",
         look=DUSK, night=0.95, year=2024.0, pad=2.5,
         cam=[(0, (-50, 600, 170)), (1, (60, 820, 140))],
         target=[(0, (-420, 1150, 20)), (1, (-450, 1150, 10))], lens=30,
         overlay=[dict(kind="title", t=(0.45, 1.0), text="永和", sub="一座花園城市的消失")]),
    # ------------------------------------------------------------ 河洲
    dict(id="S03", chapter="河洲",
         text="新店溪在這裡轉了一個大彎，沖積出一片平坦的沙洲。十七世紀的荷蘭文獻裡，已經記下這一帶的平埔族部落：秀朗社與龜崙蘭社。",
         look=MORNING, year=1650.0,
         cam=[(0, (2600, -2300, 380)), (1, (2050, -1750, 170))],
         target=[(0, (1300, -1150, 0)), (1, (1480, -1300, 0))], lens=35,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="十七世紀"),
                  dict(kind="label", t=(0.55, 1.0), text="秀朗社", at=(1500, -1300, 10))]),
    dict(id="S04", chapter="河洲",
         text="一七〇九年起，漢人移民獲准開墾臺北盆地，接著渡溪而來。沙洲上漸漸出現水田、竹叢與合院，這一帶被稱為「溪洲」。",
         look=MORNING, year=[(0, 1705.0), (1, 1905.0)],
         cam=[(0, (-2200, -2600, 1500)), (1, (-1500, -2100, 1150))],
         target=[(0, (200, 300, 0)), (1, (300, 350, 0))], lens=35,
         overlay=[dict(kind="yearcount", t=(0.0, 1.0))]),
    dict(id="S05", chapter="河洲",
         text="要到對岸的台北，只能搭網溪渡的渡船。",
         look=MORNING, year=1925.0, pad=1.5,
         cam=[(0, (300, 1150, 22)), (1, (420, 1230, 18))],
         target=[(0, (650, 1520, 0)), (1, (700, 1600, 0))], lens=32,
         boat=[(0, (540, 1340)), (1, (680, 1600))],
         overlay=[dict(kind="year", t=(0.0, 1.0), text="1920年代"),
                  dict(kind="label", t=(0.3, 1.0), text="網溪渡", at=(520, 1300, 5))]),
    dict(id="S06", chapter="一座橋",
         text="一九三七年，在地方士紳的奔走下，新店溪上架起了川端橋，長約三百公尺、寬五點三公尺。它就是今天中正橋的前身。",
         look=DAY, year=[(0, 1935.9), (0.55, 1937.6), (1, 1938.0)],
         cam=[(0, (-700, 1550, 90)), (1, (-620, 1700, 70))],
         target=[(0, (-280, 1830, 0)), (1, (-280, 1830, 0))], lens=30,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="1937"),
                  dict(kind="label", t=(0.55, 1.0), text="川端橋（今中正橋）", at=(-280, 1830, 8))]),
    # ------------------------------------------------------------ 疏散
    dict(id="S07", chapter="疏散",
         text="一九四九年後，大批軍民隨政府來台，台北市人滿為患。考量防空疏散，一河之隔的這片沙洲被劃為疏散地區。一九四六年，這裡只有七千七百多人；十一年後，已將近兩萬五千人。",
         look=OVERCAST, year=[(0, 1946.0), (1, 1957.0)],
         cam=[(0, (-1300, 2700, 900)), (1, (-1000, 2300, 700))],
         target=[(0, (-100, 900, 0)), (1, (100, 600, 0))], lens=35,
         overlay=[dict(kind="yearcount", t=(0.0, 1.0)), dict(kind="popcount", t=(0.0, 1.0))]),
    dict(id="S08", chapter="疏散",
         text="一九五五年，從大陳島撤退的居民，也有一部分被安置在新店溪堤岸旁，建起了大陳新村。",
         look=OVERCAST, year=[(0, 1954.9), (1, 1956.6)],
         cam=[(0, (420, 600, 120)), (1, (520, 690, 95))],
         target=[(0, (820, 960, 0)), (1, (820, 960, 0))], lens=32,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="1955"),
                  dict(kind="label", t=(0.5, 1.0), text="大陳新村", at=(800, 950, 6))]),
    # ------------------------------------------------------------ 藍圖
    dict(id="S09", chapter="藍圖",
         text="同一年，政府為這片土地擬定了都市計畫。規劃者借用源自英美的田園城市與鄰里單元手法：七座大型公園，綠地約占九分之一，道路以環狀和弧線，繞著公園展開。",
         look=BLUEPRINT, year=1955.5, bp=[(0, 0.0), (0.12, 1.0)], reveal=[(0.1, 0.0), (0.85, 1.05)],
         cam=[(0, (200, -900, 5200)), (1, (150, -500, 4300))],
         target=[(0, (150, 250, 0)), (1, (150, 300, 0))], lens=35, roll=0,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="1955"),
                  dict(kind="parknums", t=(0.55, 1.0))]),
    dict(id="S10", chapter="藍圖",
         text="計畫人口，只有三萬人。",
         look=BLUEPRINT, year=1955.5, bp=1.0, reveal=1.05, pad=2.5,
         cam=[(0, (150, -500, 4300)), (1, (150, -380, 4000))],
         target=[(0, (150, 300, 0)), (1, (150, 320, 0))], lens=35,
         overlay=[dict(kind="bignum", t=(0.15, 1.0), text="計畫人口　30,000")]),
    dict(id="S11", chapter="設鎮",
         text="一九五八年四月一日，永和鎮從中和鄉分出。據說地方耆老楊仲佐取名「永和」，寄望來自各地的居民永久和平。分治時，面積五點五九平方公里，人口三萬八千多人，已經超過了計畫人口。",
         look=DAY, year=[(0, 1958.2), (1, 1960.8)], bp=[(0, 0.6), (0.2, 0.0)], reveal=1.05,
         ghost=[(0.0, 0.0), (0.6, 0.0), (0.8, 0.5)],
         cam=[(0, (1700, -1900, 1500)), (1, (1300, -1500, 1100))],
         target=[(0, (100, 300, 0)), (1, (50, 350, 0))], lens=35,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="1958"),
                  dict(kind="stat", t=(0.6, 1.0), text="1960　人口 38,727")]),
    # ------------------------------------------------------------ 膨脹
    dict(id="S12", chapter="膨脹",
         text="接下來三十年，人口以驚人的速度成長：一九六一年四萬四千人，一九七一年將近十萬，一九八一年突破二十一萬。中正橋兩度拓寬，平房一棟棟拆除，四、五層樓的公寓接連蓋起。",
         look=DAY, year=[(0, 1960.5), (1, 1984.0)],
         cam=[(0, (-1500, 2300, 520)), (0.5, (-300, 2300, 420)), (1, (900, 1900, 380))],
         target=[(0, (-300, 1300, 0)), (0.5, (-100, 1000, 0)), (1, (100, 700, 0))], lens=32,
         overlay=[dict(kind="yearcount", t=(0.0, 1.0)), dict(kind="popcount", t=(0.0, 1.0))]),
    dict(id="S13", chapter="膨脹",
         text="原本預定的公園，一座接一座消失。二號公園成了福和國中，三號公園成了公所與機關用地，五號公園成了秀朗國小，六號、七號公園全部蓋成了住宅。",
         look=DAY, year=[(0, 1964.0), (1, 1980.0)], ghost=[(0, 0.0), (0.1, 0.7)],
         cam=[(0, (-1800, -1900, 1500)), (1, (-1200, -1500, 1200))],
         target=[(0, (250, 100, 0)), (1, (350, 50, 0))], lens=38,
         overlay=[dict(kind="yearcount", t=(0.0, 1.0)), dict(kind="parknums", t=(0.05, 1.0))]),
    dict(id="S14", chapter="膨脹",
         text="一九八六年，秀朗國小的學生多達一萬一千三百多人，被金氏世界紀錄列為全球學生最多的學校。",
         look=GOLDEN, year=1986.0,
         cam=[(0, (1650, -1450, 160)), (1, (1520, -1350, 130))],
         target=[(0, (1250, -950, 0)), (1, (1250, -950, 0))], lens=32,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="1986"),
                  dict(kind="stat", t=(0.45, 1.0), text="秀朗國小　學生 11,319 人")]),
    dict(id="S15", chapter="膨脹",
         text="只有四號公園，因為中永和分治時被劃進了中和，反而完整保存下來。",
         look=GOLDEN, year=1990.0, ghost=0.6,
         cam=[(0, (-1500, -350, 260)), (1, (-1450, -250, 220))],
         target=[(0, (-1000, 120, 0)), (1, (-1000, 120, 0))], lens=32,
         overlay=[dict(kind="label", t=(0.3, 1.0), text="四號公園（今八二三紀念公園）", at=(-1000, 120, 10))]),
    # ------------------------------------------------------------ 今日
    dict(id="S16", chapter="今日",
         text="一九九一年，永和人口來到約二十四萬七千人的高峰。一九九八年，捷運中和線通車，頂溪站一帶成為最熱鬧的街區。",
         look=DAY, year=[(0, 1989.0), (1, 2012.0)],
         cam=[(0, (-900, 700, 160)), (1, (-760, 860, 130))],
         target=[(0, (-380, 1100, 20)), (1, (-380, 1100, 20))], lens=30,
         overlay=[dict(kind="yearcount", t=(0.0, 1.0)), dict(kind="popcount", t=(0.0, 1.0))]),
    dict(id="S17", chapter="今日",
         text="今天的永和，人口約二十一萬，每平方公里三萬七千多人。都市計畫裡的公園用地只剩約七公頃，大約百分之一。當年的環狀道路失去了中心的公園，成了外地人口中繞不出去的迷宮。",
         look=DUSK, night=0.85, year=2024.0, ghost=[(0, 0.0), (0.45, 0.0), (0.6, 1.0)],
         cam=[(0, (300, -1500, 2600)), (1, (220, -800, 3600))],
         target=[(0, (150, 250, 0)), (1, (150, 300, 0))], lens=35,
         overlay=[dict(kind="year", t=(0.0, 1.0), text="2024"),
                  dict(kind="stat", t=(0.35, 1.0), text="公園用地 7.18 公頃 ／ 計畫面積 582.92 公頃")]),
    dict(id="S18", chapter="尾聲",
         text="一號公園留下的一角，就是今天的仁愛公園。花園城市沒有實現，但它的形狀，一直留在永和彎曲的街道裡。",
         look=DUSK, night=1.0, year=2024.0, ghost=[(0, 0.0), (0.55, 0.0), (0.85, 0.8)], pad=4.0,
         cam=[(0, (-640, 240, 70)), (0.5, (-760, 120, 260)), (1, (-1100, -400, 1500))],
         target=[(0, (-520, 350, 0)), (0.5, (-450, 350, 0)), (1, (-200, 350, 0))], lens=30,
         overlay=[dict(kind="label", t=(0.1, 0.6), text="仁愛公園", at=(-540, 350, 10))]),
]

ENDCARD = dict(id="END", seconds=14.0)


def get(sid):
    for s in SHOTS:
        if s["id"] == sid:
            return s
    raise KeyError(sid)


def audio_seconds(sid):
    p = os.path.join(AUDIO, f"{sid}.wav")
    if not os.path.exists(p):
        return None
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def duration(shot):
    a = audio_seconds(shot["id"])
    pad = shot.get("pad", 1.6)
    if a is None:
        a = len(shot["text"]) / 4.3
    return round(a + pad + 0.6, 2)


if __name__ == "__main__":
    tot = 0
    for s in SHOTS:
        d = duration(s)
        tot += d
        print(s["id"], d, audio_seconds(s["id"]))
    print("total", tot, "frames", int(tot * 24))
    print(json.dumps([dict(id=s["id"], text=s["text"]) for s in SHOTS], ensure_ascii=False)[:200])
