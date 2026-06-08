import re
from typing import Dict, Any, List

BANK_CONFIGS: Dict[str, Dict[str, Any]] = {
    "HDFC": {
        "bank_name": "HDFC Bank",
        "signatures": [
            r"hdfc bank",
            r"hdfcbank",
            r"housing development finance corporation",
        ],
        "ifsc_prefixes": ["HDFC"],
        "account_number_patterns": [
            r"\b(?:account\s+no|account\s+number|account\s+no\.?)\b\s*[\-:：]?\s*([0-9]{9,18})\b",
            r"\b(?:customer\s+id|cust\s+id)\b\s*[\-:：]?\s*([0-9]{9,18})\b"
        ],
        "account_holder_patterns": [
            r"MR\s+([A-Z\s\.]{3,40})\n",
            r"MS\s+([A-Z\s\.]{3,40})\n",
            r"\b(?:account\s+holder|customer\s+name|name\s+of\s+account\s+holder|name)\b\s*[\-:：]?\s*([A-Za-z\s\.]{3,40})"
        ],
        "table_start_patterns": [
            r"Date\s+Narration\s+Chq\./Ref\.No\.\s+Value\s+Dt\s+Withdrawal\s+Amt\.\s+Deposit\s+Amt\.\s+Closing\s+Balance",
            r"Date\s+Narration\s+Chq\.\s*No\.\s+Date\s+Debit\s+Credit\s+Balance"
        ],
        "table_end_patterns": [
            r"STATEMENT\s+SUMMARY",
            r"Brought\s+Forward",
            r"Page\s+Total",
            r"This\s+is\s+a\s+computer\s+generated\s+statement",
        ],
        "date_format": "%d/%m/%y",
        "parser_profile": "fixed_table",
        "columns": {
            "date_idx": 0,
            "narration_idx": 1,
            "debit_idx": -3,
            "credit_idx": -2,
            "balance_idx": -1
        }
    },
    "ICICI": {
        "bank_name": "ICICI Bank",
        "signatures": [
            r"icici bank",
            r"icicibank",
            r"khayaal aapka"
        ],
        "ifsc_prefixes": ["ICIC"],
        "account_number_patterns": [
            r"\b(?:savings\s+a/c|savings\s+account|account\s+number|account\s+no\.?)\b\s*([0-9]{12})\b",
            r"\b(\d{12})\b"
        ],
        "account_holder_patterns": [
            r"MR\.([A-Z\s\.]{3,40})\n",
            r"MS\.([A-Z\s\.]{3,40})\n",
            r"MR\s+([A-Z\s\.]{3,40})\n",
            r"\b(?:customer\s+name|name|account\s+holder)\b\s*[\-:：]?\s*([A-Za-z\s\.]{3,40})"
        ],
        "table_start_patterns": [
            r"DATE\s+MODE.*?\s+PARTICULARS\s+DEPOSITS\s+WITHDRAWALS\s+BALANCE",
            r"DATE\s+PARTICULARS\s+DEPOSITS\s+WITHDRAWALS\s+BALANCE",
            r"Transaction\s+Date\s+Value\s+Date\s+Cheque\s*No\.\s+Description\s+Amount\s+Balance"
        ],
        "table_end_patterns": [
            r"Total\s+outstanding",
            r"Carried\s+Forward",
            r"Legend\s+used\s+in\s+statement",
        ],
        "date_format": "%d-%m-%Y",
        "parser_profile": "fixed_table",
        "columns": {
            "date_idx": 0,
            "narration_idx": 2,
            "debit_idx": -3,
            "credit_idx": -2,
            "balance_idx": -1
        }
    },
    "KVB": {
        "bank_name": "Karur Vysya Bank",
        "signatures": [
            r"karur vysya bank",
            r"kvb",
            r"smart way to bank"
        ],
        "ifsc_prefixes": ["KVBL"],
        "account_number_patterns": [
            r"\b(?:acc\.no\.|account\s+number|a/c\s+no\.?)\b\s*[\-:：]?\s*([0-9]{15,16})\b",
            r"\b(\d{15,16})\b"
        ],
        "account_holder_patterns": [
            r"^([A-Z\s\.]{3,40})\n",
            r"\b(?:customer\s+name|name|account\s+holder)\b\s*[\-:：]?\s*([A-Za-z\s\.]{3,40})"
        ],
        "table_start_patterns": [
            r"Txn\s+Date\s+Value\s+Date\s+Particulars\s+Ref\.\s*No\.\s+Debit\s+Credit\s+Balance",
            r"Txn\s+Date\s+Value\s+Date\s+Particulars\s+Debit\s+Credit\s+Balance"
        ],
        "table_end_patterns": [
            r"This\s+is\s+a\s+computer\s+generated\s+statement",
            r"Note\s*:",
        ],
        "date_format": "%d-%b-%Y",
        "parser_profile": "fixed_table",
        "columns": {
            "date_idx": 0,
            "narration_idx": 2,
            "debit_idx": -3,
            "credit_idx": -2,
            "balance_idx": -1
        }
    },
    "BOB": {
        "bank_name": "Bank of Baroda",
        "signatures": [
            r"bank of baroda",
            r"bob world",
            r"bob"
        ],
        "ifsc_prefixes": ["BARB"],
        "account_number_patterns": [
            r"\b(?:account\s+number|acc\.no\.|a/c\s+no\.?)\b\s*[\-:：]?\s*([0-9]{14})\b",
            r"\b(\d{14})\b"
        ],
        "account_holder_patterns": [
            r"Customer\s+Name\s*\n\s*([A-Z\s\.]{3,40})",
            r"\b(?:customer\s+name|name|account\s+holder)\b\s*[\-:：]?\s*([A-Za-z\s\.]{3,40})"
        ],
        "table_start_patterns": [
            r"Serial\s+Transaction\s+Value\s+Description\s+Cheque\s+Debit\s+Credit\s+Balance",
            r"Serial\s+No\s+Transaction\s+Date\s+Description\s+Debit\s+Credit\s+Balance"
        ],
        "table_end_patterns": [
            r"Note\s*:",
            r"This\s+is\s+a\s+computer\s+generated\s+statement",
        ],
        "date_format": "%d-%m-%Y",
        "parser_profile": "fixed_table",
        "columns": {
            "date_idx": 1,
            "narration_idx": 3,
            "debit_idx": -3,
            "credit_idx": -2,
            "balance_idx": -1
        }
    },
    "KOTAK": {
        "bank_name": "Kotak Mahindra Bank",
        "signatures": [
            r"kotak mahindra bank",
            r"kotak bank",
            r"kotak"
        ],
        "ifsc_prefixes": ["KKBK"],
        "account_number_patterns": [
            r"\b(?:account\s+no|account\s+number|account\s+no\.?)\b\s*[\-:：]?\s*([0-9]{9,18})\b"
        ],
        "account_holder_patterns": [
            r"([A-Z \t\.]{3,30})\s{2,}.*?\n.*?\n\s*(?:W/O|C/O|S/O|D/O|S/D/W\s+OF)",
            r"\b(?:customer\s+name|name|account\s+holder)\b\s*[\-:：]?\s*([A-Za-z\s\.]{3,40})"
        ],
        "table_start_patterns": [
            r"Date\s+Narration\s+Chq/Ref\s*No",
            r"Withdrawal\s*\(Dr\)/\s*Deposit\s*\(Cr\)"
        ],
        "table_end_patterns": [
            r"This\s+is\s+a\s+computer\s+generated\s+statement",
            r"STATEMENT\s+SUMMARY",
            r"Brought\s+Forward",
            r"Page\s+Total"
        ],
        "date_format": "%d-%m-%Y",
        "parser_profile": "fixed_table",
        "columns": {
            "date_idx": 0,
            "amount_idx": -2,
            "type_idx": -2,
            "balance_idx": -1
        }
    }
}
