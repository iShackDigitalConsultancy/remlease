import os
import re

directories_to_scan = [
    '/Users/wdbmacminipro/Desktop/REM-Leases/lexichat-ui',
    '/Users/wdbmacminipro/Desktop/REM-Leases/lexichat-api',
    '/Users/wdbmacminipro/Desktop/REM-Leases/vercel.json'
]
exclude_dirs = {'venv', 'node_modules', '.git', 'dist', '.next', '__pycache__'}

replacements = [
    # SVGs specific styling
    (r'<tspan fill="([^"]+)">lekker</tspan><tspan fill="([^"]+)">pilot</tspan>', r'<tspan fill="\g<1>">REM</tspan><tspan fill="\g<2>">-Leases</tspan>'),
    (r'<tspan>lekkerpilot</tspan>', r'<tspan>REM-Leases</tspan>'),
    (r'<tspan>lekker</tspan>', r'<tspan>REM</tspan>'),
    (r'<tspan>pilot</tspan>', r'<tspan>-Leases</tspan>'),
    # Exact word replacements
    (r'Lekkerpilot\.ai', r'REM-Leases'),
    (r'Lekkerpilot', r'REM-Leases'),
    (r'lekkerpilot', r'rem-leases'),
    (r'\bLexi\b', r'REM Assistant'),
    # Edge case fixes
    (r'REM Assistant, your AI legal assistant', r'REM Assistant, your AI assistant'),
    (r'lekker_session_id', r'rem_session_id')
]

def update_branding():
    for item in directories_to_scan:
        if os.path.isfile(item):
            to_process = [item]
        else:
            to_process = []
            for root, dirs, files in os.walk(item):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                for file in files:
                    if not file.endswith(('.png', '.jpg', '.jpeg', '.gif', '.DS_Store', '.ico', '.pyc')):
                        to_process.append(os.path.join(root, file))

        for filepath in to_process:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = content
                for pattern, repl in replacements:
                    new_content = re.sub(pattern, repl, new_content)
                    
                if new_content != content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Updated content in: {filepath}")
                    
                # Rename file if needed
                dir_name = os.path.dirname(filepath)
                base_name = os.path.basename(filepath)
                if 'lekkerpilot' in base_name.lower():
                    # Handle varying casing if needed, but it's usually lekkerpilot-*.svg
                    new_base = re.sub(r'lekkerpilot', 'rem-leases', base_name, flags=re.IGNORECASE)
                    new_filepath = os.path.join(dir_name, new_base)
                    os.rename(filepath, new_filepath)
                    print(f"Renamed {filepath} to {new_filepath}")
                    
            except Exception as e:
                # ignore binary files or encoding errors
                pass

if __name__ == '__main__':
    update_branding()
    print("Branding update complete.")
