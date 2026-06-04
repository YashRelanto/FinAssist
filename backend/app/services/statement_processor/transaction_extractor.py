import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from .models import ParsedTransaction
from .bank_configs import BANK_CONFIGS

class TransactionExtractor:
    """
    Parses transaction rows from statement raw text.
    Combines vertical columnar block parsing, horizontal sequential parsing, and generic flat fallbacks.
    """

    _DATE_FORMATS = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%y",
        "%d %b %Y", "%d %b %y", "%d-%b-%Y", "%d-%b-%y", "%d %B %Y",
        "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y",
    ]

    _MONTHS_MAP = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06", 
        "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
    }

    @classmethod
    def _parse_date(cls, date_str: str) -> Optional[str]:
        date_str = date_str.strip().replace(",", " ").replace("  ", " ")
        
        # Sequentially map common formats like "01-Jan-2026"
        seq_match = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", date_str, re.IGNORECASE)
        if seq_match:
            day = f"{int(seq_match.group(1)):02d}"
            mon = cls._MONTHS_MAP.get(seq_match.group(2).lower(), "01")
            yr = seq_match.group(3)
            return f"{yr}-{mon}-{day}"

        for fmt in cls._DATE_FORMATS:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 2000 and len(date_str) <= 8:
                    dt = dt.replace(year=dt.year + 2000)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    @classmethod
    def _parse_amount(cls, amount_str: str) -> Optional[float]:
        if not amount_str:
            return None
        cleaned = amount_str.strip()
        cleaned = re.sub(r"[₹$Rs\s]", "", cleaned)
        cleaned = re.sub(r"(CR|DR|cr|dr)$", "", cleaned).strip()
        if not cleaned or cleaned in ["-", "."]:
            return None
        # Handle Indian comma-decimal formats (e.g. 22,00 -> 22.00) vs standard thousands commas
        if re.fullmatch(r"\d{1,9},\d{2}", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return abs(float(cleaned))
        except (ValueError, TypeError):
            return None

    @classmethod
    def _parse_config_driven_table(cls, text: str, config: Dict[str, Any]) -> List[ParsedTransaction]:
        """
        Generic parsing engine driven by config templates.
        Locates the transaction table, parses row-by-row, and extracts columns based on configured indices.
        """
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines or not config:
            return []

        # ── Step 1: Detect Table Start ──
        table_started = False
        start_idx = 0
        for idx, line in enumerate(lines):
            for pat in config.get("table_start_patterns", []):
                if re.search(pat, line, re.IGNORECASE):
                    table_started = True
                    start_idx = idx + 1
                    break
            if table_started:
                break

        if not table_started:
            return []

        # ── Step 2: Iterate Rows and Parse ──
        transactions = []
        cols = config.get("columns", {})
        
        # Matches typical date formats
        date_pattern = re.compile(
            r"(\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b|"
            r"\b\d{4}[-/\s]+\d{1,2}[-/\s]+\d{1,2}\b)"
        )

        for line in lines[start_idx:]:
            # Check Table End Markers
            is_end = False
            for pat in config.get("table_end_patterns", []):
                if re.search(pat, line, re.IGNORECASE):
                    is_end = True
                    break
            if is_end:
                break

            # Parse Row columns by tokens
            tokens = [t.strip() for t in line.split() if t.strip()]
            if len(tokens) < 3:
                # Narration continuation line (no date, no amounts)
                if transactions and len(tokens) > 0:
                    transactions[-1].description += " " + " ".join(tokens)
                    transactions[-1].description = re.sub(r"\s+", " ", transactions[-1].description).strip()
                    transactions[-1].merchant_name = transactions[-1].description[:50]
                continue

            # Check if this token matches a date to confirm it's a new transaction row
            first_token_date = date_pattern.match(tokens[0])
            if not first_token_date:
                if transactions:
                    transactions[-1].description += " " + " ".join(tokens)
                    transactions[-1].description = re.sub(r"\s+", " ", transactions[-1].description).strip()
                    transactions[-1].merchant_name = transactions[-1].description[:50]
                continue

            # Extract fields based on column configurations
            try:
                date_val = tokens[cols["date_idx"]]
                parsed_date = cls._parse_date(date_val)
                if not parsed_date:
                    continue

                # Get balance
                balance = None
                if "balance_idx" in cols:
                    balance_idx = cols["balance_idx"]
                    balance_idx_resolved = len(tokens) + balance_idx if balance_idx < 0 else balance_idx
                    if 0 <= balance_idx_resolved < len(tokens):
                        balance = cls._parse_amount(tokens[balance_idx_resolved])

                # Get amounts
                debit = 0.0
                credit = 0.0
                amount = 0.0
                tx_type = "expense"

                if "debit_idx" in cols and "credit_idx" in cols:
                    deb_idx = cols["debit_idx"]
                    cred_idx = cols["credit_idx"]
                    deb_idx_resolved = len(tokens) + deb_idx if deb_idx < 0 else deb_idx
                    cred_idx_resolved = len(tokens) + cred_idx if cred_idx < 0 else cred_idx
                    
                    if 0 <= deb_idx_resolved < len(tokens):
                        debit = cls._parse_amount(tokens[deb_idx_resolved]) or 0.0
                    if 0 <= cred_idx_resolved < len(tokens):
                        credit = cls._parse_amount(tokens[cred_idx_resolved]) or 0.0
                    
                    if credit > 0:
                        amount = credit
                        tx_type = "income"
                    else:
                        amount = debit
                        tx_type = "expense"
                elif "amount_idx" in cols:
                    amt_idx = cols["amount_idx"]
                    amt_idx_resolved = len(tokens) + amt_idx if amt_idx < 0 else amt_idx
                    if 0 <= amt_idx_resolved < len(tokens):
                        amount = cls._parse_amount(tokens[amt_idx_resolved]) or 0.0
                        
                    if "type_idx" in cols:
                        t_idx = cols["type_idx"]
                        t_idx_resolved = len(tokens) + t_idx if t_idx < 0 else t_idx
                        if 0 <= t_idx_resolved < len(tokens):
                            type_flag = tokens[t_idx_resolved].lower()
                            if "cr" in type_flag or "c" == type_flag:
                                tx_type = "income"
                            else:
                                tx_type = "expense"

                # Get narration description (everything in between)
                all_indices = set(range(len(tokens)))
                used_indices = {cols["date_idx"]}
                if "value_date_idx" in cols:
                    used_indices.add(cols["value_date_idx"])
                if "debit_idx" in cols:
                    used_indices.add(len(tokens) + cols["debit_idx"] if cols["debit_idx"] < 0 else cols["debit_idx"])
                if "credit_idx" in cols:
                    used_indices.add(len(tokens) + cols["credit_idx"] if cols["credit_idx"] < 0 else cols["credit_idx"])
                if "amount_idx" in cols:
                    used_indices.add(len(tokens) + cols["amount_idx"] if cols["amount_idx"] < 0 else cols["amount_idx"])
                if "type_idx" in cols:
                    used_indices.add(len(tokens) + cols["type_idx"] if cols["type_idx"] < 0 else cols["type_idx"])
                if "balance_idx" in cols:
                    used_indices.add(len(tokens) + cols["balance_idx"] if cols["balance_idx"] < 0 else cols["balance_idx"])

                desc_tokens = [tokens[idx] for idx in sorted(list(all_indices - used_indices))]
                description = " ".join(desc_tokens).strip()

                if not any(k in description.upper() for k in ["B/F", "BROUGHT FORWARD", "BALANCE FORWARD", "OPENING BALANCE", "OPENING BAL"]):
                    transactions.append(ParsedTransaction(
                        transaction_date=parsed_date,
                        amount=amount,
                        transaction_type=tx_type,
                        description=description,
                        merchant_name=description[:50],
                        running_balance=balance
                    ))
            except Exception:
                continue

        return transactions

    @classmethod
    def _parse_vertical_columnar_blocks(cls, text: str) -> List[ParsedTransaction]:
        """
        Parses vertical/multi-line column text dumps (where columns are printed vertically line-by-line).
        Matches: Date -> Narration -> Ref number -> Date -> Amount 1 -> Amount 2 -> Narration continuation.
        """
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        # Filter out repeated page header/footer and address junk lines
        cleaned_lines = []
        skip_words = [
            "page no", "joint holders", "nomination :", "statement of account",
            "account branch", "od limit", "cust id", "account status", "rtgs/neft ifsc",
            "micr :", "branch code", "account type", "hdfc bank limited", "closing balance includes",
            "contents of this statement", "is that on record with the bank", "state account branch gstn",
            "gstin number details", "registered office address", "a/c open date", "open date", "cust_id",
            "triveni appartment", "doranda ranchi", "ranchi 834002", "jharkhand india", "near hotel green",
            "near hotal green", "airport road", "air port road", "hinoo doranda", "yash rohan", "valued customer",
            "karur vysya bank", "icici bank", "bank of baroda", "chq./ref.no.", "value dt", "withdrawal amt.",
            "deposit amt.", "closing balance", "narration", "serial transaction", "value description",
            "txn date", "particulars", "ref. no.", "debit", "credit", "balance", "txn_date", "mode",
            "outstanding", "carried forward", "brought forward", "page_no", "page total", "legend used",
            "account no", "account number", "customer name", "nomination registered", "this statement",
            "dr count", "cr count", "generated on:", "generated by:", "does not require signature",
            "computer generated statement", "closing bal"
        ]
        
        for l in lines:
            l_lower = l.lower()
            # Stop adding lines if we hit the end-of-statement summary
            if "statement summary" in l_lower or ("summary of account" in l_lower and "from" not in l_lower):
                break
            # 1. Skip lines starting with colon (key-value metadata field values)
            if l.startswith(":"):
                continue
            # 2. Skip lines containing known header/footer words
            if any(w in l_lower for w in skip_words):
                continue
            # 3. Skip single titles/names isolated on page boundaries
            if l.strip() in ["MR", "MS", "MR.", "MS.", "DR.", "M/S", "MR YASH ROHAN", "MS YASH ROHAN", "City", "State", "Address", "Phone no.", "Phone no", "OD Limit", "Currency", "Email", "Cust ID", "Account No", "A/C Open Date", "Account Status", "Branch Code", "Account Type"]:
                continue
            # 4. Skip email addresses
            if "@" in l_lower and any(dom in l_lower for dom in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]):
                continue
            # 5. Skip specific key-value structured prefix lines
            if l_lower.startswith("address") or l_lower.startswith("city") or l_lower.startswith("state") or l_lower.startswith("phone no") or l_lower.startswith("currency") or l_lower.startswith("email"):
                continue
            if l_lower.startswith("from :") or l_lower.startswith("to :") or l_lower.startswith("from:") or l_lower.startswith("to:"):
                continue
            cleaned_lines.append(l)
            
        lines = cleaned_lines
        
        # Date regex for lines (dd/mm/yy or dd/mm/yyyy)
        date_regex = re.compile(r"^\b\d{1,2}/\d{1,2}/\d{2,4}\b$")
        amount_regex = re.compile(r"^\b[-+]?\s*[\d,]+\.\d{2}\b$")
        ref_regex = re.compile(r"^\d{12,18}$")

        date_indices = []
        for idx, line in enumerate(lines):
            if date_regex.match(line):
                date_indices.append(idx)

        transactions = []
        i = 0
        num_dates = len(date_indices)

        while i < num_dates:
            start_idx = date_indices[i]
            val_date_idx = None
            next_tx_date_idx_ptr = i + 1
            
            # Scan forward to find the next actual transaction start date, skipping the current value date
            for j in range(i + 1, num_dates):
                candidate_idx = date_indices[j]
                if candidate_idx - start_idx <= 8 and val_date_idx is None:
                    val_date_idx = candidate_idx
                else:
                    next_tx_date_idx_ptr = j
                    break
            else:
                next_tx_date_idx_ptr = num_dates

            end_idx = date_indices[next_tx_date_idx_ptr] if next_tx_date_idx_ptr < num_dates else len(lines)
            block_lines = lines[start_idx:end_idx]

            tx_date_str = block_lines[0]
            block_val_date_idx = None
            for idx, line in enumerate(block_lines[1:], start=1):
                if date_regex.match(line):
                    block_val_date_idx = idx
                    break

            if block_val_date_idx:
                # Narration lines are between Tx Date and Value Date
                narration_parts = []
                for line in block_lines[1:block_val_date_idx]:
                    if not ref_regex.match(line):
                        if not any(k in line.lower() for k in ["page no", "joint holders", "statement of account"]):
                            narration_parts.append(line)

                # Parse amounts and narration continuation after Value Date
                amount_vals = []
                continuation_parts = []
                
                for line in block_lines[block_val_date_idx + 1:]:
                    if amount_regex.match(line):
                        cleaned_amt = line.replace(",", "")
                        try:
                            amount_vals.append(float(cleaned_amt))
                        except ValueError:
                            pass
                    else:
                        if not any(k in line.lower() for k in ["page no", "joint holders", "statement of account"]):
                            continuation_parts.append(line)

                if amount_vals:
                    tx_amount = amount_vals[0]
                    balance = amount_vals[1] if len(amount_vals) >= 2 else None

                    # Combine description
                    description = " ".join(narration_parts + continuation_parts)
                    description = re.sub(r"\s+", " ", description).strip()

                    parsed_date = cls._parse_date(tx_date_str)
                    if parsed_date:
                        # Fallback keyword match
                        tx_type = "expense"
                        desc_lower = description.lower()
                        if any(k in desc_lower for k in ["salary", "refund", "deposit", "credit", "interest", "received"]):
                            tx_type = "income"

                        transactions.append(ParsedTransaction(
                            transaction_date=parsed_date,
                            amount=tx_amount,
                            transaction_type=tx_type,
                            description=description,
                            merchant_name=description[:50],
                            running_balance=balance
                        ))

            i = next_tx_date_idx_ptr

        # Type resolve based on running balance differences
        for idx in range(1, len(transactions)):
            prev = transactions[idx - 1]
            curr = transactions[idx]
            if curr.running_balance is not None and prev.running_balance is not None:
                bal_diff = curr.running_balance - prev.running_balance
                if bal_diff > 0.01:
                    curr.transaction_type = "income"
                elif bal_diff < -0.01:
                    curr.transaction_type = "expense"

        return transactions

    @classmethod
    def parse_transactions(cls, text: str, detected_bank: str) -> List[ParsedTransaction]:
        # ─── STRATEGY 1: Vertical Columnar Block Parser ───
        # Runs on multi-line vertical column formats (e.g. HDFC statements)
        vertical_txs = cls._parse_vertical_columnar_blocks(text)
        if len(vertical_txs) > 0:
            return vertical_txs

        # ─── STRATEGY 2: Configuration-Driven Generic Parser ───
        if detected_bank in BANK_CONFIGS:
            config = BANK_CONFIGS[detected_bank]
            config_txs = cls._parse_config_driven_table(text, config)
            if len(config_txs) > 0:
                return config_txs

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return []

        # ─── STRATEGY 3: Sequential Columnar Block Parser Fallback ───
        sequential_txs = []
        date_regex = re.compile(
            r"^(\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b)$",
            re.IGNORECASE
        )
        time_regex = re.compile(r"^\d{2}:\d{2}:\d{2}$")
        
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            date_match = date_regex.match(line)
            
            if date_match:
                txn_date_str = date_match.group(1)
                parsed_date = cls._parse_date(txn_date_str)
                if not parsed_date:
                    i += 1
                    continue
                    
                has_time = False
                if i + 1 < n and time_regex.match(lines[i+1]):
                    has_time = True
                    
                val_date_idx = i + 2 if has_time else i + 1
                if val_date_idx < n and date_regex.match(lines[val_date_idx]):
                    idx = val_date_idx + 1
                    tokens = []
                    while idx < n:
                        l = lines[idx]
                        if date_regex.match(l) and (idx + 1 >= n or time_regex.match(lines[idx+1]) or date_regex.match(lines[idx+1]) or idx + 2 >= n or date_regex.match(lines[idx+2])):
                            break
                        if l.lower() in ["account summary", "current balance", "note:", "this is a computer-generated", "account statement", "total info"]:
                            break
                        tokens.append(l)
                        idx += 1
                    
                    if len(tokens) >= 3:
                        balance_tok = tokens[-1]
                        credit_tok = tokens[-2]
                        debit_tok = tokens[-3]
                        
                        debit = cls._parse_amount(debit_tok) if debit_tok != "-" else 0.0
                        credit = cls._parse_amount(credit_tok) if credit_tok != "-" else 0.0
                        balance = cls._parse_amount(balance_tok)
                        
                        desc_tokens = tokens[:-3]
                        if len(desc_tokens) > 0 and (re.match(r"^\d{12,13}$", desc_tokens[-1]) or desc_tokens[-1] == "-"):
                            desc_tokens = desc_tokens[:-1]
                                
                        description = " ".join(desc_tokens).strip()
                        
                        if "B/F" not in description and description.lower() != "balance forward":
                            if credit and credit > 0:
                                amount = credit
                                tx_type = "income"
                            else:
                                amount = debit if debit else 0.0
                                tx_type = "expense"
                                
                            if amount > 0:
                                sequential_txs.append(ParsedTransaction(
                                    transaction_date=parsed_date,
                                    amount=amount,
                                    transaction_type=tx_type,
                                    description=description,
                                    merchant_name=description[:50],
                                    running_balance=balance
                                ))
                    i = idx
                    continue
            i += 1
            
        sequential_txs = []
        date_regex = re.compile(
            r"^(\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b)$",
            re.IGNORECASE
        )
        time_regex = re.compile(r"^\d{2}:\d{2}:\d{2}$")
        
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            date_match = date_regex.match(line)
            
            if date_match:
                txn_date_str = date_match.group(1)
                parsed_date = cls._parse_date(txn_date_str)
                if not parsed_date:
                    i += 1
                    continue
                    
                has_time = False
                if i + 1 < n and time_regex.match(lines[i+1]):
                    has_time = True
                    
                val_date_idx = i + 2 if has_time else i + 1
                if val_date_idx < n and date_regex.match(lines[val_date_idx]):
                    idx = val_date_idx + 1
                    tokens = []
                    while idx < n:
                        l = lines[idx]
                        if date_regex.match(l) and (idx + 1 >= n or time_regex.match(lines[idx+1]) or date_regex.match(lines[idx+1]) or idx + 2 >= n or date_regex.match(lines[idx+2])):
                            break
                        if l.lower() in ["account summary", "current balance", "note:", "this is a computer-generated", "account statement", "total info"]:
                            break
                        tokens.append(l)
                        idx += 1
                    
                    if len(tokens) >= 3:
                        balance_tok = tokens[-1]
                        credit_tok = tokens[-2]
                        debit_tok = tokens[-3]
                        
                        debit = cls._parse_amount(debit_tok) if debit_tok != "-" else 0.0
                        credit = cls._parse_amount(credit_tok) if credit_tok != "-" else 0.0
                        balance = cls._parse_amount(balance_tok)
                        
                        desc_tokens = tokens[:-3]
                        if len(desc_tokens) > 0 and (re.match(r"^\d{12,13}$", desc_tokens[-1]) or desc_tokens[-1] == "-"):
                            desc_tokens = desc_tokens[:-1]
                                
                        description = " ".join(desc_tokens).strip()
                        
                        if "B/F" not in description and description.lower() != "balance forward":
                            if credit and credit > 0:
                                amount = credit
                                tx_type = "income"
                            else:
                                amount = debit if debit else 0.0
                                tx_type = "expense"
                                
                            if amount > 0:
                                sequential_txs.append(ParsedTransaction(
                                    transaction_date=parsed_date,
                                    amount=amount,
                                    transaction_type=tx_type,
                                    description=description,
                                    merchant_name=description[:50],
                                    running_balance=balance
                                ))
                    i = idx
                    continue
            i += 1
            
        if len(sequential_txs) > 0:
            return sequential_txs

        # ─── STRATEGY 4: Flat Single-Line Fallback Regex Parser ───
        flat_txs = []
        date_pattern = re.compile(
            r"(\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b|"
            r"\b\d{4}[-/\s]+\d{1,2}[-/\s]+\d{1,2}\b|"
            r"\b[A-Za-z]{3,9}\s+\d{1,2}\s*,\s*\d{4}\b)"
        )
        amount_pattern = re.compile(r"[-+]?\s*[\d,]+\.\d{2}\b")
        credit_keywords = re.compile(r"\b(cr|credit|dep|deposit|received|refund|salary|interest|reversal)\b", re.IGNORECASE)
        debit_keywords = re.compile(r"\b(dr|debit|wdr|withdrawal|payment|charge|fee|spent)\b", re.IGNORECASE)

        for line in lines:
            if any(kw in line.lower() for kw in [
                "brought forward", "b/f", "opening balance", "closing balance", "page",
                "nomination", "customer id", "cust id", "account branch", "ifs code",
                "phone no", "email", "address", "gstin", "registered office"
            ]):
                continue

            date_match = date_pattern.search(line)
            if not date_match:
                continue
                
            date_str = date_match.group(1)
            parsed_date = cls._parse_date(date_str)
            if not parsed_date:
                continue
                
            rest = line.replace(date_str, " ").strip()
            amounts = amount_pattern.findall(rest)
            if not amounts:
                continue
                
            parsed_amounts = []
            for amt in amounts:
                cleaned = cls._parse_amount(amt)
                if cleaned is not None and cleaned > 0:
                    parsed_amounts.append((amt, cleaned))
                    
            if not parsed_amounts:
                continue
                
            tx_amt_str, tx_amount = parsed_amounts[0]
            
            desc = rest
            for amt_str, _ in parsed_amounts:
                desc = desc.replace(amt_str, " ")
                
            tx_type = "expense"
            lower_line = line.lower()
            if credit_keywords.search(lower_line):
                tx_type = "income"
            elif debit_keywords.search(lower_line):
                tx_type = "expense"
                
            desc = re.sub(r"\s+", " ", desc).strip()
            desc = re.sub(r"^(?:rs|usd|inr|[\$\u20B9\s,\.-])+", "", desc, flags=re.IGNORECASE).strip()
            desc = re.sub(r"(?:cr|dr)$", "", desc, flags=re.IGNORECASE).strip()
            
            if not desc:
                desc = "Transaction"
                
            flat_txs.append(ParsedTransaction(
                transaction_date=parsed_date,
                amount=tx_amount,
                transaction_type=tx_type,
                description=desc,
                merchant_name=desc[:50],
                running_balance=parsed_amounts[1][1] if len(parsed_amounts) > 1 else None
            ))
            
        return flat_txs
