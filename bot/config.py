from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Config:
    bot_token: str
    database_url: str
    openrouter_api_key: str
    admin_ids: List[int]
    # Prices in kopecks
    price_lab_docx: int
    price_presentation: int
    price_text_answer: int
    price_lab_plus_pres: int
    price_extra_edit: int
    price_subscription_30d: int
    # 1 Telegram Star = N kopecks
    kopecks_per_star: int
    # Referral bonuses in kopecks
    referral_bonus_invitee: int   # 50 ₽ for the invited user
    referral_bonus_inviter: int   # 75 ₽ for the inviter after first order
    # Misc
    support_username: str
    referral_code_prefix: str
    order_edit_days_limit: int


def load_config() -> Config:
    raw_ids = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(i.strip()) for i in raw_ids.split(",") if i.strip()]

    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        database_url=os.environ["DATABASE_URL"],
        openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
        admin_ids=admin_ids,
        price_lab_docx=int(os.getenv("PRICE_LAB_DOCX", "15000")),
        price_presentation=int(os.getenv("PRICE_PRESENTATION", "18000")),
        price_text_answer=int(os.getenv("PRICE_TEXT_ANSWER", "2000")),
        price_lab_plus_pres=int(os.getenv("PRICE_LAB_PLUS_PRES", "28000")),
        price_extra_edit=int(os.getenv("PRICE_EXTRA_EDIT", "1500")),
        price_subscription_30d=int(os.getenv("PRICE_SUBSCRIPTION_30D", "99900")),
        kopecks_per_star=int(os.getenv("KOPECKS_PER_STAR", "200")),
        referral_bonus_invitee=int(os.getenv("REFERRAL_BONUS_INVITEE", "5000")),
        referral_bonus_inviter=int(os.getenv("REFERRAL_BONUS_INVITER", "7500")),
        support_username=os.getenv("SUPPORT_USERNAME", "@support"),
        referral_code_prefix=os.getenv("REFERRAL_CODE_PREFIX", "UCH"),
        order_edit_days_limit=int(os.getenv("ORDER_EDIT_DAYS_LIMIT", "7")),
    )


config = load_config()

MODEL_DEFAULT = "google/gemini-2.0-flash-001"
MODEL_PRESENTATION = "anthropic/claude-sonnet-4-6"
VIP_DAILY_LIMIT = 3
SUPPORT_USERNAME = "Uchenikbot_adm"
OZON_CARD_NUMBER = os.getenv("OZON_CARD_NUMBER", "0000 0000 0000 0000")
OZON_CARD_OWNER = os.getenv("OZON_CARD_OWNER", "Имя Фамилия")
OZON_SBP_LINK = os.getenv(
    "OZON_SBP_LINK",
    "https://finance.ozon.ru/apps/sbp/ozonbankpay/019e644b-9096-782b-8ffc-9368ae8a641f",
)
