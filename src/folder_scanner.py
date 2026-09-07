"""
Folder Scanner - Recursively scan folders and generate detailed structure report
Includes Telugu to English translation for filenames
"""
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import json
from filename_utils import contains_telugu, transliterate_telugu_to_english


class FolderScanner:
    """Scan folders recursively and generate detailed reports"""
    
    def __init__(self, root_path: str):
        """
        Initialize folder scanner
        
        Args:
            root_path: Root directory to scan
        """
        self.root_path = Path(root_path)
        if not self.root_path.exists():
            raise ValueError(f"Path does not exist: {root_path}")
        if not self.root_path.is_dir():
            raise ValueError(f"Path is not a directory: {root_path}")
        
        self.scan_results = []
        self.stats = {
            'total_files': 0,
            'total_dirs': 0,
            'total_size': 0,
            'telugu_files': 0,
            'file_types': {},
        }
    
    def format_size(self, size_bytes: int) -> str:
        """
        Format file size in human-readable format
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string (e.g., "1.5 MB")
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def get_file_info(self, file_path: Path) -> Dict:
        """
        Get detailed information about a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with file information
        """
        try:
            stat = file_path.stat()
            filename = file_path.name
            
            # Check if filename contains Telugu
            has_telugu = contains_telugu(filename)
            if has_telugu:
                self.stats['telugu_files'] += 1
                translated_name = transliterate_telugu_to_english(filename)
            else:
                translated_name = filename
            
            # Get file extension
            extension = file_path.suffix.lower()
            if extension:
                self.stats['file_types'][extension] = self.stats['file_types'].get(extension, 0) + 1
            
            # Get relative path from root
            try:
                relative_path = file_path.relative_to(self.root_path)
            except ValueError:
                relative_path = file_path
            
            return {
                'type': 'file',
                'name': filename,
                'translated_name': translated_name,
                'has_telugu': has_telugu,
                'path': str(file_path),
                'relative_path': str(relative_path),
                'size': stat.st_size,
                'size_formatted': self.format_size(stat.st_size),
                'extension': extension,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
            }
        except Exception as e:
            return {
                'type': 'file',
                'name': file_path.name,
                'error': str(e)
            }
    
    def get_dir_info(self, dir_path: Path) -> Dict:
        """
        Get detailed information about a directory
        
        Args:
            dir_path: Path to the directory
            
        Returns:
            Dictionary with directory information
        """
        try:
            dirname = dir_path.name
            
            # Check if directory name contains Telugu
            has_telugu = contains_telugu(dirname)
            if has_telugu:
                translated_name = transliterate_telugu_to_english(dirname)
            else:
                translated_name = dirname
            
            # Get relative path from root
            try:
                relative_path = dir_path.relative_to(self.root_path)
            except ValueError:
                relative_path = dir_path
            
            # Count items in directory
            try:
                items = list(dir_path.iterdir())
                file_count = sum(1 for item in items if item.is_file())
                dir_count = sum(1 for item in items if item.is_dir())
            except PermissionError:
                file_count = 0
                dir_count = 0
            
            return {
                'type': 'directory',
                'name': dirname,
                'translated_name': translated_name,
                'has_telugu': has_telugu,
                'path': str(dir_path),
                'relative_path': str(relative_path),
                'file_count': file_count,
                'dir_count': dir_count,
            }
        except Exception as e:
            return {
                'type': 'directory',
                'name': dir_path.name,
                'error': str(e)
            }
    
    def scan(self) -> List[Dict]:
        """
        Recursively scan the root directory
        
        Returns:
            List of dictionaries with file/directory information
        """
        self.scan_results = []
        self.stats = {
            'total_files': 0,
            'total_dirs': 0,
            'total_size': 0,
            'telugu_files': 0,
            'file_types': {},
        }
        
        print(f"Scanning: {self.root_path}")
        print("This may take a while for large directories...")
        
        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)
            
            # Process directories
            for dirname in sorted(dirs):
                dir_path = root_path / dirname
                dir_info = self.get_dir_info(dir_path)
                self.scan_results.append(dir_info)
                self.stats['total_dirs'] += 1
            
            # Process files
            for filename in sorted(files):
                file_path = root_path / filename
                file_info = self.get_file_info(file_path)
                self.scan_results.append(file_info)
                self.stats['total_files'] += 1
                if 'size' in file_info:
                    self.stats['total_size'] += file_info['size']
        
        print(f"✓ Scan complete: {self.stats['total_files']} files, {self.stats['total_dirs']} directories")
        return self.scan_results
    
    def build_tree_structure(self) -> Dict:
        """
        Build a hierarchical tree structure from scan results
        
        Returns:
            Dictionary representing the tree structure
        """
        tree = {}
        
        for item in self.scan_results:
            if 'error' in item:
                continue
            
            path_parts = Path(item['relative_path']).parts
            current = tree
            
            # Navigate/create the tree structure
            for i, part in enumerate(path_parts[:-1]):
                if part not in current:
                    current[part] = {'_dirs': {}, '_files': []}
                current = current[part]['_dirs']
            
            # Add the item
            if item['type'] == 'directory':
                name = path_parts[-1] if path_parts else item['name']
                if name not in current:
                    current[name] = {'_dirs': {}, '_files': [], '_info': item}
            elif item['type'] == 'file':
                parent = current
                if path_parts:
                    parent_name = path_parts[-2] if len(path_parts) > 1 else None
                    if parent_name and parent_name in tree:
                        parent = tree[parent_name].get('_files', [])
                parent.setdefault('_files', []).append(item)
        
        return tree
    
    def generate_text_report(self, output_file: str = None) -> str:
        """
        Generate a tree-structured text report
        
        Args:
            output_file: Optional path to save the report
            
        Returns:
            Report content as string
        """
        if not self.scan_results:
            self.scan()
        
        lines = []
        lines.append(f"Tree structure of '{self.root_path}':")
        lines.append("")
        
        # Build tree structure by organizing items hierarchically
        def print_tree(path: Path, prefix: str = "", is_last: bool = True):
            """Recursively print tree structure"""
            try:
                items = list(path.iterdir())
                # Sort: directories first, then files
                dirs = sorted([item for item in items if item.is_dir()])
                files = sorted([item for item in items if item.is_file()])
                all_items = dirs + files
                
                for i, item in enumerate(all_items):
                    is_last_item = (i == len(all_items) - 1)
                    connector = "└── " if is_last_item else "├── "
                    
                    # Get item info
                    item_name = item.name
                    has_telugu = contains_telugu(item_name)
                    
                    if item.is_dir():
                        # Directory
                        if has_telugu:
                            translated = transliterate_telugu_to_english(item_name)
                            lines.append(f"{prefix}{connector}{item} [{translated}]")
                        else:
                            lines.append(f"{prefix}{connector}{item}")
                        
                        # Recurse into directory
                        extension = "    " if is_last_item else "│   "
                        print_tree(item, prefix + extension, is_last_item)
                    else:
                        # File
                        try:
                            stat = item.stat()
                            size = stat.st_size
                            mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                            
                            if has_telugu:
                                translated = transliterate_telugu_to_english(item_name)
                                lines.append(f"{prefix}{connector}{item_name} [{translated}] (size: {size} bytes, modified: {mtime})")
                            else:
                                lines.append(f"{prefix}{connector}{item_name} (size: {size} bytes, modified: {mtime})")
                        except Exception as e:
                            lines.append(f"{prefix}{connector}{item_name} (error: {e})")
            
            except PermissionError:
                lines.append(f"{prefix}[Permission Denied]")
            except Exception as e:
                lines.append(f"{prefix}[Error: {e}]")
        
        # Start tree traversal from root
        print_tree(self.root_path)
        
        # Add summary statistics at the end
        lines.append("")
        lines.append("=" * 80)
        lines.append("SUMMARY")
        lines.append("=" * 80)
        lines.append(f"Total Files:       {self.stats['total_files']}")
        lines.append(f"Total Directories: {self.stats['total_dirs']}")
        lines.append(f"Total Size:        {self.format_size(self.stats['total_size'])}")
        lines.append(f"Telugu Files:      {self.stats['telugu_files']}")
        
        if self.stats['file_types']:
            lines.append("")
            lines.append("File Types:")
            for ext, count in sorted(self.stats['file_types'].items(), key=lambda x: x[1], reverse=True):
                ext_display = ext if ext else "(no extension)"
                lines.append(f"  {ext_display:20} {count:5} files")
        
        report = "\n".join(lines)
        
        # Save to file if specified
        if output_file:
            output_path = Path(output_file)
            output_path.write_text(report, encoding='utf-8')
            print(f"✓ Report saved to: {output_file}")
        
        return report
    
    def generate_json_report(self, output_file: str) -> str:
        """
        Generate a JSON report
        
        Args:
            output_file: Path to save the JSON report
            
        Returns:
            JSON content as string
        """
        if not self.scan_results:
            self.scan()
        
        report_data = {
            'root_directory': str(self.root_path),
            'scan_date': datetime.now().isoformat(),
            'statistics': self.stats,
            'items': self.scan_results
        }
        
        json_content = json.dumps(report_data, indent=2, ensure_ascii=False)
        
        output_path = Path(output_file)
        output_path.write_text(json_content, encoding='utf-8')
        print(f"✓ JSON report saved to: {output_file}")
        
        return json_content


def main():
    """Command-line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Recursively scan folders and generate detailed structure report with Telugu translation'
    )
    parser.add_argument('folder', help='Folder path to scan')
    parser.add_argument('-o', '--output', help='Output text file path (default: folder_structure.txt)',
                        default='folder_structure.txt')
    parser.add_argument('-j', '--json', help='Also generate JSON report')
    parser.add_argument('-p', '--print', action='store_true', help='Print report to console')
    
    args = parser.parse_args()
    
    try:
        # Create scanner
        scanner = FolderScanner(args.folder)
        
        # Scan the folder
        scanner.scan()
        
        # Generate text report
        report = scanner.generate_text_report(args.output)
        
        # Print to console if requested
        if args.print:
            print("\n" + report)
        
        # Generate JSON report if requested
        if args.json:
            scanner.generate_json_report(args.json)
        
        print("\n✓ Scan completed successfully!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
