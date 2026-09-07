#!/usr/bin/env python3
"""Scan a folder for EPUB/MOBI/AZW ebooks and tabulate title & author.

Usage:
    python ebook_catalog.py <folder> [-o out.csv]
"""
import argparse
import csv
import datetime
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS_CONTAINER = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
NS_DC = {"dc": "http://purl.org/dc/elements/1.1/"}


def epub_metadata(path):
    with zipfile.ZipFile(path) as zf:
        container = zf.read("META-INF/container.xml")
        root = ET.fromstring(container)
        rootfile = root.find(".//c:rootfile", NS_CONTAINER).get("full-path")
        opf_root = ET.fromstring(zf.read(rootfile))
        title_el = opf_root.find(".//dc:title", NS_DC)
        creator_els = opf_root.findall(".//dc:creator", NS_DC)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        authors = "; ".join(c.text.strip() for c in creator_els if c.text)
        return title, authors


def mobi_metadata(path, read_bytes=400_000):
    with open(path, "rb") as f:
        data = f.read(read_bytes)

    db_name = data[0:32].split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()
    db_name = re.sub(r"[_]+", " ", db_name).strip()

    title = ""
    authors = []

    idx = data.find(b"EXTH")
    if idx != -1:
        try:
            record_count = int.from_bytes(data[idx + 8:idx + 12], "big")
            pos = idx + 12
            for _ in range(record_count):
                rec_type = int.from_bytes(data[pos:pos + 4], "big")
                rec_len = int.from_bytes(data[pos + 4:pos + 8], "big")
                if rec_len < 8:
                    break
                rec_data = data[pos + 8:pos + rec_len]
                pos += rec_len
                if rec_type == 100:
                    authors.append(rec_data.decode("utf-8", errors="replace").strip())
                elif rec_type == 503 and not title:
                    title = rec_data.decode("utf-8", errors="replace").strip()
        except Exception:
            pass

    if not title:
        title = db_name

    return title, "; ".join(authors)


def find_books(folder):
    results = []
    for dirpath, _dirs, files in os.walk(folder):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".epub", ".mobi", ".azw3", ".azw"):
                continue
            full = os.path.join(dirpath, name)
            try:
                if ext == ".epub":
                    title, author = epub_metadata(full)
                else:
                    title, author = mobi_metadata(full)
            except Exception as e:
                title, author = f"<error: {e}>", ""
            if not title:
                title = os.path.splitext(name)[0]
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full))
            results.append({
                "file": os.path.relpath(full, folder),
                "title": title,
                "author": author or "Unknown",
                "date": mtime.strftime("%Y-%m-%d %H:%M:%S"),
            })
    return results


def build_table_lines(rows):
    if not rows:
        return ["No epub/mobi files found."]
    title_w = min(max(len("Title"), max(len(r["title"]) for r in rows)), 60)
    author_w = min(max(len("Author"), max(len(r["author"]) for r in rows)), 40)
    date_w = max(len("Date Modified"), max(len(r["date"]) for r in rows))

    def fit(s, w):
        return (s[: w - 1] + "…") if len(s) > w else s.ljust(w)

    lines = [
        f"{fit('Title', title_w)}  {fit('Author', author_w)}  {fit('Date Modified', date_w)}",
        "-" * (title_w + author_w + date_w + 4),
    ]
    for r in sorted(rows, key=lambda r: r["title"].lower()):
        lines.append(f"{fit(r['title'], title_w)}  {fit(r['author'], author_w)}  {fit(r['date'], date_w)}")
    lines.append(f"\n{len(rows)} book(s) found.")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Tabulate EPUB/MOBI title & author from a folder.")
    parser.add_argument("folder", help="Folder to scan (recursively)")
    parser.add_argument("-o", "--output", help="Optional CSV output path")
    parser.add_argument("-l", "--log", help="Optional path to write the printed table as UTF-8 text "
                                             "(use this instead of shell '>' redirection, which can "
                                             "mangle non-Latin text like Telugu on Windows)")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"Not a folder: {args.folder}", file=sys.stderr)
        sys.exit(1)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    rows = find_books(args.folder)
    lines = build_table_lines(rows)
    for line in lines:
        print(line)

    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Saved log: {args.log}")

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "author", "date", "file"])
            writer.writeheader()
            for r in sorted(rows, key=lambda r: r["title"].lower()):
                writer.writerow(r)
        print(f"Saved CSV: {args.output}")


if __name__ == "__main__":
    main()
