"""
Seed 5 virtual artists, 10 albums, and 50 published songs for YuE2 Studio.
Owner: '제세형' (user_id = 1, username = 'digitalism8150')
"""

import io
import json
import math
import os
import random
import shutil
import sqlite3
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "yue2_app" / "data" / "yue2.sqlite3"
COVERS_DIR = ROOT_DIR / "yue2_app" / "data" / "covers"
COMFY_YUE2_OUTPUT = ROOT_DIR / "ComfyUI" / "output" / "yue2"

COVERS_DIR.mkdir(parents=True, exist_ok=True)
COMFY_YUE2_OUTPUT.mkdir(parents=True, exist_ok=True)

FONT_KR_BOLD = "C:/Windows/Fonts/malgunbd.ttf"
FONT_KR_REG = "C:/Windows/Fonts/malgun.ttf"
FONT_EN_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_EN_REG = "C:/Windows/Fonts/arial.ttf"

def get_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def create_gradient_image(width: int, height: int, color1: tuple, color2: tuple, direction: str = "vertical"):
    base = Image.new("RGB", (width, height), color1)
    top = Image.new("RGB", (width, height), color2)
    mask = Image.new("L", (width, height))
    mask_data = []
    if direction == "vertical":
        for y in range(height):
            mask_data.extend([int(255 * (y / height))] * width)
    elif direction == "horizontal":
        for y in range(height):
            for x in range(width):
                mask_data.append(int(255 * (x / width)))
    else:  # diagonal
        for y in range(height):
            for x in range(width):
                val = int(255 * ((x / width + y / height) / 2))
                mask_data.append(min(255, max(0, val)))
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def draw_artistic_graphics(img: Image, theme: str, width: int, height: int):
    draw = ImageDraw.Draw(img, "RGBA")
    random.seed(hash(theme) % 100000)

    if theme == "luna":
        # Ethereal, starry, moon, soft concentric circles
        for r in range(50, min(width, height) // 2 + 100, 40):
            alpha = max(10, 60 - r // 8)
            draw.ellipse(
                (width // 2 - r, height // 2 - r, width // 2 + r, height // 2 + r),
                outline=(200, 220, 255, alpha),
                width=2,
            )
        # Moon crescent
        moon_center = (width * 3 // 4, height // 4)
        m_r = min(width, height) // 8
        draw.ellipse((moon_center[0] - m_r, moon_center[1] - m_r, moon_center[0] + m_r, moon_center[1] + m_r), fill=(240, 245, 255, 180))
        draw.ellipse((moon_center[0] - m_r + 20, moon_center[1] - m_r - 10, moon_center[0] + m_r + 20, moon_center[1] + m_r - 10), fill=(20, 25, 55, 255))
        # Stars
        for _ in range(80):
            sx = random.randint(0, width)
            sy = random.randint(0, height)
            sr = random.randint(1, 3)
            s_alpha = random.randint(100, 255)
            draw.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(255, 255, 255, s_alpha))

    elif theme == "kairos":
        # Cyberpunk neon grid and glitch bars
        # Perspective grid
        grid_y = height // 2
        for x in range(0, width, 40):
            draw.line([(x, height), (width // 2 + (x - width // 2) // 4, grid_y)], fill=(0, 240, 255, 70), width=1)
        for y_step in range(grid_y, height, 25):
            draw.line([(0, y_step), (width, y_step)], fill=(255, 0, 128, 60), width=1)
        # Neon sun / circle behind
        sun_r = min(width, height) // 4
        sun_y = grid_y - 20
        draw.ellipse((width // 2 - sun_r, sun_y - sun_r, width // 2 + sun_r, sun_y + sun_r), fill=(255, 40, 100, 160))
        # Laser beams / glitch rectangles
        for _ in range(12):
            rx = random.randint(0, width - 100)
            ry = random.randint(100, height - 100)
            rw = random.randint(60, 250)
            rh = random.randint(2, 6)
            color = random.choice([(0, 255, 255, 140), (255, 0, 128, 140), (255, 255, 0, 140)])
            draw.rectangle((rx, ry, rx + rw, ry + rh), fill=color)

    elif theme == "haeun":
        # Warm, organic, acoustic, floral / leaf silhouettes, gentle curves
        for _ in range(8):
            cx = random.randint(width // 4, width * 3 // 4)
            cy = random.randint(height // 4, height * 3 // 4)
            cr = random.randint(80, 200)
            draw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=(255, 240, 220, 30))
        # Warm acoustic wave arcs
        for i in range(10):
            offset = i * 30
            bbox = (width // 4 - offset, height // 3 - offset, width * 3 // 4 + offset, height * 2 // 3 + offset)
            draw.arc(bbox, start=200, end=340, fill=(210, 170, 120, 60), width=3)
        # Gentle floating dots/leaves
        for _ in range(40):
            dx = random.randint(0, width)
            dy = random.randint(0, height)
            dr = random.randint(2, 5)
            draw.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), fill=(245, 230, 200, 100))

    elif theme == "groove":
        # Retro city pop sunset and diagonal stripes
        # Half sun
        sun_r = min(width, height) // 3
        draw.pieslice((width // 2 - sun_r, height // 2 - sun_r, width // 2 + sun_r, height // 2 + sun_r), start=180, end=360, fill=(255, 180, 40, 200))
        # Horizontal blinds cutting through sun
        for by in range(height // 2 - sun_r, height // 2, 16):
            draw.line([(width // 2 - sun_r - 20, by), (width // 2 + sun_r + 20, by)], fill=(30, 15, 60, 255), width=4)
        # Geometric triangles and Memphis pattern
        for _ in range(15):
            tx = random.randint(50, width - 50)
            ty = random.randint(height // 2, height - 50)
            ts = random.randint(15, 35)
            draw.polygon([(tx, ty), (tx + ts, ty + ts), (tx - ts, ty + ts)], outline=(255, 100, 150, 120), width=2)

    elif theme == "aetheria":
        # Epic fantasy, runic compass, majestic concentric geometry, golden rays
        center = (width // 2, height // 2)
        # Rays
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            x2 = center[0] + int(math.cos(rad) * max(width, height))
            y2 = center[1] + int(math.sin(rad) * max(width, height))
            draw.line([center, (x2, y2)], fill=(255, 215, 100, 25), width=2)
        # Circles & Diamonds
        for r in [80, 140, 200, 280, 380]:
            if r < min(width, height) // 2 + 50:
                draw.ellipse((center[0] - r, center[1] - r, center[0] + r, center[1] + r), outline=(230, 190, 80, 80), width=2)
        # Diamond
        dr = 180
        draw.polygon([(center[0], center[1] - dr), (center[0] + dr, center[1]), (center[0], center[1] + dr), (center[0] - dr, center[1])], outline=(255, 230, 140, 90), width=2)

    return img

def create_artist_avatar(theme: str, artist_name: str) -> str:
    size = 800
    palettes = {
        "luna": ((15, 20, 50), (60, 40, 110)),
        "kairos": ((10, 10, 25), (180, 15, 90)),
        "haeun": ((50, 40, 35), (190, 140, 100)),
        "groove": ((35, 10, 50), (230, 100, 50)),
        "aetheria": ((10, 25, 45), (160, 120, 30)),
    }
    c1, c2 = palettes[theme]
    img = create_gradient_image(size, size, c1, c2, direction="diagonal")
    img = draw_artistic_graphics(img, theme, size, size)

    # Blur slightly for depth
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    draw = ImageDraw.Draw(blurred)

    # Circular portrait frame
    margin = 80
    draw.ellipse((margin, margin, size - margin, size - margin), outline=(255, 255, 255, 160), width=6)
    draw.ellipse((margin + 12, margin + 12, size - margin - 12, size - margin - 12), outline=(255, 255, 255, 70), width=2)

    # Initial letter / Name
    font_large = get_font(FONT_EN_BOLD if theme != "haeun" else FONT_KR_BOLD, 180)
    initial = artist_name[0]
    bbox = font_large.getbbox(initial)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1] - 30), initial, font=font_large, fill=(255, 255, 255))

    # Artist full name bottom
    font_sub = get_font(FONT_EN_BOLD if theme != "haeun" else FONT_KR_BOLD, 46)
    bbox_sub = font_sub.getbbox(artist_name)
    sw = bbox_sub[2] - bbox_sub[0]
    draw.text(((size - sw) // 2, size - margin - 75), artist_name, font=font_sub, fill=(240, 240, 255))

    filename = f"{uuid.uuid4().hex}.jpg"
    blurred.save(COVERS_DIR / filename, "JPEG", quality=92)
    return filename

def create_artist_banner(theme: str, artist_name: str, genre_label: str) -> str:
    width, height = 1800, 600
    palettes = {
        "luna": ((8, 12, 35), (45, 25, 85)),
        "kairos": ((10, 5, 20), (140, 10, 70)),
        "haeun": ((40, 32, 28), (140, 100, 70)),
        "groove": ((25, 10, 40), (190, 70, 40)),
        "aetheria": ((8, 18, 32), (120, 90, 25)),
    }
    c1, c2 = palettes[theme]
    img = create_gradient_image(width, height, c1, c2, direction="horizontal")
    img = draw_artistic_graphics(img, theme, width, height)

    # Subtle vignette overlay
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 60))

    # Banner title
    font_title = get_font(FONT_EN_BOLD if theme != "haeun" else FONT_KR_BOLD, 100)
    font_sub = get_font(FONT_EN_REG if theme != "haeun" else FONT_KR_REG, 40)

    draw.text((120, 220), artist_name, font=font_title, fill=(255, 255, 255))
    draw.text((125, 340), genre_label.upper(), font=font_sub, fill=(200, 210, 230))

    filename = f"{uuid.uuid4().hex}.jpg"
    img.save(COVERS_DIR / filename, "JPEG", quality=92)
    return filename

def create_album_cover(theme: str, artist_name: str, album_title: str, subtitle: str) -> str:
    size = 1200
    palettes = {
        "luna": [
            ((12, 18, 48), (75, 45, 130)),
            ((10, 28, 55), (30, 95, 140)),
        ],
        "kairos": [
            ((15, 8, 30), (220, 20, 90)),
            ((5, 15, 25), (0, 180, 210)),
        ],
        "haeun": [
            ((55, 42, 35), (205, 155, 115)),
            ((35, 48, 40), (120, 160, 130)),
        ],
        "groove": [
            ((40, 12, 55), (240, 120, 45)),
            ((20, 25, 60), (225, 75, 130)),
        ],
        "aetheria": [
            ((12, 24, 40), (180, 135, 40)),
            ((20, 15, 35), (140, 70, 150)),
        ],
    }
    choice = palettes[theme][random.randint(0, 1)]
    img = create_gradient_image(size, size, choice[0], choice[1], direction="diagonal")
    img = draw_artistic_graphics(img, theme, size, size)

    # Frame border
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((60, 60, size - 60, size - 60), outline=(255, 255, 255, 100), width=3)
    draw.rectangle((75, 75, size - 75, size - 75), outline=(255, 255, 255, 40), width=1)

    # Title & Artist Text
    font_main = get_font(FONT_EN_BOLD if any(c.isascii() for c in album_title) and not "봄" in album_title and not "비" in album_title else FONT_KR_BOLD, 72)
    font_art = get_font(FONT_EN_BOLD if theme != "haeun" else FONT_KR_BOLD, 42)
    font_sub = get_font(FONT_EN_REG if theme != "haeun" else FONT_KR_REG, 30)

    # Bottom block with dark translucent scrim for readability
    scrim = Image.new("RGBA", (size, 340), (0, 0, 0, 140))
    img.paste(scrim, (0, size - 340), scrim)

    draw = ImageDraw.Draw(img)
    draw.text((100, size - 290), album_title, font=font_main, fill=(255, 255, 255))
    draw.text((105, size - 200), artist_name, font=font_art, fill=(220, 225, 240))
    draw.text((105, size - 140), subtitle, font=font_sub, fill=(180, 185, 200))

    filename = f"{uuid.uuid4().hex}.jpg"
    img.save(COVERS_DIR / filename, "JPEG", quality=92)
    return filename


# Setup the 5 Artist Personas
ARTISTS_DATA = [
    {
        "id": -1,
        "name": "Luna Veil (루나 베일)",
        "theme": "luna",
        "genre": "Dream Pop · Ambient · Ethereal Synth",
        "bio": "밤의 파도와 푸른 달빛 사이를 부유하는 드림팝 싱어송라이터. 몽환적인 신시사이저와 부드러운 보컬로 꿈의 경계를 노래합니다.",
        "albums": [
            {
                "title": "Nocturne in Blue",
                "subtitle": "Vol. 1 · Midnight Soundscape",
                "desc": "자정 너머 어둠 속에서 번지는 푸른 감정과 몽환적인 사운드스케이프를 담은 정규 1집.",
                "tracks": [
                    {
                        "title": "Midnight Echoes",
                        "style": "Dream pop, ethereal female vocals, lush reverb guitars, nostalgic synth pads, 85 bpm",
                        "lyrics": "[Verse 1]\nFading shadows on the windowpane\nWhispers echoing through the rain\nCounting stars in a velvet sky\nWatching midnight pass us by\n\n[Chorus]\nEchoes in the dark, calling out your name\nNothing in the cold will ever feel the same\nDrifting on the sound of an endless sea\nMidnight echoes returning to me",
                        "plays": 2420,
                    },
                    {
                        "title": "Lucent Waves",
                        "style": "Ambient dream pop, soft delay electric guitar, warm sub bass, airy vocals, 90 bpm",
                        "lyrics": "[Verse 1]\nSilver ripples under the quiet moon\nHoping morning doesn't come too soon\nClose your eyes and breathe the salty air\nFind the peace we left behind somewhere\n\n[Chorus]\nLucent waves, carrying the light\nGuiding us gently through the night\nHold on tight before the tides erase\nEvery memory of this secret place",
                        "plays": 1850,
                    },
                    {
                        "title": "Velvet Haze",
                        "style": "Lo-fi chillwave, muted Rhodes, warm vintage cassette tape warble, whisper vocal, 78 bpm",
                        "lyrics": "[Verse 1]\nDim the purple neon glow\nMove along so soft and slow\nThrough the haze we gently fall\nShadows dancing on the wall\n\n[Chorus]\nVelvet haze covering my mind\nLeaving all the broken thoughts behind\nIn this quiet shelter where we stay\nUntil the twilight drifts away",
                        "plays": 1210,
                    },
                    {
                        "title": "Moonlit Tide",
                        "style": "Ethereal indie pop, swelling strings, slow tempo acoustic guitar, haunting melody, 82 bpm",
                        "lyrics": "[Verse 1]\nTides are rising high against the shore\nI don't fear the ocean anymore\nLet the gentle water wash away\nAll the sorrow born of yesterday\n\n[Chorus]\nUnderneath the pale moonlit tide\nThere is nowhere left for us to hide\nTake my hand and sink into the blue\nEvery wave is leading back to you",
                        "plays": 940,
                    },
                    {
                        "title": "Dawn Will Wait",
                        "style": "Ambient outro, slow piano, cinematic atmospheric drone, emotional vocalization, 72 bpm",
                        "lyrics": "[Verse 1]\nDon't let the sunlight break the spell\nStories that the darkness learned to tell\nRest your heavy head upon my chest\nHere is where your weary heart can rest\n\n[Chorus]\nDawn will wait until we say goodbye\nLet the last star linger in the sky\nHold this dream before it fades away\nDawn will wait for just another day",
                        "plays": 680,
                    },
                ],
            },
            {
                "title": "Stardust Reverie",
                "subtitle": "Vol. 2 · Cosmic Odyssey",
                "desc": "우주의 고요함과 은하수의 잔물결을 여행하는 시네마틱 앰비언트 팝 앨범.",
                "tracks": [
                    {
                        "title": "Cosmic Dust",
                        "style": "Space ambient, airy synthesizer, celestial bells, gentle pulsing beat, 92 bpm",
                        "lyrics": "[Verse 1]\nFloating high beyond the stratosphere\nFar away from all the doubt and fear\nParticles of light around my hand\nTraveling across an endless land\n\n[Chorus]\nWe are made of stardust and desire\nBurning in a quiet astral fire\nDancing in the cosmic dust alone\nFinding where the universe is home",
                        "plays": 2180,
                    },
                    {
                        "title": "Nebula Lullaby",
                        "style": "Ethereal ballad, harp, shimmer reverb, soothing vocal harmonies, 75 bpm",
                        "lyrics": "[Verse 1]\nSpinning wheels of violet and gold\nAncient legends that the cosmos told\nClose your eyes, the nebula is near\nSinging soft so you will never fear\n\n[Chorus]\nSleep beneath the glowing starlight stream\nWander deep into a celestial dream\nLullaby of colors in the sky\nNebula will watch you as you fly",
                        "plays": 1640,
                    },
                    {
                        "title": "Weightless",
                        "style": "Downtempo electronica, floating synth arpeggios, gentle sub kick, ethereal hook, 100 bpm",
                        "lyrics": "[Verse 1]\nGravity is slipping from the floor\nI don't feel the anchor anymore\nDrifting upward to the open blue\nNothing else matters besides you\n\n[Chorus]\nWeightless in the dark, weightless in the air\nNo more burdens left for us to bear\nSoaring through the infinite expanse\nGiving every fleeting hope a chance",
                        "plays": 1130,
                    },
                    {
                        "title": "Aurora Glow",
                        "style": "Ambient synth pop, crystalline pads, rhythmic pulses, expansive soundstage, 88 bpm",
                        "lyrics": "[Verse 1]\nEmerald ribbons in the frozen night\nPainting darkness with magnetic light\nNature's silent symphony unfurled\nOverhead above the sleeping world\n\n[Chorus]\nWatch the aurora glow, watch it softly weave\nAll the wonder that we can believe\nIn the frozen quiet of the pole\nColor pouring directly to the soul",
                        "plays": 850,
                    },
                    {
                        "title": "Silent Orbit",
                        "style": "Minimalist ambient, tape delay piano, breathy vocal drone, reflective, 70 bpm",
                        "lyrics": "[Verse 1]\nCircling around the silent earth\nLooking back at all that we were worth\nTiny lights like diamonds down below\nSpinning in a peaceful, steady flow\n\n[Chorus]\nIn this silent orbit round the sun\nKnowing that the journey has begun\nNo regrets and nothing left to say\nAs the orbit carries us away",
                        "plays": 590,
                    },
                ],
            },
        ],
    },
    {
        "id": -2,
        "name": "KAIROS (카이로스)",
        "theme": "kairos",
        "genre": "Cyberpunk · Dark Synthwave · Industrial",
        "bio": "네온 빛으로 뒤덮인 미래 도시의 그림자를 질주하는 신스웨이브 프로듀서. 강렬한 아날로그 베이스와 레트로 퓨처리즘 사운드로 미래의 고독을 표현합니다.",
        "albums": [
            {
                "title": "Neon Odyssey 2099",
                "subtitle": "Vol. 1 · Megalopolis Nights",
                "desc": "2099년 거대 메가로폴리스의 젖은 아스팔트와 네온 사인을 질주하는 고속 사이버펑크 앨범.",
                "tracks": [
                    {
                        "title": "Cybernetic Pulse",
                        "style": "Cyberpunk synthwave, aggressive saw bass, driving 16th arpeggio, 80s gated snare, 128 bpm",
                        "lyrics": "[Verse 1]\nWired into the mainframe deep inside\nSilicon bloodlines nowhere left to hide\nDigital adrenaline in the veins\nSpeeding down the automated lanes\n\n[Chorus]\nFeel the cybernetic pulse ignite\nPiercing through the artificial night\nSystem override, no turning back\nBlazing down the cyber highway track",
                        "plays": 2750,
                    },
                    {
                        "title": "Neon Boulevard",
                        "style": "Outrun synthwave, warm analog lead, punchy kick drum, driving bassline, 120 bpm",
                        "lyrics": "[Verse 1]\nRaindrops reflecting hologram signs\nTracing the curvature of city lines\nTwin turbo engine screaming out loud\nCutting cleanly through the midnight crowd\n\n[Chorus]\nNeon boulevard, burning magenta red\nChasing every phantom in my head\nSpeedometer climbing to the edge\nLiving on the neon highway's ledge",
                        "plays": 1980,
                    },
                    {
                        "title": "Overdrive Protocol",
                        "style": "Dark electro, distorted bass, industrial percussion, synth lead hook, 130 bpm",
                        "lyrics": "[Verse 1]\nEmergency alarms beginning to sound\nWarning beacons flashing all around\nRPM peaking in the danger zone\nRacing this machine all on my own\n\n[Chorus]\nOverdrive protocol initiated now\nBreak the firewall, show them how\nMaximum power flowing through the core\nWe won't take the limits anymore",
                        "plays": 1420,
                    },
                    {
                        "title": "Hologram Tears",
                        "style": "Melodic synthwave, emotional synth brass, nostalgic 80s drums, minor chord progression, 115 bpm",
                        "lyrics": "[Verse 1]\nProjected faces in the smoggy rain\nPixelated smiles hiding real pain\nSynthetic dreams and memory cards\nScattered across synthetic boulevards\n\n[Chorus]\nHologram tears wiping off the glass\nWaiting for the digital storm to pass\nEven machines can learn to feel the grief\nIn a world where innocence is brief",
                        "plays": 990,
                    },
                    {
                        "title": "Tokyo Midnight Run",
                        "style": "Fast-paced darksynth, shredding synth solo, pulsing sub bass, 135 bpm",
                        "lyrics": "[Verse 1]\nShuto expressway stretching to the bay\nLeaving all the sirens far away\nHeadlights flashing on the concrete wall\nWaiting for the final checkpoint call\n\n[Chorus]\nTokyo midnight run, we never slow down\nKing of the underground across this town\nEngines screaming till the break of day\nTokyo midnight running all the way",
                        "plays": 810,
                    },
                ],
            },
            {
                "title": "Analog Dystopia",
                "subtitle": "Vol. 2 · Gritty Wasteland",
                "desc": "잊혀진 아날로그 신시사이저와 거친 디스토션으로 빚어낸 황량한 미래의 디스토피아 사운드트랙.",
                "tracks": [
                    {
                        "title": "Glitch Matrix",
                        "style": "Glitch electro, broken beats, bitcrushed bass, sci-fi fx, aggressive groove, 125 bpm",
                        "lyrics": "[Verse 1]\nStatic on the frequency, numbers on screen\nFlickering illusions like you've never seen\nData packets dropping in the broken line\nSearching for the secret hidden design\n\n[Chorus]\nGlitch in the matrix tearing at the seam\nWaking up inside an artificial dream\nReset the system, wipe the memory clean\nDisappear into the static machine",
                        "plays": 2340,
                    },
                    {
                        "title": "Rust and Chrome",
                        "style": "Industrial synth, heavy metallic percussion, driving bassline, retro futuristic, 122 bpm",
                        "lyrics": "[Verse 1]\nAbandoned factories and broken steel\nRemembering how humans used to feel\nRust creeping up the polished chrome\nScrap metal city that we call home\n\n[Chorus]\nBetween the rust and the shining chrome\nSearching for a sanctuary of our own\nGears keep turning in the acid rain\nEnduring through the industrial pain",
                        "plays": 1720,
                    },
                    {
                        "title": "Synthetic Soul",
                        "style": "Deep synthwave, vocoder vocal chops, analog warmth, moody atmosphere, 110 bpm",
                        "lyrics": "[Verse 1]\nCode running deep within my chest\nSearching for an hour of quiet rest\nWires and copper wrapped around a heart\nTorn by the algorithms right apart\n\n[Chorus]\nDo you believe in a synthetic soul?\nCan artificial circuits make us whole?\nEchoing humanity inside the steel\nShow me that what I feel is real",
                        "plays": 1260,
                    },
                    {
                        "title": "Circuit Breaker",
                        "style": "High-energy darksynth, aggressive arps, pounding industrial kick, 132 bpm",
                        "lyrics": "[Verse 1]\nVoltage spikes beyond the safe degree\nSparks flying everywhere you see\nThe grid is collapsing on the floor\nWe can't hold the surge here anymore\n\n[Chorus]\nTrip the circuit breaker, shut it down\nBlackout descending on the megatown\nKill the electricity, let it freeze\nBring the giant mainframe to its knees",
                        "plays": 770,
                    },
                    {
                        "title": "Edge of the Grid",
                        "style": "Atmospheric synthwave outro, lingering analog pads, distant thunder, cinematic finish, 95 bpm",
                        "lyrics": "[Verse 1]\nThe pavement ends where the desert lies\nUnderneath the starless blackened skies\nLast signal tower fading out of view\nBeginning something desolate and new\n\n[Chorus]\nStanding right here on the edge of the grid\nNo more hiding what we ever did\nLook ahead into the silent wild\nFree at last, nature's forgotten child",
                        "plays": 540,
                    },
                ],
            },
        ],
    },
    {
        "id": -3,
        "name": "하은 (HaEun)",
        "theme": "haeun",
        "genre": "Acoustic Indie Folk · K-Indie Pop",
        "bio": "계절의 바람과 일상의 온도를 담담하게 노래하는 인디 포크 싱어송라이터. 따뜻한 통기타와 어쿠스틱 피아노로 마음에 머무는 멜로디를 전합니다.",
        "albums": [
            {
                "title": "오래된 일기장의 봄",
                "subtitle": "Spring in the Old Diary",
                "desc": "지나간 시간의 온기를 들추어보는 담담한 어쿠스틱 선율과 봄날의 서정.",
                "tracks": [
                    {
                        "title": "바람이 머문 자리",
                        "style": "Acoustic indie folk, fingerpicking acoustic guitar, warm cello, gentle female vocals, 80 bpm",
                        "lyrics": "[Verse 1]\n골목길 모퉁이를 돌아설 때면\n코끝을 스쳐가는 봄의 냄새\n잊은 줄 알았던 그날의 너와 내가\n어느새 바람 타고 다시 불어와\n\n[Chorus]\n바람이 머문 자리에 서서\n가만히 네 이름을 불러보네\n계절은 흘러도 변하지 않는\n따스했던 우리들의 시간 속으로",
                        "plays": 2890,
                    },
                    {
                        "title": "서랍 속의 편지",
                        "style": "Upright piano, acoustic guitar strum, heartfelt vocal, subtle strings, 76 bpm",
                        "lyrics": "[Verse 1]\n먼지 쌓인 서랍 깊은 곳에서\n노랗게 바랜 편지 한 장을 보았지\n삐뚤빼뚤 적어 내려간 다짐들\n그 시절의 내가 날 바라보고 있어\n\n[Chorus]\n전하지 못한 말들이 남아\n종이 위에 소복이 내려앉아\n아직도 설레는 그 마음 그대로\n서랍 속 편지는 꿈을 꾸네",
                        "plays": 2100,
                    },
                    {
                        "title": "오후 네 시의 햇살",
                        "style": "Bossa nova indie pop, nylon guitar, soft shakers, gentle upright bass, 95 bpm",
                        "lyrics": "[Verse 1]\n창가로 비쳐 드는 나른한 빛\n머그잔에 피어나는 작은 김\n책장을 넘기다 스르르 잠들면\n고양이도 내 곁에 몸을 뉘이네\n\n[Chorus]\n오후 네 시의 햇살처럼\n따스하게 날 감싸 안아줘\n바쁜 하루 끝 작은 쉼표 하나\n너와 함께 누리는 이 순간",
                        "plays": 1530,
                    },
                    {
                        "title": "작은 화분",
                        "style": "Folk pop, acoustic fingerstyle, melodica, sweet harmonies, 88 bpm",
                        "lyrics": "[Verse 1]\n햇볕 잘 드는 창가 자리에\n조그만 씨앗 하나 심어두었지\n매일 아침 물을 주며 기다린 날들\n작고 여린 초록 잎이 돋아났어\n\n[Chorus]\n작은 화분 하나가 주는 위로\n메마른 마음에 피어난 꽃처럼\n조금씩 자라나는 우리의 내일도\n눈부신 햇살을 맞이할 거야",
                        "plays": 1050,
                    },
                    {
                        "title": "봄날의 산책",
                        "style": "Bright acoustic indie, cheerful strum, light hand claps, whistling, 105 bpm",
                        "lyrics": "[Verse 1]\n가벼운 운동화를 꿰어 신고\n벚꽃 잎 흩날리는 길을 걸어\n발걸음 맞춰 콧노래 부르며\n파란 하늘 아래로 나아가\n\n[Chorus]\n봄날의 산책, 너와 걷는 길\n모든 풍경이 노래가 되는 날\n손잡고 걸어가는 이 길 끝에서\n우리 활짝 웃을 수 있기를",
                        "plays": 740,
                    },
                ],
            },
            {
                "title": "비 내린 숲길",
                "subtitle": "Rainy Forest Path",
                "desc": "비 갠 숲의 촉촉한 흙내음과 조용한 위로를 건네는 어쿠스틱 발라드 앨범.",
                "tracks": [
                    {
                        "title": "빗방울 발자국",
                        "style": "Rainy day acoustic ballad, delicate piano arpeggio, soft rain sounds, intimate vocal, 72 bpm",
                        "lyrics": "[Verse 1]\n토닥토닥 창문을 두드리는 소리\n젖은 처마 밑으로 맺힌 물방울들\n비 오는 날이면 유난히 생각나\n너와 함께 걷던 그 젖은 길거리\n\n[Chorus]\n빗방울 발자국 따라 걸어가면\n어느새 너의 곁에 닿을 것 같아\n비에 젖은 세상이 맑아지듯\n내 슬픈 마음도 씻겨 내려가",
                        "plays": 2250,
                    },
                    {
                        "title": "안개 낀 아침",
                        "style": "Atmospheric folk, low guitar drone, airy flute, slow emotional progression, 68 bpm",
                        "lyrics": "[Verse 1]\n숲속 깊은 곳 자욱한 하얀 안개\n숨을 들이쉬면 차가운 이슬 향기\n길을 잃어도 두렵지 않은 건\n나무들이 내 곁을 지켜주니까\n\n[Chorus]\n안개 낀 아침, 고요한 침묵 속에\n나의 작은 숨소리만 맴돌고\n천천히 안개가 걷혀갈 때쯤\n새로운 빛이 길을 비춰주리",
                        "plays": 1690,
                    },
                    {
                        "title": "나무 그늘 아래서",
                        "style": "Warm acoustic folk, rich 6-string acoustic guitar, double bass, relaxed tempo, 84 bpm",
                        "lyrics": "[Verse 1]\n큰 참나무 그늘 아래 털썩 주저앉아\n풀잎 스치는 소리에 귀를 기울여\n세상의 소음들은 저 멀리 두고\n시원한 그늘 밑에서 쉬어가네\n\n[Chorus]\n나무 그늘 아래서 쉬어가요\n지친 어깨를 잠시 내려놓고\n바람이 건네는 다정한 인사에\n미소 짓는 하루가 되기를",
                        "plays": 1180,
                    },
                    {
                        "title": "잔잔한 물결",
                        "style": "Piano and acoustic guitar duet, gentle crescendo, pure vocal tone, 76 bpm",
                        "lyrics": "[Verse 1]\n작은 조약돌을 호수에 던지면\n동그랗게 번져가는 잔잔한 파문\n내 작은 마음의 떨림도 언젠간\n누군가의 마음에 가닿을까\n\n[Chorus]\n잔잔한 물결처럼 흔들려도\n결국엔 평온을 찾아가듯이\n깊은 호수 같은 너의 품에 안겨\n조용히 잠들고 싶어라",
                        "plays": 860,
                    },
                    {
                        "title": "밤하늘의 쉼표",
                        "style": "Lyrical indie ballad, acoustic nylon guitar, celestial glockenspiel, peaceful outro, 70 bpm",
                        "lyrics": "[Verse 1]\n까만 밤하늘에 외롭게 떠 있는\n초승달 하나, 꼭 쉼표를 닮았네\n오늘 하루도 참 고생 많았다고\n하늘이 건네는 조용한 쉼표 하나\n\n[Chorus]\n밤하늘의 쉼표를 바라보며\n오늘의 무거운 짐을 내려놔요\n내일은 더 고운 별빛이 뜰 테니\n편안한 밤이 되기를 기도해요",
                        "plays": 620,
                    },
                ],
            },
        ],
    },
    {
        "id": -4,
        "name": "GROOVE MATRIX (그루브 매트릭스)",
        "theme": "groove",
        "genre": "City Pop · Neo Soul · Funk · R&B",
        "bio": "80~90년대 시티팝의 황금기와 세련된 네오 소울의 그루브를 융합하는 밴드 프로젝트. 도시의 반짝이는 밤거리와 로맨스를 연주합니다.",
        "albums": [
            {
                "title": "City Lights Boulevard",
                "subtitle": "Vol. 1 · Tokyo Sunset & Neon",
                "desc": "네온 불빛 반짝이는 해안 도로와 화려한 도심의 나이트라이프를 담은 시티팝 명반.",
                "tracks": [
                    {
                        "title": "Midnight Highway",
                        "style": "80s Japanese City pop, slap bass, energetic brass, funky guitar chops, female vocals, 118 bpm",
                        "lyrics": "[Verse 1]\nHeadlights cutting through the midnight breeze\nOcean air moving through the coastal trees\nCassette playing our favorite disco tune\nUnderneath the golden crescent moon\n\n[Chorus]\nCruising down the midnight highway lane\nWashing away all the city pain\nTurn the volume up and let it roll\nMidnight groove taking full control",
                        "plays": 2680,
                    },
                    {
                        "title": "Champagne Sunset",
                        "style": "Smooth neo soul, jazzy Fender Rhodes, sweet vocal harmonies, tight pocket groove, 94 bpm",
                        "lyrics": "[Verse 1]\nGlass of bubbly resting in your hand\nGolden horizon over sea and sand\nSky is blushing in shades of peach and rose\nThat's the way a summer evening goes\n\n[Chorus]\nSipping on a champagne sunset dream\nColors blending in a velvet stream\nStay with me until the stars awake\nEvery breath a paradise we make",
                        "plays": 1890,
                    },
                    {
                        "title": "Plastic Fantasy",
                        "style": "Retro funk pop, synth bass, synth brass stabs, funky clavinet, bright vocal melody, 122 bpm",
                        "lyrics": "[Verse 1]\nMannequins posing behind polished glass\nWatching all the fashion lovers pass\nNeon advertisements shining bright\nLiving in a fantasy tonight\n\n[Chorus]\nPlastic fantasy, sparkling and new\nEverything is glossy, shining through\nSpin around upon the disco floor\nLeave the ordinary at the door",
                        "plays": 1370,
                    },
                    {
                        "title": "Tokyo Bay Cruise",
                        "style": "Mellow city pop, sax solo, smooth acoustic drums, chorus guitar, romantic vibe, 106 bpm",
                        "lyrics": "[Verse 1]\nRainbow bridge glowing in the dark\nSetting sail from the harbor park\nGentle waves rocking on the hull\nCity skyline so beautiful and full\n\n[Chorus]\nTokyo bay cruise gliding through the night\nSurrounded by a million points of light\nHold my hand against the salty wind\nWhere our secret romance will begin",
                        "plays": 920,
                    },
                    {
                        "title": "Neon Umbrella",
                        "style": "Mid-tempo funk ballad, electric piano, warm bass, soulful vocal performance, 98 bpm",
                        "lyrics": "[Verse 1]\nAsphalt glistening in the warm night rain\nReflecting neon colors once again\nShared an umbrella made of vivid green\nPrettiest sight the city's ever seen\n\n[Chorus]\nUnderneath our neon umbrella shelter\nWhile the city rushes in a helter-skelter\nJust the two of us inside our world\nWatching every drop of rain unfurled",
                        "plays": 710,
                    },
                ],
            },
            {
                "title": "Midnight Groove Session",
                "subtitle": "Vol. 2 · Deep Lounge & Funk",
                "desc": "심야 라운지의 묵직하고 감각적인 베이스라인과 네오 소울의 감미로움을 담은 세션 앨범.",
                "tracks": [
                    {
                        "title": "Velvet Bassline",
                        "style": "Deep funk, heavy groove bassline, syncopated hi-hats, soulful electric piano, 102 bpm",
                        "lyrics": "[Verse 1]\nFeel the low frequency rattle in your chest\nLeave behind the fatigue and the stress\nFingers moving up and down the fret\nA funky rhythm you won't soon forget\n\n[Chorus]\nRiding on the velvet bassline groove\nFind the way your body wants to move\nLock it in the pocket, feel the beat\nBringing all the rhythm to the street",
                        "plays": 2150,
                    },
                    {
                        "title": "Rooftop Cocktail",
                        "style": "Sophisticated lounge soul, muted trumpet, silky synth chords, brushed snare, 90 bpm",
                        "lyrics": "[Verse 1]\nFifty stories high above the town\nWatching all the tiny cars run down\nIce is clinking in the crystal glass\nLetting all the noisy hours pass\n\n[Chorus]\nRooftop cocktail under starry skies\nSeeing reflections in your lovely eyes\nSweet martini and a sax refrain\nSoaking in the atmosphere again",
                        "plays": 1610,
                    },
                    {
                        "title": "Last Dance at 2AM",
                        "style": "Late-night R&B, slow jam, sensual groove, warm Rhodes chords, passionate vocals, 78 bpm",
                        "lyrics": "[Verse 1]\nClub is clearing out, the lights turn low\nBartender says it's time for us to go\nJust one more record on the turntable deck\nFeel your warm breath softly on my neck\n\n[Chorus]\nLast dance at 2 AM with you\nHolding on until the night is through\nSwaying slow upon the empty floor\nWishing we could dance forevermore",
                        "plays": 1140,
                    },
                    {
                        "title": "Urban Mirage",
                        "style": "Funky disco house, 4-on-the-floor kick, synth lead, infectious hook, 120 bpm",
                        "lyrics": "[Verse 1]\nIs it real or just a trick of light?\nMirage shimmering in the city night\nReflections on the skyscraper glass\nChasing dreams that vanish as they pass\n\n[Chorus]\nUrban mirage calling out my name\nPlaying such a mesmerizing game\nFollow the illusion down the street\nTo the pounding rhythm of the beat",
                        "plays": 830,
                    },
                    {
                        "title": "Sweet Afterglow",
                        "style": "Smooth soul outro, gospel choir harmonies, warm organ, gentle outro groove, 86 bpm",
                        "lyrics": "[Verse 1]\nParty's over but the feeling stays\nMemories lingering in a golden haze\nSmiling to myself as morning nears\nRemembering the laughter and the cheers\n\n[Chorus]\nBasking in the sweet, sweet afterglow\nWatching early morning sunrise glow\nMusic echoing inside my head\nAs I finally lay down in bed",
                        "plays": 580,
                    },
                ],
            },
        ],
    },
    {
        "id": -5,
        "name": "Aetheria (에테리아)",
        "theme": "aetheria",
        "genre": "Cinematic Orchestral · Epic Fantasy · Celtic",
        "bio": "대서사시적 판타지와 광활한 자연의 경이로움을 웅장한 오케스트레이션과 켈틱 멜로디로 그려내는 시네마틱 사운드트랙 작곡가.",
        "albums": [
            {
                "title": "Chronicles of the Ancient Realm",
                "subtitle": "Vol. 1 · Celtic Legends",
                "desc": "잊혀진 고대 전설과 영웅들의 대서사시를 그린 웅장한 심포닉 오케스트라 앨범.",
                "tracks": [
                    {
                        "title": "Whispers of the Highlands",
                        "style": "Celtic orchestral, Irish whistle, fiddle, acoustic bodhran, sweeping strings, 96 bpm",
                        "lyrics": "[Verse 1]\nOver rolling hills of emerald green\nWhere the ancient standing stones are seen\nWind is singing songs of forgotten lore\nEchoing across the rugged shore\n\n[Chorus]\nHear the whispers of the highlands blow\nCarrying the spirits from below\nRise, oh travelers of the ancient way\nFollow where the highland piper plays",
                        "plays": 2540,
                    },
                    {
                        "title": "Rise of the Dragon Crest",
                        "style": "Epic trailer music, brass fanfare, thunderous taiko drums, rising string ostinato, 130 bpm",
                        "lyrics": "[Verse 1]\nShadows gather over mountain peaks\nThe guardian of the fire kingdom speaks\nDraw the royal blade and raise the shield\nPrepare to conquer on the battlefield\n\n[Chorus]\nWitness the rise of the dragon crest\nLighting fire within every hero's chest\nThrough the smoke and ashes we shall soar\nUnconquered and triumphant evermore",
                        "plays": 1950,
                    },
                    {
                        "title": "Misty Valley",
                        "style": "Pastoral fantasy, solo cello, harp, ethereal female choir, peaceful atmosphere, 75 bpm",
                        "lyrics": "[Verse 1]\nDown beneath the cliffs of misty stone\nWhere the forest speaks in undertone\nCrystal waters flowing pure and cold\nGuarding ancient mysteries untold\n\n[Chorus]\nIn the misty valley peace will reign\nHealing every weary traveler's pain\nLet the gentle waterfalls descend\nWhere all journeys find a tranquil end",
                        "plays": 1410,
                    },
                    {
                        "title": "Song of the Elders",
                        "style": "Nordic folk orchestral, tagelharpa, deep male chanting, solemn drums, 82 bpm",
                        "lyrics": "[Verse 1]\nGather round the sacred fire of oak\nListen as the tribal elders spoke\nCarve the runes into the hardened stone\nWe do not face the long night alone\n\n[Chorus]\nSing the song of the elders loud and clear\nCast away the darkness and the fear\nFrom our ancestors strength will arise\nUnderneath the northern starry skies",
                        "plays": 960,
                    },
                    {
                        "title": "Crown and Glory",
                        "style": "Majestic symphonic finale, full orchestral brass, triumphal timpani, choir climax, 115 bpm",
                        "lyrics": "[Verse 1]\nGates swing open to the grand hall door\nTrumpets sounding on the marble floor\nBanners waving in the morning breeze\nVictory brought across the seven seas\n\n[Chorus]\nFor the crown, for honor and the glory\nEtched forever in the kingdom's story\nShining bright until the end of time\nIn our triumph glorious and sublime",
                        "plays": 730,
                    },
                ],
            },
            {
                "title": "Celestial Horizons",
                "subtitle": "Vol. 2 · Stellar Ascension",
                "desc": "별들의 바다를 건너는 신화적 여정과 승천을 노래한 웅장하고 영적인 시네마틱 앨범.",
                "tracks": [
                    {
                        "title": "Across the Starry Ocean",
                        "style": "Space orchestral, soaring french horns, lush string section, starry glockenspiel, 100 bpm",
                        "lyrics": "[Verse 1]\nSailing through the silver galactic sea\nUnbound from worldly chains, completely free\nConstellations guiding through the night\nBathed in endless waves of celestial light\n\n[Chorus]\nAcross the starry ocean we will ride\nWith the cosmos flowing by our side\nBeyond the boundaries of time and space\nHeading for our destination place",
                        "plays": 2290,
                    },
                    {
                        "title": "Wings of the Valkyrie",
                        "style": "Fast-paced epic orchestral, galloping strings, triumphant female soprano, heavy percussion, 138 bpm",
                        "lyrics": "[Verse 1]\nSpears of lightning pierce the stormy cloud\nWarriors standing resolute and proud\nHear the golden wings unfold above\nBringing valor, honor, and true love\n\n[Chorus]\nOn the wings of the valkyrie we fly\nRising up into the golden sky\nTo the halls where fallen heroes dwell\nHear the victory trumpet loudly swell",
                        "plays": 1750,
                    },
                    {
                        "title": "Tears of Elysium",
                        "style": "Emotional cinematic adagio, solo violin, piano, lush orchestral pad, heartbreaking melody, 65 bpm",
                        "lyrics": "[Verse 1]\nGolden fields where fallen petals weep\nCradling memories so dark and deep\nEven in paradise sorrow finds a way\nWishing you were here with me today\n\n[Chorus]\nTears of Elysium falling from above\nIn eternal memory of our love\nThough worlds divide us far apart\nYou live forever in my aching heart",
                        "plays": 1220,
                    },
                    {
                        "title": "The Eternal Flame",
                        "style": "Inspiring hybrid orchestral, driving synth bass, tribal percussion, soaring brass, 124 bpm",
                        "lyrics": "[Verse 1]\nIn the darkest temple underground\nWhere the sacred embers can be found\nIt has burned ten thousand years or more\nLighting up the ancient stony floor\n\n[Chorus]\nFeed the eternal flame with all your might\nLet it illuminate the longest night\nNever let the burning torch go cold\nAs the ancient prophecies unfold",
                        "plays": 840,
                    },
                    {
                        "title": "Hymn of the Ascendant",
                        "style": "Grand celestial finale, massive cathedral choir, pipe organ, full orchestra crescendo, 80 bpm",
                        "lyrics": "[Verse 1]\nLight breaks through the highest vaulted dome\nThe wanderer is finally coming home\nAscending past the clouds into the sun\nThe grand heroic pilgrimage is done\n\n[Chorus]\nSing the hymn of the ascendant soul\nEvery broken fragment now made whole\nGlory echo through eternity\nEverlasting, magnificent and free",
                        "plays": 570,
                    },
                ],
            },
        ],
    },
]


def seed_database():
    print(f"Connecting to database: {DB_PATH}")
    # Backup first
    backup_path = DB_PATH.with_suffix(f".backup-{int(datetime.now().timestamp())}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Database backed up to: {backup_path.name}")

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    # Check user '제세형'
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    if not user:
        raise RuntimeError("User id 1 not found in database!")
    user_id = user["id"]
    creator_name = f"{user['display_name']} (@{user['username']})"
    print(f"Target User: {creator_name} (id={user_id})")

    # Find existing mp3 files in ComfyUI/output/yue2 to use for track seeding
    existing_mp3s = list(COMFY_YUE2_OUTPUT.glob("*.mp3"))
    if not existing_mp3s:
        raise RuntimeError(f"No existing mp3 files found in {COMFY_YUE2_OUTPUT}!")
    print(f"Found {len(existing_mp3s)} source MP3 files in ComfyUI/output/yue2 for audio seeding.")

    now = datetime.now(timezone.utc)
    mp3_idx = 0

    inserted_artists = 0
    inserted_albums = 0
    inserted_tracks = 0

    try:
        conn.execute("BEGIN IMMEDIATE")

        for a_idx, artist_data in enumerate(ARTISTS_DATA):
            artist_id = artist_data["id"]
            artist_name = artist_data["name"]
            theme = artist_data["theme"]
            bio = artist_data["bio"]
            genre = artist_data["genre"]

            print(f"\n--- Seeding Artist {a_idx+1}/5: {artist_name} (ID: {artist_id}) ---")

            # Generate Avatar & Banner
            avatar_filename = create_artist_avatar(theme, artist_name)
            banner_filename = create_artist_banner(theme, artist_name, genre)

            # Insert or replace artist profile
            conn.execute(
                """
                INSERT INTO artist_profiles (id, user_id, artist_name, bio, avatar_filename, banner_filename, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    artist_name = excluded.artist_name,
                    bio = excluded.bio,
                    avatar_filename = excluded.avatar_filename,
                    banner_filename = excluded.banner_filename,
                    updated_at = excluded.updated_at
                """,
                (artist_id, user_id, artist_name, bio, avatar_filename, banner_filename, (now - timedelta(days=random.randint(1, 14))).isoformat()),
            )
            inserted_artists += 1

            for alb_idx, album_data in enumerate(artist_data["albums"]):
                album_id = str(uuid.uuid4())
                album_title = album_data["title"]
                subtitle = album_data["subtitle"]
                desc = album_data["desc"]

                # Generate Album Cover
                cover_filename = create_album_cover(theme, artist_name, album_title, subtitle)
                alb_created = (now - timedelta(days=random.randint(1, 10), hours=random.randint(1, 23))).isoformat()

                conn.execute(
                    """
                    INSERT INTO albums (id, owner_id, title, description, cover_filename, created_at, updated_at, artist_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (album_id, user_id, album_title, desc, cover_filename, alb_created, alb_created, artist_id),
                )
                inserted_albums += 1
                print(f"  [Album {alb_idx+1}/2] {album_title} (ID: {album_id})")

                for trk_idx, track_data in enumerate(album_data["tracks"]):
                    job_id = str(uuid.uuid4())
                    prompt_id = str(uuid.uuid4())
                    title = track_data["title"]
                    style = track_data["style"]
                    lyrics = track_data["lyrics"]
                    plays = 0

                    # Release date staggered within past 7 days
                    pub_time = (now - timedelta(days=random.uniform(0.1, 6.5), hours=random.randint(1, 12))).isoformat()
                    seed = random.randint(100000000, 999999999)
                    settings = {
                        "duration": 120.0,
                        "temperature": 1.0,
                        "top_p": 0.95,
                        "top_k": 100,
                        "repetition_penalty": 1.2,
                        "planning_enabled": True,
                        "plan_temperature": 0.7,
                        "plan_top_p": 0.9,
                        "plan_top_k": 30,
                        "plan_repetition_penalty": 1.005,
                        "penalty_window": 100,
                    }

                    # Physical MP3 destination
                    output_filename = f"{job_id}_00001.mp3"
                    dest_mp3 = COMFY_YUE2_OUTPUT / output_filename

                    # Pick an existing high-quality MP3 from ComfyUI output
                    src_mp3 = existing_mp3s[mp3_idx % len(existing_mp3s)]
                    mp3_idx += 1
                    shutil.copy2(src_mp3, dest_mp3)

                    conn.execute(
                        """
                        INSERT INTO jobs (
                            id, prompt_id, mode, title, style, lyrics, created_at, updated_at,
                            status, seed, settings, source_filename, creator_id, creator_name,
                            output_filename, output_subfolder, output_type, error,
                            published_at, published_title, cover_filename, album_id, play_count, artist_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            job_id,
                            prompt_id,
                            "original",
                            title,
                            style,
                            lyrics,
                            pub_time,
                            pub_time,
                            "completed",
                            seed,
                            json.dumps(settings, ensure_ascii=False, separators=(",", ":")),
                            None,
                            user_id,
                            creator_name,
                            output_filename,
                            "yue2",
                            "output",
                            None,
                            pub_time,
                            title,
                            None,  # inherit album cover
                            album_id,
                            plays,
                            artist_id,
                        ),
                    )
                    inserted_tracks += 1
                    print(f"    - Track {trk_idx+1}/5: {title} ({plays:,} plays) -> {output_filename}")

        conn.commit()
        print("\n=== Seeding Committed Successfully! ===")
        print(f"Total Artists Seeded: {inserted_artists}")
        print(f"Total Albums Seeded:  {inserted_albums}")
        print(f"Total Tracks Seeded:  {inserted_tracks}")

    except Exception as e:
        conn.rollback()
        print(f"Error during seeding: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    seed_database()
