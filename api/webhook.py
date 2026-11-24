import os
import asyncio
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

INSTABOX_BASE_URL = os.getenv("INSTABOX_BASE_URL", "https://api.instabox.sh/v1")


def get_config():
    required = ["TELEGRAM_TOKEN", "CHAT_ID", "INSTABOX_API_KEY", "INSTABOX_VM_ID"]
    missing = [k for k in required if not os.getenv(k, "").strip()]
    if missing:
        return None, f"Environment variable belum terbaca: {', '.join(missing)}"

    raw_chat_id = os.getenv("CHAT_ID", "").strip().strip('"').strip("'")
    if not raw_chat_id.lstrip("-").isdigit():
        return None, f"Format CHAT_ID harus berupa angka murni, terbaca: {raw_chat_id}"

    return {
        "telegram_token": os.getenv("TELEGRAM_TOKEN").strip().strip('"'),
        "chat_id": int(raw_chat_id),
        "instabox_api_key": os.getenv("INSTABOX_API_KEY").strip().strip('"'),
        "instabox_vm_id": os.getenv("INSTABOX_VM_ID").strip().strip('"'),
    }, None


@app.get("/")
@app.get("/api/webhook")
async def check_status():
    cfg, err = get_config()
    if err:
        return {"status": "error_config", "detail": err}
    return {"status": "Vercel Webhook aktif dan siap digunakan"}


async def wake_and_run_instabox(cfg: dict):
    headers = {
        "Authorization": f"Bearer {cfg['instabox_api_key']}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        res_wake = await client.post(
            f"{INSTABOX_BASE_URL}/boxes/{cfg['instabox_vm_id']}/resume",
            headers=headers,
        )
        res_wake.raise_for_status()

        await asyncio.sleep(2)

        cmd = (
            "nohup timeout 12m ~/bounty-hunter/venv/bin/python3 "
            "~/bounty-hunter/bounty_worker.py > /tmp/worker.log 2>&1 &"
        )
        res_exec = await client.post(
            f"{INSTABOX_BASE_URL}/boxes/{cfg['instabox_vm_id']}/exec",
            headers=headers,
            json={"command": cmd},
        )
        res_exec.raise_for_status()


@app.post("/")
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    cfg, err = get_config()
    if err:
        return {"ok": False, "error": err}

    tg_api = f"https://api.telegram.org/bot{cfg['telegram_token']}"
    data = await req.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        if chat_id != cfg["chat_id"]:
            return {"ok": True}

        keyboard = {
            "inline_keyboard": [
                [{"text": "🚀 Mulai Berburu Bounty", "callback_data": "hunt_bounty"}]
            ]
        }
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{tg_api}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "Panel Bounty Hunter siap. Tekan tombol di bawah untuk membangunkan InstaBox:",
                    "reply_markup": keyboard,
                },
            )

    elif "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        if chat_id != cfg["chat_id"]:
            return {"ok": True}

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{tg_api}/answerCallbackQuery",
                json={
                    "callback_query_id": cb["id"],
                    "text": "Perintah diterima! Membangunkan InstaBox...",
                },
            )

        try:
            await wake_and_run_instabox(cfg)
        except Exception as wake_err:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"{tg_api}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"❌ Gagal membangunkan InstaBox:\n`{str(wake_err)}`",
                        "parse_mode": "Markdown",
                    },
                )

    return {"ok": True}
