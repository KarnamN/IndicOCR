"""
Check current OCR tool usage and remaining quotas.
"""
from usage_tracker import UsageTracker
import sys

def main():
    tracker = UsageTracker()
    print("\n" + "="*40)
    print("      OCR API USAGE DASHBOARD")
    print("="*40)
    print(tracker.get_summary())
    print("="*40)
    
    # Check if we need to set keys
    import config
    print("\nConfiguration Status:")
    print(f" Gemini: {'✓ CONFIGURED' if config.GEMINI_AVAILABLE else '✗ MISSING KEY (Set GEMINI_API_KEY in .env)'}")
    print(f" GVision: {'✓ CONFIGURED' if config.GOOGLE_VISION_AVAILABLE else '✗ MISSING SERVICE ACCOUNT (Set GOOGLE_VISION_SERVICE_ACCOUNT in .env)'}")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
