import dotenv

# Prepare the environment
dotenv.load_dotenv()

import os
import typing
import pytz
import telegram
import logging
import dotenv
from modules.chat import Chat
from modules.google import Google
from modules.memory import clear_history
from modules.schedule import Scheduler
from utils.auth import auth
from telegram.helpers import escape_markdown
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    PicklePersistence,
    Defaults,
    filters,
)

# logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# set the global timezone. TODO configure per user.
os.environ["TZ"] = "Europe/Berlin"

application = (
    Application.builder()
    .token(os.environ.get("TELEGRAM_API_KEY"))
    .persistence(PicklePersistence(filepath="./data/data.pickle"))
    .defaults(defaults=Defaults(tzinfo=pytz.timezone(os.environ["TZ"])))
    .build()
)

# dict of browser instances for each user.
chats: typing.Dict[str, Chat] = {}

# set up the Google API
google = Google(os.getenv("SERP_API_KEY"))

# set up the scheduler
scheduler = Scheduler(application.job_queue)


@auth()
async def send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send message to OpenAI"""
    chat = get_chat(update, context)

    async def typing():
        await application.bot.send_chat_action(update.effective_chat.id, "typing")

    # get the response from the API
    response = await chat.send_message(
        update.message.text, typing=typing, context=context
    )

    response = escape_markdown(response, version=2)

    # send the response to the user
    await update.message.reply_text(
        response, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
    )


@auth()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "You are ready to start using Assistant. Say hello!"
    )


@auth()
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the browser instance for the user."""
    key = update.effective_user.id

    if key in chats:
        await update.message.reply_text("Resetting your assistant...")

        # clear the chat instance and history
        await clear_history(context)
        del chats[key]

        # create a new chat instance
        chats[key] = Chat(context=None)

    await update.message.reply_text(
        "You are ready to start using Assistant. Say hello!"
    )


@auth()
async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the browser instance for the user."""
    chat = get_chat(update, context)

    async def typing():
        await application.bot.send_chat_action(update.effective_chat.id, "typing")

    response = await google.google(
        update.message.text.replace("/browse", "").strip(),
        chat=chat,
        typing=typing,
        context=context,
    )

    response = escape_markdown(response, version=2)

    await update.message.reply_text(
        response, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
    )


@auth()
async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Schedule an event for the user."""

    async def typing():
        await application.bot.send_chat_action(update.effective_chat.id, "typing")

    response = await scheduler.schedule(
        update.message.text.replace("/schedule", "").strip(),
        username=update.effective_user.username,
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        typing=typing,
    )

    response = escape_markdown(response, version=2)

    await update.message.reply_text(
        response, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
    )


def get_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Chat:
    """Get the chat instance for the user."""
    key = update.effective_user.id

    # create a chat instance for the user if not already present
    if key not in chats:
        chats[key] = Chat(context)

    return chats[key]


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    print(f"Update {update} caused error {context.error}")
    logger.warning('Error "%s"', context.error)


def main():
    # Handle messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, send),
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("schedule", schedule))
    application.add_handler(CommandHandler("browse", browse))
    application.add_error_handler(error)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
