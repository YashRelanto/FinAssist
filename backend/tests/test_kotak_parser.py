import unittest
from app.services.statement_processor.bank_detector import BankDetector
from app.services.statement_processor.account_extractor import AccountExtractor
from app.services.statement_processor.transaction_extractor import TransactionExtractor

class TestKotakParser(unittest.TestCase):

    def setUp(self):
        self.kotak_statement_text = """
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

    def test_detect_kotak_bank(self):
        detected = BankDetector.detect_bank(self.kotak_statement_text)
        self.assertEqual(detected, "KOTAK")

    def test_extract_kotak_account_details(self):
        details = AccountExtractor.extract_account_details(self.kotak_statement_text, "KOTAK")
        self.assertEqual(details.bank_name, "Kotak Mahindra Bank")
        self.assertEqual(details.account_holder, "Gurprit Kaur")
        self.assertEqual(details.account_number, "9449630577")
        self.assertEqual(details.ifsc, "KKBK0004345")

    def test_parse_kotak_transactions(self):
        transactions = TransactionExtractor.parse_transactions(self.kotak_statement_text, "KOTAK")
        self.assertEqual(len(transactions), 5)

        # Check transaction 1 (debit)
        self.assertEqual(transactions[0].transaction_date, "2024-06-01")
        self.assertEqual(transactions[0].amount, 100.00)
        self.assertEqual(transactions[0].transaction_type, "expense")
        self.assertIn("UPI/iMobile Bill UPI- Pa/127419263674/00000001117V 127425639780", transactions[0].description)
        self.assertEqual(transactions[0].running_balance, 1200123.38)

        # Check transaction 3 (credit)
        self.assertEqual(transactions[2].transaction_date, "2024-06-01")
        self.assertEqual(transactions[2].amount, 200.00)
        self.assertEqual(transactions[2].transaction_type, "income")
        self.assertIn("Payment UPI/DEEPAK KUMAR UPI- GU/127419271223/UPI Payment 127425644816", transactions[2].description)
        self.assertEqual(transactions[2].running_balance, 1200223.38)

        # Check transaction 5 (NEFT credit)
        self.assertEqual(transactions[4].transaction_date, "2024-06-05")
        self.assertEqual(transactions[4].amount, 40.00)
        self.assertEqual(transactions[4].transaction_type, "income")
        self.assertIn("NEFT CMS2166555203 SME AND AGRI NEFTINW- GROUP ICIC0000104 0326932477", transactions[4].description)
        self.assertEqual(transactions[4].running_balance, 1200264.38)

if __name__ == "__main__":
    unittest.main()
