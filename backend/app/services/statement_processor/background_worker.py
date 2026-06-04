import os
import traceback
from datetime import datetime
from typing import Optional
from app.utils.supabase_client import supabase
from .pipeline import StatementPipeline

class BackgroundWorker:
    """
    Asynchronously executes the processing pipeline in a safe thread,
    logging real-time progress percentages to the processing_jobs table.
    """

    @staticmethod
    def update_job_status(
        job_id: str,
        status: str,
        progress: int,
        error_message: Optional[str] = None
    ):
        """
        Helper method to update processing_jobs status in database.
        """
        try:
            supabase.table("processing_jobs").update({
                "status": status,
                "progress": progress,
                "error_message": error_message,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", job_id).execute()
        except Exception as e:
            print(f"Failed to update job status in DB: {e}")

    @classmethod
    def process_statement_task(
        cls,
        job_id: str,
        statement_id: str,
        file_path: str,
        user_id: str,
        password: Optional[str] = None
    ):
        """
        Standard worker entry point. Spawns pipeline and updates status tracker.
        This function runs in a background thread.
        """
        print(f"[Worker] Starting statement ingestion: job_id={job_id}, statement_id={statement_id}")
        
        # Define progress logger callback
        def progress_callback(pct: int):
            cls.update_job_status(job_id, "PROCESSING", pct)

        try:
            # 1. Update job to processing
            cls.update_job_status(job_id, "PROCESSING", 0)
            
            # 2. Run Pipeline
            res = StatementPipeline.run_pipeline(
                statement_id=statement_id,
                file_path=file_path,
                user_id=user_id,
                password=password,
                progress_callback=progress_callback
            )
            
            # 3. Update uploaded_statements to COMPLETED
            supabase.table("uploaded_statements").update({"status": "COMPLETED"}).eq("id", statement_id).execute()
            
            # 4. Update job status to COMPLETED
            cls.update_job_status(job_id, "COMPLETED", 100)
            print(f"[Worker] Ingestion succeeded: {res}")
            
        except Exception as e:
            err_msg = str(e)
            trace = traceback.format_exc()
            print(f"[Worker] Ingestion failed: {err_msg}\n{trace}")
            
            # Update uploaded_statements and jobs to FAILED
            try:
                supabase.table("uploaded_statements").update({"status": "FAILED"}).eq("id", statement_id).execute()
            except Exception:
                pass
            cls.update_job_status(job_id, "FAILED", 100, error_message=err_msg)
            
        finally:
            # Clean up temporary file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"[Worker] Cleaned up temporary statement file: {file_path}")
                except Exception as cleanup_err:
                    print(f"[Worker] Temporary file cleanup failed: {cleanup_err}")
