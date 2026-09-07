import re
from collections import Counter

log_file = 'converter.log'
date_pattern = '2026-05-09'

counts = Counter()
try:
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if date_pattern in line:
                if 'AUDIT' in line or 'Junk' in line:
                    # Try to extract the book name from the thread name or log label
                    # e.g. [ThreadPoolExecutor-305_1]
                    counts['total_audits'] += 1
                    if 'శ_ర_క_ష_ణ_చర_త_ర_6వ_భ_గమ' in line:
                        counts['part6_audits'] += 1
                    elif 'శ_ర_క_ష_ణ_చర_త_ర_7వ_భ_గమ' in line:
                        counts['part7_audits'] += 1
except Exception as e:
    print(f"Error: {e}")

print(f"Audit counts for {date_pattern}:")
for k, v in counts.items():
    print(f"  {k}: {v}")
