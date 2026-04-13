"""Remove invalid parameters: default_administration, download_folder, vendor_folder_mappings."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from database import DatabaseManager

logger = logging.getLogger(__name__)

SQL = (
    "DELETE FROM parameters "
    "WHERE (namespace = 'general' AND `key` = 'default_administration') "
    "OR (namespace = 'storage' AND `key` IN ('download_folder', 'vendor_folder_mappings'))"
)

def run_cleanup(db=None):
    if db is None:
        db = DatabaseManager()
    result = db.execute_query(SQL, fetch=False, commit=True)
    logger.info("Deleted %s rows", result)
    return result

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    run_cleanup()
