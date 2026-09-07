import re

log_file = 'converter.log'
date_pattern = '2026-05-09'

folders = set()
with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if date_pattern in line and '6వ_భ_గమ' in line:
            # Look for something like "శ_ర_క_ష_ణ_చర_త_ర_6వ_భ_గమ__[a-z0-0]+"
            match = re.search(r'శ_ర_క_ష_ణ_చర_త_ర_6వ_భ_గమ__[a-f0-9]+', line)
            if match:
                folders.add(match.group(0))

print(f"Folders found for Part 6 on May 9th: {folders}")
