# Optional follow-ups I can do, just say which:

Fix scalability_manager.py (pool_recycle + pool_size=50→≤32) so the startup error disappears and the multi-pool path is safe if ever re-enabled.

Route logging to stdout so Railway stops labeling INFO lines as errors.
