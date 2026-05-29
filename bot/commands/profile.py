from context.loader import read_profile_context


async def handle_profile(update):
    profile = read_profile_context()

    if not profile.strip():
        await update.message.reply_text(
            "Profile context not found."
        )
        return

    message = f"""
👤 PAOS Profile

{profile[:3800]}
"""

    await update.message.reply_text(message[:4000])