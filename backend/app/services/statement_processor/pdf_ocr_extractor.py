import os
import sys
import glob
from typing import Optional

_poppler_initialized = False

def _setup_poppler_path():
    global _poppler_initialized
    if _poppler_initialized:
        return
    if sys.platform.startswith("win"):
        # We search default candidate paths first to avoid slow glob search unless necessary
        POPPLER_CANDIDATE_PATHS = [
            r"C:\Program Files\poppler\bin",
            r"C:\Program Files\poppler\Library\bin",
            r"C:\poppler\bin",
            r"C:\ProgramData\chocolatey\bin",
            r"C:\ProgramData\chocolatey\lib\poppler\tools\bin",
            r"C:\msys64\mingw64\bin",
        ]
        
        # Check if basic paths work first
        found = False
        for path in POPPLER_CANDIDATE_PATHS:
            if os.path.isdir(path):
                if path not in os.environ["PATH"]:
                    os.environ["PATH"] += os.pathsep + path
                found = True
                
        # Only fallback to slow recursive glob crawling if poppler not found in standard paths
        if not found:
            downloads_dir = os.path.expandvars(r"%USERPROFILE%\Downloads")
            candidates = (
                glob.glob(os.path.join(downloads_dir, "**/Library/bin"), recursive=True) +
                glob.glob(os.path.join(downloads_dir, "**/poppler*/bin"), recursive=True) +
                glob.glob(r"C:\Program Files\**/Library/bin", recursive=True) +
                glob.glob(r"C:\Program Files\**/poppler*/bin", recursive=True)
            )
            for path in candidates:
                if os.path.isdir(path) and path not in os.environ["PATH"]:
                    os.environ["PATH"] += os.pathsep + path

    _poppler_initialized = True

class PasswordProtectedException(Exception):
    def __init__(self, message: str, error_type: str):
        super().__init__(message)
        self.error_type = error_type # "password_required" or "wrong_password"

class TextExtractionException(Exception):
    pass

class PDFOCRExtractor:
    """
    Modular text extractor supporting PyMuPDF, pdfplumber, pypdf,
    and a fallback Tesseract OCR image flow.
    """

    @staticmethod
    def extract_text(file_path: str, password: Optional[str] = None) -> str:
        # Engine 1: PyMuPDF (Super robust and fast vector text extraction)
        try:
            import fitz
            with fitz.open(file_path) as doc:
                if doc.is_encrypted:
                    if password:
                        if not doc.authenticate(password):
                            raise PasswordProtectedException("Incorrect PDF password.", "wrong_password")
                    else:
                        # Attempt empty string authentication for restricted PDFs that don't need a password
                        if not doc.authenticate(""):
                            raise PasswordProtectedException("Password required to open PDF.", "password_required")
                
                text = ""
                for page in doc:
                    text += page.get_text() or ""
                if text.strip():
                    return text
        except PasswordProtectedException:
            raise
        except Exception as e:
            pass

        # Engine 2: pdfplumber fallback (Best for complex column layouts)
        try:
            import pdfplumber
            # If pdfplumber raises a password error, we catch it
            with pdfplumber.open(file_path, password=password or "") as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                if text.strip():
                    return text
        except Exception as e_plumber:
            from pdfminer.pdfdocument import PDFPasswordIncorrect, PDFEncryptionError
            err_msg = str(e_plumber).lower()
            is_password_err = isinstance(e_plumber, (PDFPasswordIncorrect, PDFEncryptionError)) or any(
                k in err_msg for k in ["password", "encrypted", "authenticate", "passphrase"]
            )
            if is_password_err:
                err_type = "wrong_password" if password else "password_required"
                raise PasswordProtectedException(f"PDF password error: {e_plumber}", err_type)

        # Engine 3: Tesseract OCR fallback (for scanned statement images/PDFs)
        try:
            _setup_poppler_path()
            import fitz
            from PIL import Image
            import pytesseract
            
            with fitz.open(file_path) as doc:
                if doc.is_encrypted:
                    if password:
                        if not doc.authenticate(password):
                            raise PasswordProtectedException("Incorrect PDF password.", "wrong_password")
                    else:
                        if not doc.authenticate(""):
                            raise PasswordProtectedException("PDF is password-protected.", "password_required")
                
                text = ""
                for page in doc:
                    pix = page.get_pixmap(dpi=150)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text += pytesseract.image_to_string(img) or ""
                if text.strip():
                    return text
        except PasswordProtectedException:
            raise
        except Exception as ocr_err:
            pass

        raise TextExtractionException(
            "FinAssist was unable to extract text from the PDF. Scanned/image statement PDFs require Tesseract OCR installed on the system."
        )
