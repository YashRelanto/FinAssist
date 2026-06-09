import re
import sys
sys.path.append("backend")

from app.services.statement_processor.bank_configs import BANK_CONFIGS
from app.services.statement_processor.bank_detector import BankDetector
from app.services.statement_processor.account_extractor import AccountExtractor
from app.services.statement_processor.transaction_extractor import TransactionExtractor

text = """
KOTAK MAHINDRA BANK
Kotak Mahindra Bank

GURPRIT KAUR                            Period          : 01-06-2024 to 20-08-2024
                                        Cust.Reln.No    : 894666839
W/O BALIHAR SINGH                       Account No      : 9449630577
VPO MACHHRAULI (94)                     Currency        : INR
DISTRICT KURUKSHETRA,                   Branch          : SHAHBAD
HARYANA-136118, INDIA                   IFSC Code       : KKBK0004345
                                        Date            : 20-08-2024

Date            Narration                   Chq/Ref No      Withdrawal (Dr)/    Balance
                                                            Deposit (Cr)
---------------------------------------------------------------------------------------
                B/F                                                 0.00(Cr)    12,00,223.38(Cr)
01-06-2024 UPI/iMobile Bill                 UPI-            100.00(Dr)          12,00,123.38(Cr)
           Pa/127419263674/00000001117V     127425639780
01-06-2024 UPI/DEEPAK KUMAR                 UPI-            100.00(Dr)          12,00,023.38(Cr)
           GU/127419270227/UPI              127425643095
01-06-2024 Payment UPI/DEEPAK KUMAR         UPI-            200.00(Cr)          12,00,223.38(Cr)
           GU/127419271223/UPI Payment      127425644816
01-06-2024 UPI/ARTI                         UPI-            1.00(Cr)            12,00,224.38(Cr)
           GUPTA/127407842426/UPI
                                            127425733316
05-06-2024 NEFT CMS2166555203 SME AND AGRI  NEFTINW-        40.00(Cr)           12,00,264.38(Cr)
           GROUP ICIC0000104                0326932477
This is a computer generated statement.
"""

print("Detected Bank:", BankDetector.detect_bank(text))

# Test holder patterns
config = BANK_CONFIGS["KOTAK"]
print("\n--- Testing Account Holder Extraction ---")
details = AccountExtractor.extract_account_details(text, "KOTAK")
print("Extracted Holder:", details.account_holder)
print("Extracted Account No:", details.account_number)
print("Extracted IFSC:", details.ifsc)



print("\n--- Running parse_transactions ---")
txs = TransactionExtractor.parse_transactions(text, "KOTAK")
print("Total parsed transactions:", len(txs))
for idx, tx in enumerate(txs):
    print(f"Tx {idx}: Date={tx.transaction_date}, Amount={tx.amount}, Type={tx.transaction_type}, RunningBalance={tx.running_balance}")
    print(f"      Desc={tx.description}")
