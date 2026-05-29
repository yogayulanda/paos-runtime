import subprocess

from context.loader import load_env


async def handle_digest(update):
    env = load_env()

    runtime_path = env.get(
        "PAOS_RUNTIME_PATH",
        "/home/ubuntu/paos/paos-runtime",
    )

    await update.message.reply_text("Running digest...")

    command = (
        f"{runtime_path}/venv/bin/python "
        f"{runtime_path}/workers/ai-digest.py "
        f">> {runtime_path}/logs/ai-digest.log 2>&1"
    )

    subprocess.run(command, shell=True)

    await update.message.reply_text("Digest completed.")