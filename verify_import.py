import sys
import os
sys.path.append(os.getcwd())

try:
    from app.config.logging import logger
    from app.utils.audit import log_audit_event
    from app.services.admin_service import list_users
    print("Import successful")
except Exception as e:
    print(f"Import failed: {e}")
