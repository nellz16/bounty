import os
import asyncio
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ["CHAT_ID"])
INSTABOX_API_KEY = os.environ["INSTABOX_API_KEY"]
INSTABOX_VM_ID = os.environ["INSTABOX_VM_ID"]
INSTABOX_BASE_URL = os.getenv("INSTABOX_BASE_URL", "https://api.instabox.sh/v1")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


@app.get("/api/webhook")
async def check_status():
    return {"status": "Vercel Webhook aktif"}


async def wake_and_run_instabox():
    headers = {
        "Authorization": f"Bearer {INSTABOX_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        res_wake = await client.post(
            f"{INSTABOX_BASE_URL}/boxes/{INSTABOX_VM_ID}/resume",
            headers=headers,
        )
        res_wake.raise_for_status()

        await asyncio.sleep(2)

        cmd = (
            "nohup timeout 12m ~/bounty-hunter/venv/bin/python3 "
            "~/bounty-hunter/bounty_worker.py > /tmp/worker.log 2>&1 &"
        )
        res_exec = await client.post(
            f"{INSTABOX_BASE_URL}/boxes/{INSTABOX_VM_ID}/exec",
            headers=headers,
            json={"command": cmd},
        )
        res_exec.raise_for_status()


@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        if chat_id != ALLOWED_CHAT_ID:
            return {"ok": True}

        keyboard = {
            "inline_keyboard": [
                [{"text": "🚀 Mulai Berburu Bounty", "callback_data": "hunt_bounty"}]
            ]
        }
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{TG_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "Panel Bounty Hunter siap. Tekan tombol di bawah untuk membangunkan InstaBox:",
                    "reply_markup": keyboard,
                },
            )

    elif "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        if chat_id != ALLOWED_CHAT_ID:
            return {"ok": True}

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{TG_API}/answerCallbackQuery",
                json={
                    "callback_query_id": cb["id"],
                    "text": "Perintah diterima! Membangunkan InstaBox...",
                },
            )

        try:
            await wake_and_run_instabox()
        except Exception as err:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"{TG_API}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"❌ Gagal membangunkan InstaBox:\n`{str(err)}`",
                        "parse_mode": "Markdown",
                    },
                )

    return {"ok": True}
