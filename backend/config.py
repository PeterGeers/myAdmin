import os

class Config:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.base_folder = os.path.join(os.getcwd(), 'storage')
        
        # Vendor folder mapping
        self.vendor_folders = {
            'avance': 'Avance',
            'booking': 'Booking.com',
            'booking.com': 'Booking.com',
            'amazon': 'Amazon',
            'microsoft': 'Microsoft',
            'coursera': 'Coursera',
            'general': 'General'
        }
    
    def get_storage_folder(self, vendor_name):
        """Get storage folder path for vendor"""
        folder_name = self.vendor_folders.get(vendor_name.lower(), vendor_name)
        return os.path.join(self.base_folder, folder_name)
    
    def ensure_folder_exists(self, folder_path):
        """Create folder if it doesn't exist"""
        os.makedirs(folder_path, exist_ok=True)