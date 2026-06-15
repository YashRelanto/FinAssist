import unittest

from app.services.statement_processor.bank_detector import BankDetector


class TestBankDetector(unittest.TestCase):
    def test_hdfc_header_wins_over_kotak_narration(self):
        text = """
HDFC BANK
We understand your world
Account Branch : J P NAGAR V PHASE
RTGS/NEFT IFSC : HDFC000284
Statement of account
Date Narration Chq./Ref.No. Value Dt Withdrawal Amt. Deposit Amt. Closing Balance
04/04/26 UPI/KOTAK MAHINDRA BANK/UPI/KKBK0000001 0000001 20.00 25,080.00
"""
        self.assertEqual(BankDetector.detect_bank(text), "HDFC")

    def test_iob_ifsc_detects_indian_overseas_bank(self):
        text = """
STATEMENT OF THE ACCOUNT FOR THE PERIOD OF : 2025-06-01 to 2026-05-31
CUSTOMER DETAILS
Account No : 255101000011431
IFS Code : IOBA0002551
Date(Value Date) Particulars Ref No. Transaction Type Debit(Rs) Credit(Rs) Balance(Rs)
"""
        self.assertEqual(BankDetector.detect_bank(text), "IOB")


if __name__ == "__main__":
    unittest.main()
