import unittest

from app.services.statement_processor.account_extractor import AccountExtractor
from app.services.statement_processor.bank_detector import BankDetector
from app.services.statement_processor.transaction_extractor import TransactionExtractor


class TestNumberedStatementParser(unittest.TestCase):
    def test_icici_numbered_vertical_statement(self):
        text = """
1
S No.
Transaction
Date
Cheque Number
Transaction Remarks
Withdrawal
Amount (INR)
Deposit
Amount (INR)
Balance
(INR)
1
05.03.2026
Gaurav Bha
UPI/Gaurav Bha/bhattgaurav250/UPI/State
Bank/606439534838/AXI91e202e71b9b41cebbfa5c
1915954877
1.00
1.00
2
06.03.2026
Indian Cle
MMT/IMPS/606511202238/Bank Account Ve/Indian
Cle/Kotak Mahindra
1.00
2.00
SUYASH SINGH BHADOURIA
E-1604 ARIHANT AMBIENCE,CROSSING,REPUBLIK
GHAZIABAD
UTTAR PRADESH - INDIA -  201016
Statement of Transactions in Saving Account no. 812701500464 in INR for the period April 1, 2025 - March 31, 2026
Your Base Branch:  ICICI BANK LIMITED,
www.icici.bank.in
"""
        self.assertEqual(BankDetector.detect_bank(text), "ICICI")

        details = AccountExtractor.extract_account_details(text, "ICICI")
        self.assertEqual(details.account_holder, "Suyash Singh Bhadouria")
        self.assertEqual(details.account_number, "812701500464")

        transactions = TransactionExtractor.parse_transactions(text, "ICICI")
        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].transaction_type, "expense")
        self.assertEqual(transactions[1].transaction_type, "income")
        self.assertIn("Kotak Mahindra", transactions[1].description)


if __name__ == "__main__":
    unittest.main()
