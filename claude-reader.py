#!/usr/bin/env python3
"""
Claude JSONL Chat Reader
Pure Python script to read and convert Claude project JSONL chat files to readable format
"""

import json
import sys
import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import subprocess

# Colors for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    PURPLE = '\033[0;35m'
    NC = '\033[0m'  # No Color

def print_colored(message, color):
    """Print colored message to terminal"""
    print(f"{color}{message}{Colors.NC}")

def format_timestamp(ts):
    """Format timestamp to readable format"""
    try:
        if ts is None:
            return 'No timestamp'
        if isinstance(ts, str):
            # Parse ISO format (like 2025-09-20T12:28:46.794Z)
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                return ts
        if isinstance(ts, (int, float)):
            # Handle both seconds and milliseconds timestamps
            if ts > 1000000000000:  # Milliseconds
                return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            else:  # Seconds
                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        return str(ts)
    except:
        return 'Invalid timestamp'

def format_content(content, role):
    """Format message content"""
    if content is None:
        return f'[Empty {role} message]'
    
    if not content:
        return f'[No content in {role} message]'
    
    # Handle string content
    if isinstance(content, str):
        return content.strip() if content.strip() else f'[Empty {role} message]'
    
    # Handle list content (Claude's structured format)
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text = item.get('text', '').strip()
                    if text:
                        text_parts.append(text)
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'unknown')
                    tool_input = item.get('input', {})
                    text_parts.append(f'🔧 [Tool Use: {tool_name}]')
                    if tool_input:
                        # Show first few parameters
                        if 'file_path' in tool_input:
                            text_parts.append(f'   File: {tool_input["file_path"]}')
                        elif 'todos' in tool_input:
                            todos = tool_input.get('todos', [])
                            if todos:
                                text_parts.append(f'   Todos: {len(todos)} items')
                                for todo in todos[:2]:  # Show first 2 todos
                                    todo_content = todo.get('content', 'Unknown todo')
                                    status = todo.get('status', 'unknown')
                                    text_parts.append(f'     • {todo_content} ({status})')
                        elif 'old_string' in tool_input and 'new_string' in tool_input:
                            old_preview = tool_input['old_string'][:50] + '...' if len(tool_input['old_string']) > 50 else tool_input['old_string']
                            text_parts.append(f'   Replacing: {old_preview}')
                        elif 'edits' in tool_input:
                            edits = tool_input.get('edits', [])
                            text_parts.append(f'   Edits: {len(edits)} changes')
                        else:
                            params = []
                            for k, v in list(tool_input.items())[:3]:
                                if isinstance(v, str) and len(v) > 50:
                                    params.append(f'{k}={v[:50]}...')
                                elif isinstance(v, (list, dict)):
                                    params.append(f'{k}=<{type(v).__name__}>')
                                else:
                                    params.append(f'{k}={v}')
                            if params:
                                text_parts.append(f'   Parameters: {", ".join(params)}')
                elif item.get('type') == 'tool_result':
                    result = item.get('content', '')
                    if isinstance(result, str):
                        preview = result[:200] + '...' if len(result) > 200 else result
                        text_parts.append(f'⚙️ [Tool Result: {preview}]')
                    else:
                        text_parts.append('⚙️ [Tool Result]')
                elif item.get('type') == 'image':
                    text_parts.append('🖼️ [Image attachment]')
            elif isinstance(item, str):
                if item.strip():
                    text_parts.append(item.strip())
            else:
                text_parts.append(str(item))
        
        result = '\n'.join(text_parts) if text_parts else f'[Empty {role} message]'
        return result
    
    # Handle dict content
    if isinstance(content, dict):
        if 'text' in content:
            return content['text'].strip() if content['text'] else f'[Empty {role} message]'
        elif 'content' in content:
            return format_content(content['content'], role)
        else:
            return f'[Complex {role} data: {str(content)[:100]}...]'
    
    return str(content) if content else f'[Empty {role} message]'

def format_tool_result(tool_result, role):
    """Format tool result information"""
    if not tool_result:
        return ''
    
    if isinstance(tool_result, str):
        return f'\n⚙️ [Tool Output]: {tool_result[:200]}...' if len(tool_result) > 200 else f'\n⚙️ [Tool Output]: {tool_result}'
    
    if isinstance(tool_result, dict):
        result_type = tool_result.get('type', 'unknown')
        
        if result_type == 'text' and 'file' in tool_result:
            file_info = tool_result['file']
            file_path = file_info.get('filePath', 'unknown')
            lines = file_info.get('numLines', 0)
            return f'\n📄 [File Read]: {file_path} ({lines} lines)'
        
        elif 'newTodos' in tool_result:
            new_todos = tool_result.get('newTodos', [])
            old_todos = tool_result.get('oldTodos', [])
            return f'\n✅ [Todo Update]: {len(old_todos)} → {len(new_todos)} todos'
        
        elif 'filePath' in tool_result and 'newString' in tool_result:
            file_path = tool_result.get('filePath', 'unknown')
            return f'\n✏️ [File Edit]: {file_path}'
        
        else:
            return f'\n⚙️ [Tool Result]: {result_type}'
    
    return f'\n⚙️ [Tool Result]: {str(tool_result)[:100]}...'

def get_terminal_size():
    """Get terminal size (width, height)"""
    try:
        return shutil.get_terminal_size()
    except:
        return shutil.get_terminal_size((80, 24))  # fallback

def display_with_pager(content, title=""):
    """Display content with less-like paging behavior"""
    lines = content.split('\n')
    terminal_size = get_terminal_size()
    page_height = terminal_size.lines - 2  # Reserve 2 lines for status and input
    
    if len(lines) <= page_height:
        # Content fits on screen, display directly
        if title:
            print_colored(title, Colors.BLUE)
            print("=" * 60)
            print()
        print(content)
        return
    
    current_line = 0
    
    if title:
        print_colored(title, Colors.BLUE)
        print("=" * 60)
        print()
    
    while current_line < len(lines):
        # Calculate how many lines to show
        end_line = min(current_line + page_height, len(lines))
        
        # Display the current page
        for i in range(current_line, end_line):
            print(lines[i])
        
        # Show status line
        if end_line >= len(lines):
            status = f"{Colors.BLUE}(END) - Press 'q' to quit, 'b' for back{Colors.NC}"
        else:
            percent = int((end_line / len(lines)) * 100)
            remaining = len(lines) - end_line
            status = f"{Colors.BLUE}-- More -- ({percent}%, {remaining} lines remaining) [Space/Enter: next, 'b': back, 'q': quit]{Colors.NC}"
        
        print(status, end='', flush=True)
        
        # Get user input
        try:
            # Read single character without Enter
            import termios, tty
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            
            # Clear the status line
            print('\r' + ' ' * len(status.replace(Colors.BLUE, '').replace(Colors.NC, '')) + '\r', end='')
            
            if ch.lower() == 'q':
                break
            elif ch.lower() == 'b':
                # Go back one page
                current_line = max(0, current_line - page_height)
            elif ch == ' ':
                # Space bar - next page
                current_line = end_line
            elif ch == '\r' or ch == '\n':
                # Enter - next line
                current_line = min(current_line + 1, len(lines) - page_height)
            elif ch == 'j':
                # j - next line (vim-like)
                current_line = min(current_line + 1, len(lines) - page_height)
            elif ch == 'k':
                # k - previous line (vim-like)
                current_line = max(0, current_line - 1)
            elif ch == 'd':
                # d - half page down
                current_line = min(current_line + page_height // 2, len(lines) - page_height)
            elif ch == 'u':
                # u - half page up
                current_line = max(0, current_line - page_height // 2)
            elif ch == 'g':
                # g - go to top
                current_line = 0
            elif ch.upper() == 'G':
                # G - go to bottom
                current_line = max(0, len(lines) - page_height)
            else:
                # Any other key - next page
                current_line = end_line
                
        except (ImportError, OSError):
            # Fallback for systems without termios (Windows)
            input()  # Just wait for Enter
            current_line = end_line

def clean_project_name(name):
    """Clean project name by removing leading dash and making it readable"""
    # Remove leading dash if present
    if name.startswith('-'):
        name = name[1:]
    
    # Replace dashes with spaces for better readability (optional)
    # You can comment this out if you prefer to keep the original format
    readable_name = name.replace('-', ' ').title()
    
    return readable_name

def get_claude_projects_dir():
    """Get Claude projects directory path"""
    home = Path.home()
    claude_dir = home / '.claude' / 'projects'
    return claude_dir

def get_project_info(project_dir):
    """Get information about a project"""
    project_name = clean_project_name(project_dir.name)
    jsonl_files = list(project_dir.glob('*.jsonl'))
    file_count = len(jsonl_files)
    last_modified = None
    total_messages = 0
    
    if jsonl_files:
        # Get most recent modification time
        timestamps = []
        for file in jsonl_files:
            try:
                timestamps.append(file.stat().st_mtime)
                # Count messages in file
                with open(file, 'r', encoding='utf-8') as f:
                    total_messages += sum(1 for line in f if line.strip())
            except:
                pass
        
        if timestamps:
            last_modified = datetime.fromtimestamp(max(timestamps)).strftime('%Y-%m-%d %H:%M')
    
    return {
        'name': project_name,
        'file_count': file_count,
        'total_messages': total_messages,
        'last_modified': last_modified or 'unknown',
        'path': project_dir
    }

def list_projects():
    """List all available projects"""
    claude_dir = get_claude_projects_dir()
    
    print_colored("📁 Available Claude Projects", Colors.BLUE)
    print("=" * 60)
    
    if not claude_dir.exists() or not any(claude_dir.iterdir()):
        print_colored("No projects found in {}".format(claude_dir), Colors.YELLOW)
        return []
    
    print_colored("Project Name                 Chats  Messages   Last Modified", Colors.CYAN)
    print("-" * 70)
    
    projects = []
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            info = get_project_info(project_dir)
            projects.append(info)
            print(f"{info['name']:<28} {info['file_count']:>5}  {info['total_messages']:>8}   {info['last_modified']}")
    
    return projects

def search_projects(search_term):
    """Search for projects containing search term"""
    claude_dir = get_claude_projects_dir()
    
    print_colored(f"🔍 Searching for projects containing: '{search_term}'", Colors.BLUE)
    print("=" * 60)
    
    found = False
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            clean_name = clean_project_name(project_dir.name)
            if search_term.lower() in clean_name.lower() or search_term.lower() in project_dir.name.lower():
                info = get_project_info(project_dir)
                print_colored(f"✅ {info['name']}", Colors.GREEN)
                print(f"   {info['file_count']} chats, {info['total_messages']} messages, modified: {info['last_modified']}")
                found = True
    
    if not found:
        print_colored(f"No projects found matching '{search_term}'", Colors.YELLOW)

def search_content(search_term):
    """Search for content within chats"""
    claude_dir = get_claude_projects_dir()
    
    print_colored(f"🔍 Searching chat content for: '{search_term}'", Colors.BLUE)
    print("=" * 60)
    
    found = False
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            project_name = clean_project_name(project_dir.name)
            
            for jsonl_file in project_dir.glob('*.jsonl'):
                chat_name = jsonl_file.stem
                
                try:
                    with open(jsonl_file, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if search_term.lower() in line.lower():
                                if not found:
                                    found = True
                                print_colored(f"📝 Found in: {project_name}/{chat_name}", Colors.GREEN)
                                
                                # Try to extract meaningful context
                                try:
                                    data = json.loads(line)
                                    message = data.get('message', {})
                                    content = message.get('content', '')
                                    role = message.get('role', 'unknown')
                                    
                                    if isinstance(content, str) and search_term.lower() in content.lower():
                                        preview = content[:100] + '...' if len(content) > 100 else content
                                        print(f"   Line {line_num} ({role}): {preview}")
                                    elif isinstance(content, list):
                                        for item in content:
                                            if isinstance(item, dict) and item.get('type') == 'text':
                                                text = item.get('text', '')
                                                if search_term.lower() in text.lower():
                                                    preview = text[:100] + '...' if len(text) > 100 else text
                                                    print(f"   Line {line_num} ({role}): {preview}")
                                                    break
                                except:
                                    # Fallback to simple line preview
                                    preview = line[:100] + '...' if len(line) > 100 else line
                                    print(f"   Line {line_num}: {preview}")
                                
                                print()
                                break  # Only show first match per file
                                
                except Exception as e:
                    continue
    
    if not found:
        print_colored(f"No content found matching '{search_term}'", Colors.YELLOW)

def show_recent_projects(count=10):
    """Show most recently modified projects"""
    claude_dir = get_claude_projects_dir()
    
    print_colored(f"⏰ {count} Most Recently Modified Projects", Colors.BLUE)
    print("=" * 60)
    
    projects = []
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            info = get_project_info(project_dir)
            if info['last_modified'] != 'unknown':
                # Get actual timestamp for sorting
                jsonl_files = list(project_dir.glob('*.jsonl'))
                if jsonl_files:
                    timestamps = []
                    for file in jsonl_files:
                        try:
                            timestamps.append(file.stat().st_mtime)
                        except:
                            pass
                    if timestamps:
                        info['sort_timestamp'] = max(timestamps)
                        projects.append(info)
    
    # Sort by timestamp and show top N
    projects.sort(key=lambda x: x.get('sort_timestamp', 0), reverse=True)
    
    for info in projects[:count]:
        print_colored(f"📝 {info['name']}", Colors.GREEN)
        print(f"   {info['file_count']} chats, {info['total_messages']} messages, {info['last_modified']}")

def parse_jsonl_file(file_path, format_type='pretty', output_file=None):
    """Parse JSONL file and format output"""
    
    if not Path(file_path).exists():
        print_colored(f"❌ File not found: {file_path}", Colors.RED)
        return
    
    chat_messages = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                if data and data.get('type') != 'summary':  # Skip summary entries
                    chat_messages.append(data)
            except json.JSONDecodeError as e:
                print(f'Warning: Skipping invalid JSON on line {line_num}: {e}', file=sys.stderr)
            except Exception as e:
                print(f'Warning: Error processing line {line_num}: {e}', file=sys.stderr)

    if not chat_messages:
        print_colored('No valid messages found', Colors.YELLOW)
        return

    output_lines = []

    if format_type in ['markdown', 'book']:
        output_lines.append('# Claude Chat Export\n')
        output_lines.append(f'**Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**\n')

    msg_count = 0
    for i, entry in enumerate(chat_messages, 1):
        # Extract the nested message structure
        message = entry.get('message', {})
        
        # Skip if no message content
        if not message:
            continue
        
        msg_count += 1
        
        # Get basic message info
        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')
        timestamp = format_timestamp(entry.get('timestamp'))
        tool_result = entry.get('toolUseResult')
        
        # Format the main content
        formatted_content = format_content(content, role)
        
        # Add tool result if present
        if tool_result:
            tool_output = format_tool_result(tool_result, role)
            if tool_output:
                formatted_content += tool_output
        
        # Skip truly empty messages
        if not formatted_content or formatted_content.strip() in ['[Empty unknown message]', '[No content in unknown message]']:
            continue
        
        if format_type == 'book':
            # Book format - clean, minimal presentation
            if role == 'user':
                # User question in callout style
                output_lines.append(f'> {formatted_content}\n\n')
            elif role == 'assistant':
                # Assistant response without headers
                output_lines.append(f'{formatted_content}\n\n')
            
        elif format_type == 'markdown':
            # Original markdown format
            output_lines.append(f'## Message {msg_count} - {role.title()}\n')
            output_lines.append(f'**Time:** {timestamp}\n\n')
            output_lines.append(f'{formatted_content}\n\n')
            output_lines.append('---\n\n')
        
        elif format_type == 'raw':
            output_lines.append(json.dumps(entry, indent=2))
        
        else:  # pretty format
            if role == 'user':
                color = Colors.GREEN
                icon = '👤'
            elif role == 'assistant':
                color = Colors.BLUE
                icon = '🤖'
            elif role == 'system':
                color = Colors.PURPLE
                icon = '⚙️'
            else:
                color = Colors.YELLOW
                icon = '❓'
            
            output_lines.append(f'{color}{icon} Message {msg_count} - {role.title()}{Colors.NC}')
            output_lines.append(f'🕒 {timestamp}')
            output_lines.append(f'💬 {formatted_content}')
            output_lines.append('─' * 80)

    result = '\n'.join(output_lines)

    if output_file and output_file != '-':
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result)
        print_colored(f'Chat exported to: {output_file}', Colors.GREEN)
    else:
        print(result)

def view_chat(file_path, format_type='pretty', output_file=None):
    """View a specific chat file"""
    filename = Path(file_path).name
    
    # Parse the file and get formatted content
    if not Path(file_path).exists():
        print_colored(f"❌ File not found: {file_path}", Colors.RED)
        return
    
    chat_messages = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                if data and data.get('type') != 'summary':  # Skip summary entries
                    chat_messages.append(data)
            except json.JSONDecodeError as e:
                print(f'Warning: Skipping invalid JSON on line {line_num}: {e}', file=sys.stderr)
            except Exception as e:
                print(f'Warning: Error processing line {line_num}: {e}', file=sys.stderr)

    if not chat_messages:
        print_colored('No valid messages found', Colors.YELLOW)
        return

    output_lines = []
    msg_count = 0
    
    for i, entry in enumerate(chat_messages, 1):
        # Extract the nested message structure
        message = entry.get('message', {})
        
        # Skip if no message content
        if not message:
            continue
        
        msg_count += 1
        
        # Get basic message info
        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')
        timestamp = format_timestamp(entry.get('timestamp'))
        tool_result = entry.get('toolUseResult')
        
        # Format the main content
        formatted_content = format_content(content, role)
        
        # Add tool result if present
        if tool_result:
            tool_output = format_tool_result(tool_result, role)
            if tool_output:
                formatted_content += tool_output
        
        # Skip truly empty messages
        if not formatted_content or formatted_content.strip() in ['[Empty unknown message]', '[No content in unknown message]']:
            continue
        
        if role == 'user':
            color = Colors.GREEN
            icon = '👤'
        elif role == 'assistant':
            color = Colors.BLUE
            icon = '🤖'
        elif role == 'system':
            color = Colors.PURPLE
            icon = '⚙️'
        else:
            color = Colors.YELLOW
            icon = '❓'
        
        output_lines.append(f'{color}{icon} Message {msg_count} - {role.title()}{Colors.NC}')
        output_lines.append(f'🕒 {timestamp}')
        output_lines.append(f'💬 {formatted_content}')
        output_lines.append('─' * 80)

    result = '\n'.join(output_lines)

    if output_file and output_file != '-':
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result)
        print_colored(f'Chat exported to: {output_file}', Colors.GREEN)
    else:
        # Use pager for interactive viewing
        title = f"💬 Viewing: {filename}"
        display_with_pager(result, title)

def browse_project(project_path, format_type='pretty', output_file=None):
    """Browse a specific project"""
    project_dir = Path(project_path)
    project_name = clean_project_name(project_dir.name)
    
    # Get all jsonl files in the project
    chat_files = list(project_dir.glob('*.jsonl'))
    chat_files.sort()
    
    if not chat_files:
        print_colored(f"No JSONL chat files found in project: {project_name}", Colors.YELLOW)
        return
    
    print_colored(f"💬 Project: {project_name}", Colors.BLUE)
    print("=" * 60)
    print_colored(f"Found {len(chat_files)} chat file(s):", Colors.CYAN)
    print()
    
    # Show files with numbers and message counts
    for i, file_path in enumerate(chat_files, 1):
        filename = file_path.stem
        try:
            size = file_path.stat().st_size
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d')
            
            # Count messages
            with open(file_path, 'r', encoding='utf-8') as f:
                msg_count = sum(1 for line in f if line.strip())
            
            print(f"{i:2d}) {filename:<30} {size_str:>8} {msg_count:>10} msgs {modified}")
        except Exception as e:
            print(f"{i:2d}) {filename:<30} {'error':>8} {'?':>10} msgs {'unknown'}")
    
    print()
    print_colored("Choose an option:", Colors.YELLOW)
    print(f"  1-{len(chat_files)}) View specific chat")
    print("  a) View all chats")
    print("  e) Export all to markdown")
    print("  eb) Export all to book format") 
    print("  b) Back to main menu")
    print("  q) Quit")
    print()
    
    while True:
        try:
            choice = input("Enter choice: ").strip()
            
            if choice.lower() in ['q', 'quit']:
                break
            elif choice.lower() == 'b':
                return  # Return to main menu
            elif choice.lower() == 'a':
                # View all chats
                for file_path in chat_files:
                    print()
                    print_colored("=" * 60, Colors.CYAN)
                    view_chat(file_path, format_type)
                    print()
                    next_input = input("Press Enter for next chat (or 'q' to stop)...")
                    if next_input.lower() == 'q':
                        break
                break
            elif choice.lower() == 'e':
                # Export all to markdown
                export_dir = f"{project_name}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(export_dir, exist_ok=True)
                print_colored(f"📤 Exporting all chats to markdown in: {export_dir}", Colors.BLUE)
                
                for file_path in chat_files:
                    chat_name = file_path.stem
                    export_file = os.path.join(export_dir, f"{chat_name}.md")
                    parse_jsonl_file(file_path, 'markdown', export_file)
                
                print_colored(f"✅ All chats exported to: {export_dir}/", Colors.GREEN)
                # List exported files
                for file in os.listdir(export_dir):
                    file_path = os.path.join(export_dir, file)
                    size = os.path.getsize(file_path)
                    print(f"   {file} ({size/1024:.1f}KB)")
                break
            elif choice.lower() == 'eb':
                # Export all to book format
                export_dir = f"{project_name}_book_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(export_dir, exist_ok=True)
                print_colored(f"📚 Exporting all chats to book format in: {export_dir}", Colors.BLUE)
                
                for file_path in chat_files:
                    chat_name = file_path.stem
                    export_file = os.path.join(export_dir, f"{chat_name}.md")
                    parse_jsonl_file(file_path, 'book', export_file)
                
                print_colored(f"✅ All chats exported to book format: {export_dir}/", Colors.GREEN)
                # List exported files
                for file in os.listdir(export_dir):
                    file_path = os.path.join(export_dir, file)
                    size = os.path.getsize(file_path)
                    print(f"   {file} ({size/1024:.1f}KB)")
                break
            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(chat_files):
                    view_chat(chat_files[choice_num - 1], format_type, output_file)
                    print()
                    input("Press Enter to continue...")
                    print()
                    
                    # Redisplay the project menu
                    print_colored(f"💬 Project: {project_name}", Colors.BLUE)
                    print("=" * 60)
                    print_colored(f"Found {len(chat_files)} chat file(s):", Colors.CYAN)
                    print()
                    
                    # Show files with numbers and message counts again
                    for i, file_path in enumerate(chat_files, 1):
                        filename = file_path.stem
                        try:
                            size = file_path.stat().st_size
                            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
                            modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d')
                            
                            # Count messages
                            with open(file_path, 'r', encoding='utf-8') as f:
                                msg_count = sum(1 for line in f if line.strip())
                            
                            print(f"{i:2d}) {filename:<30} {size_str:>8} {msg_count:>10} msgs {modified}")
                        except Exception as e:
                            print(f"{i:2d}) {filename:<30} {'error':>8} {'?':>10} msgs {'unknown'}")
                    
                    print()
                    print_colored("Choose an option:", Colors.YELLOW)
                    print(f"  1-{len(chat_files)}) View specific chat")
                    print("  a) View all chats")
                    print("  e) Export all to markdown")
                    print("  eb) Export all to book format")
                    print("  b) Back to main menu")
                    print("  q) Quit")
                    print()
                    
                    # Continue the loop to return to project menu
                    continue
                else:
                    print_colored(f"Invalid selection. Please choose 1-{len(chat_files)}", Colors.RED)
            else:
                print_colored("Invalid choice. Please enter a number, 'a', 'e', 'eb', 'b', or 'q'", Colors.RED)
        
        except KeyboardInterrupt:
            print()
            break
        except EOFError:
            break

def interactive_browser():
    """Interactive project browser"""
    claude_dir = get_claude_projects_dir()
    
    print_colored("🤖 Claude JSONL Chat Browser", Colors.BLUE)
    print("=" * 60)
    print()
    
    if not claude_dir.exists():
        print_colored(f"❌ Claude projects directory not found: {claude_dir}", Colors.RED)
        print("Make sure you have Claude Desktop installed and have created projects.")
        return
    
    # Get projects
    projects = []
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            info = get_project_info(project_dir)
            if info['file_count'] > 0:  # Only show projects with JSONL files
                projects.append(info)
    
    if not projects:
        print_colored(f"No projects with chat files found in {claude_dir}", Colors.YELLOW)
        return
    
    # Sort by last modified (most recent first)
    projects.sort(key=lambda x: x['last_modified'], reverse=True)
    
    print_colored("Available projects:", Colors.CYAN)
    print()
    
    for i, info in enumerate(projects, 1):
        # Format with better alignment
        name_col = f"{i:2d}) {info['name']}"
        details_col = f"({info['file_count']} chats, {info['total_messages']} msgs, {info['last_modified']})"
        
        # Align details to column 50 for better readability
        if len(name_col) < 48:
            padding = 48 - len(name_col)
            print(f"{name_col}{' ' * padding}{details_col}")
        else:
            # If name is too long, put details on next line with indentation
            print(f"{name_col}")
            print(f"{'':>50}{details_col}")
    
    print()
    print_colored("Options:", Colors.YELLOW)
    print(f"  1-{len(projects)}) Browse specific project")
    print("  l) List all projects with details")
    print("  r) Show recent projects")
    print("  c) Search chat content")
    print("  q) Quit")
    print()
    
    while True:
        try:
            choice = input("Enter choice: ").strip()
            
            if choice.lower() in ['q', 'quit']:
                print_colored("👋 Goodbye!", Colors.BLUE)
                break
            elif choice.lower() == 'l':
                print()
                list_projects()
                print()
                input("Press Enter to continue...")
                print()
                # Return to main menu by breaking and restarting
                return interactive_browser()
            elif choice.lower() == 'r':
                print()
                show_recent_projects(10)
                print()
                input("Press Enter to continue...")
                print()
                # Return to main menu by breaking and restarting
                return interactive_browser()
            elif choice.lower() == 'c':
                search_term = input("Enter search term: ").strip()
                if search_term:
                    print()
                    search_content(search_term)
                    print()
                    input("Press Enter to continue...")
                print()
                # Return to main menu by breaking and restarting
                return interactive_browser()
            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(projects):
                    print()
                    browse_project(projects[choice_num - 1]['path'])
                    # After browsing a project, return to main menu
                    print()
                    return interactive_browser()
                else:
                    print_colored(f"Invalid selection. Please choose 1-{len(projects)}", Colors.RED)
            else:
                print_colored("Invalid choice. Please enter a number, 'l', 'r', 'c', or 'q'", Colors.RED)
        
        except KeyboardInterrupt:
            print()
            print_colored("👋 Goodbye!", Colors.BLUE)
            break
        except EOFError:
            break

def main():
    parser = argparse.ArgumentParser(
        description='Claude JSONL Chat Reader - Browse and view Claude project chat files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Interactive project browser
  %(prog)s -l                        # List all projects
  %(prog)s -r 5                      # Show 5 most recent projects
  %(prog)s -s docker                 # Search for projects with 'docker' in name
  %(prog)s "my-project"              # View specific project chats
  %(prog)s "my-project" -f book      # View as clean book format
  %(prog)s "my-project" -f markdown  # View as markdown
  %(prog)s "my-project" -o chat.md   # Save to markdown file
  %(prog)s -c "update checker"       # Search chat content
        """
    )
    
    parser.add_argument('project', nargs='?', help='Project name to browse')
    parser.add_argument('-l', '--list', action='store_true', help='List all projects')
    parser.add_argument('-s', '--search', metavar='TERM', help='Search for projects containing TERM')
    parser.add_argument('-r', '--recent', metavar='N', type=int, nargs='?', const=10,
                       help='Show N most recently modified projects (default: 10)')
    parser.add_argument('-f', '--format', choices=['pretty', 'markdown', 'raw', 'book'], 
                       default='pretty', help='Output format (default: pretty, book=clean markdown without timestamps)')
    parser.add_argument('-o', '--output', metavar='FILE', help='Save output to file')
    parser.add_argument('-c', '--content', metavar='TERM', help='Search for content within chats')
    
    args = parser.parse_args()
    
    claude_dir = get_claude_projects_dir()
    
    # Check if Claude directory exists
    if not claude_dir.exists():
        print_colored(f"❌ Claude projects directory not found: {claude_dir}", Colors.RED)
        print("Make sure you have Claude Desktop installed and have created projects.")
        sys.exit(1)
    
    # Handle command line arguments
    if args.list:
        list_projects()
    elif args.search:
        search_projects(args.search)
    elif args.content:
        search_content(args.content)
    elif args.recent is not None:
        show_recent_projects(args.recent)
    elif args.project:
        # Browse specific project - handle both clean and original names
        project_path = None
        
        # First try to find by clean name
        for project_dir in claude_dir.iterdir():
            if project_dir.is_dir():
                clean_name = clean_project_name(project_dir.name)
                if clean_name.lower() == args.project.lower() or project_dir.name.lower() == args.project.lower():
                    project_path = project_dir
                    break
        
        if project_path and project_path.exists():
            browse_project(project_path, args.format, args.output)
        else:
            print_colored(f"Project not found: {args.project}", Colors.RED)
            print("Available projects:")
            list_projects()
    else:
        # Interactive browser
        interactive_browser()

if __name__ == '__main__':
    main()
