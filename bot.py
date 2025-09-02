import os, asyncio, tempfile, time, random
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile, InputMediaVideo, InputMediaPhoto
from aiogram.client.session.aiohttp import AiohttpSession
from api import Api   # tu api.py

erome = Api()

# ================== CONFIG ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en .env")

ALLOWED = {int(x.strip()) for x in os.getenv("ALLOWED_CHATS", "").split(",") if x.strip()}
if len(ALLOWED) != 1:
    raise RuntimeError("Configura exactamente 1 chat en ALLOWED_CHATS para modo privado")
CHAT_ID = next(iter(ALLOWED))

# sesión con timeout fijo
session = AiohttpSession(timeout=120)
bot = Bot(BOT_TOKEN, session=session)
dp = Dispatcher()

VIDEO_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB
TAGS = ["casero", "amateur", "latina", "filtrada", "pack", "nudes", "mamada"]

# ================== UTIL ==================
def safe_remove(path: str | Path, retries: int = 6, delay: float = 0.5) -> None:
    """Borra un archivo con reintentos (útil en Windows si está en uso)."""
    p = Path(path)
    for _ in range(retries):
        try:
            if p.exists():
                p.unlink()
            return
        except PermissionError:
            time.sleep(delay)
        except Exception:
            time.sleep(delay)

def download_video_to_temp(url: str) -> FSInputFile | None:
    """Descarga un video de Erome y lo guarda en archivo temporal, devuelve FSInputFile."""
    try:
        data = erome.get_content(url, max_video_bytes=VIDEO_SIZE_LIMIT)
        if isinstance(data, Exception) or not data:
            print("❌ no se pudo obtener bytes del video")
            return None
        if len(data) > VIDEO_SIZE_LIMIT:
            print(f"⚠️ {len(data)/1024/1024:.1f} MB, demasiado grande")
            return None

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tmp.write(data)
        tmp_path = tmp.name
        tmp.close()
        return FSInputFile(path=tmp_path, filename="video.mp4")
    except Exception as e:
        print("❌ error en descarga de video:", e)
        return None

# ================== PRIVADO ==================
@dp.message()
async def ignore_all(m: types.Message):
    if m.chat.id != CHAT_ID and (not m.from_user or m.from_user.id != CHAT_ID):
        return

# ================== TAREA AUTOMÁTICA ==================
async def auto_post():
    while True:
        tag = random.choice(TAGS)
        print(f"🔎 buscando álbumes con tag: {tag}")
        try:
            results = erome.get_all_album_data(tag, page=1, limit=5)
            print(f"📂 encontrados {len(results)} álbumes para #{tag}")

            # filtrar por título también
            filtered = [r for r in results if tag.lower() in r["title"].lower()]
            if filtered:
                results = filtered
                print(f"🔎 filtrados {len(results)} álbumes cuyo título contiene '{tag}'")

            if results:
                result = random.choice(results)
                code = result["url"].split("/a/")[-1]
                print("➡️ álbum elegido:", code)

                alb = erome.get_album_content(code)
                videos = alb.get("videos", [])
                photos = alb.get("photos", [])
                print(f"🎬 {len(videos)} videos y 🖼️ {len(photos)} fotos en el álbum")

                media = []
                temp_files = []  # guardar rutas para limpiar luego

                # agregar videos descargados
                for v in videos:
                    link = v.get("video_url")
                    if not link:
                        continue
                    video_file = download_video_to_temp(link)
                    if video_file:
                        media.append(
                            InputMediaVideo(
                                media=video_file,
                                caption=f"#{tag}" if not media else None
                            )
                        )
                        temp_files.append(video_file.path)

                # agregar fotos por URL (Telegram acepta directo)
                for img in photos:
                    if len(media) >= 10:  # máx 10 archivos en media group
                        break
                    media.append(
                        InputMediaPhoto(
                            media=img,
                            caption=f"#{tag}" if not media else None
                        )
                    )

                # enviar
                if not media:
                    print("⚠️ no se pudo armar el media group")
                elif len(media) == 1:
                    m = media[0]
                    if isinstance(m, InputMediaVideo):
                        await bot.send_video(CHAT_ID, video=m.media, caption=f"#{tag}")
                    elif isinstance(m, InputMediaPhoto):
                        await bot.send_photo(CHAT_ID, photo=m.media, caption=f"#{tag}")
                    print("✅ 1 elemento enviado individual")
                else:
                    await bot.send_media_group(CHAT_ID, media=media)
                    print(f"✅ álbum enviado como media group ({len(media)} elementos)")

                # limpiar archivos temporales
                for path in temp_files:
                    safe_remove(path)

        except Exception as e:
            print("❌ error en auto_post:", e)

        await asyncio.sleep(5)  # cada minuto

# ================== MAIN ==================
async def main():
    print("🤖 bot iniciado (modo privado, multi-tag, envía álbum completo)")
    asyncio.create_task(auto_post())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
