"""
Usage Tracker for Premium OCR Engines
Handles persistent tracking of API calls to stay within monthly quotas.
"""
import json
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

class UsageTracker:
    """
    Tracks API usage for Google Cloud Vision and Gemini.
    Persists data to a JSON file to survive restarts.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(UsageTracker, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, storage_path=None):
        if self._initialized:
            return
            
        if storage_path is None:
            # Default to data/usage_stats.json
            import config
            self.storage_path = Path(config.DATA_DIR) / 'usage_stats.json'
        else:
            self.storage_path = Path(storage_path)
            
        self.usage_data = {
            'current_month': '',
            'engines': {
                'gemini': {'calls': 0, 'quota': 1500},  # Default values
                'google_vision': {'calls': 0, 'quota': 1000}
            },
            'history': []
        }
        
        self._load()
        self._check_month_reset()
        self._initialized = True
        logger.info(f"Usage tracker initialized. Storage: {self.storage_path}")

    def _load(self):
        """Load usage data from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    # Merge loaded data with defaults to handle schema changes
                    if 'engines' in data:
                        for engine, stats in data['engines'].items():
                            if engine in self.usage_data['engines']:
                                self.usage_data['engines'][engine].update(stats)
                            else:
                                self.usage_data['engines'][engine] = stats
                    
                    if 'current_month' in data:
                        self.usage_data['current_month'] = data['current_month']
                    
                    if 'history' in data:
                        self.usage_data['history'] = data['history']
                        
                logger.debug("Usage data loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load usage data: {e}")

    def _save(self):
        """Save usage data to disk."""
        with self._lock:
            try:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.storage_path, 'w') as f:
                    json.dump(self.usage_data, f, indent=2)
                logger.debug("Usage data saved successfully")
            except Exception as e:
                logger.error(f"Failed to save usage data: {e}")

    def _check_month_reset(self):
        """Reset counters if a new month has started."""
        now = datetime.now()
        current_month_str = now.strftime("%Y-%m")
        
        if self.usage_data['current_month'] != current_month_str:
            logger.info(f"New month detected ({current_month_str}). Resetting usage counters.")
            
            # Save old data to history before resetting
            if self.usage_data['current_month']:
                archive_entry = {
                    'month': self.usage_data['current_month'],
                    'usage': {k: v['calls'] for k, v in self.usage_data['engines'].items()}
                }
                self.usage_data['history'].append(archive_entry)
                # Keep only last 12 months in history
                self.usage_data['history'] = self.usage_data['history'][-12:]
            
            # Reset counters
            self.usage_data['current_month'] = current_month_str
            for engine in self.usage_data['engines']:
                self.usage_data['engines'][engine]['calls'] = 0
            
            self._save()

    def increment(self, engine: str, count: int = 1):
        """Increment call count for an engine."""
        self._check_month_reset()
        
        if engine in self.usage_data['engines']:
            with self._lock:
                self.usage_data['engines'][engine]['calls'] += count
            self._save()
            
            calls = self.usage_data['engines'][engine]['calls']
            quota = self.usage_data['engines'][engine].get('quota', 0)
            logger.info(f"Usage updated for {engine}: {calls}/{quota} calls this month")
        else:
            logger.warning(f"Attempted to increment usage for unknown engine: {engine}")

    def get_usage(self, engine: str) -> dict:
        """Get usage stats for an engine."""
        self._check_month_reset()
        return self.usage_data['engines'].get(engine, {'calls': 0, 'quota': 0})

    def has_quota(self, engine: str) -> bool:
        """Check if an engine has remaining monthly quota."""
        stats = self.get_usage(engine)
        return stats['calls'] < stats['quota']

    def update_quota(self, engine: str, quota: int):
        """Update the monthly quota limit for an engine."""
        if engine not in self.usage_data['engines']:
            self.usage_data['engines'][engine] = {'calls': 0}
        
        self.usage_data['engines'][engine]['quota'] = quota
        self._save()
        logger.info(f"Updated quota for {engine} to {quota}")

    def get_summary(self) -> str:
        """Return a human-readable summary of current usage."""
        self._check_month_reset()
        lines = [f"📊 Monthly Usage ({self.usage_data['current_month']}):"]
        for engine, stats in self.usage_data['engines'].items():
            percentage = (stats['calls'] / stats['quota'] * 100) if stats['quota'] > 0 else 0
            lines.append(f"  - {engine.capitalize()}: {stats['calls']}/{stats['quota']} ({percentage:.1f}%)")
        return "\n".join(lines)
