from services.health import uptime, ram_usage, disk_usage
from services.docker import container_status
from services.git import branch, status


async def handle_ops(update):
    message = f"""
🟢 PAOS Operations

⏱ Uptime:
{uptime()}

🧠 RAM:
{ram_usage()}

💾 Disk:
{disk_usage()}

🐳 Docker:
{container_status()}

🌿 Git:
Branch: {branch()}
Status: {status()}
"""

    await update.message.reply_text(message[:4000])