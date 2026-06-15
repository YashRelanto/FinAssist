import json
import logging
import re
from typing import Any, List

import openai

from app.core.config import settings
from .models import ParsedTransaction
from .transaction_extractor import TransactionExtractor

logger = logging.getLogger(__name__)

NVIDIA_NIM_BASE_URL = settings.NVIDIA_BASE_URL


class LLMTransactionParser:
    """
    Last-resort statement parser. It is intentionally kept outside the
    deterministic extractor so LLM usage only happens when the rule pipeline
    cannot extract any transactions.
    """

    MAX_TEXT_CHARS = 60000

    @classmethod
    def parse_transactions(cls, text: str, detected_bank: str) -> List[ParsedTransaction]:
        if not settings.NVIDIA_API_KEY:
            logger.warning("Statement LLM fallback skipped: NVIDIA_API_KEY not configured")
            return []

        statement_text = (text or "").strip()
        if not statement_text:
            return []

        system_prompt = (
            "You extract bank statement transactions for FinAssist.\n"
            "Return ONLY valid JSON with this exact shape:\n"
            "{\n"
            '  "transactions": [\n'
            "    {\n"
            '      "transaction_date": "YYYY-MM-DD",\n'
            '      "amount": number,\n'
            '      "transaction_type": "income" | "expense",\n'
            '      "description": string,\n'
            '      "merchant_name": string,\n'
            '      "running_balance": number | null\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Use positive amount magnitudes. Do not include opening balances, "
            "closing balances, page totals, statement summaries, or headers. "
            "When debit/credit is not explicit, infer type from running balance "
            "movement if balances are available. Do not invent transactions."
        )
        user_payload = {
            "detected_bank": detected_bank,
            "statement_text": statement_text[: cls.MAX_TEXT_CHARS],
        }

        logger.info(
            "Statement LLM fallback via NVIDIA NIM model=%s base_url=%s",
            settings.active_chat_model,
            NVIDIA_NIM_BASE_URL,
        )

        try:
            client = openai.OpenAI(
                api_key=settings.NVIDIA_API_KEY,
                base_url=NVIDIA_NIM_BASE_URL,
            )
            completion = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                temperature=0,
                max_tokens=8192,
            )
            raw = (completion.choices[0].message.content or "").strip()
            data = cls._load_json(raw)
            return cls._coerce_transactions(data.get("transactions") if isinstance(data, dict) else [])
        except Exception as exc:
            logger.error("Statement LLM fallback failed: %s", exc)
            return []

    @staticmethod
    def _load_json(raw: str) -> dict[str, Any]:
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)

    @staticmethod
    def _coerce_transactions(rows: Any) -> List[ParsedTransaction]:
        if not isinstance(rows, list):
            return []

        transactions: List[ParsedTransaction] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            parsed_date = TransactionExtractor._parse_date(str(row.get("transaction_date") or ""))
            amount = TransactionExtractor._parse_amount(str(row.get("amount") or ""))
            if not parsed_date or amount is None or amount <= 0:
                continue

            tx_type = str(row.get("transaction_type") or "").strip().lower()
            if tx_type in ["credit", "cr", "income"]:
                tx_type = "income"
            elif tx_type in ["debit", "dr", "expense", "withdrawal"]:
                tx_type = "expense"
            else:
                tx_type = "expense"

            description = re.sub(r"\s+", " ", str(row.get("description") or "")).strip()
            merchant_name = re.sub(r"\s+", " ", str(row.get("merchant_name") or "")).strip()
            if not description:
                description = merchant_name or "Transaction"
            if not merchant_name:
                merchant_name = description[:50]

            balance = None
            if row.get("running_balance") is not None:
                balance = TransactionExtractor._parse_amount(str(row.get("running_balance")))

            transactions.append(ParsedTransaction(
                transaction_date=parsed_date,
                amount=amount,
                transaction_type=tx_type,
                description=description,
                merchant_name=merchant_name[:50],
                running_balance=balance,
            ))

        return transactions
