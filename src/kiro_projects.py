"""Kiro IDE project discovery and session management.

This module provides functionality for discovering Kiro IDE workspaces,
decoding workspace paths, and listing chat sessions.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.exceptions import ChatFileNotFoundError, InvalidChatFileError


@dataclass
class KiroSession:
    """Represents a single Kiro chat session.
    
    Attributes:
        session_id: Unique identifier for the session
        title: Session title (truncated first message)
        date_created: Timestamp when session was created (in milliseconds)
        workspace_directory: Path to the workspace directory
        chat_file_path: Path to the .json file for this session
    """
    session_id: str
    title: str
    date_created: str
    workspace_directory: str
    chat_file_path: Path


@dataclass
class KiroWorkspace:
    """Represents a Kiro workspace with its sessions.
    
    Attributes:
        workspace_path: Full path to the workspace directory
        workspace_name: Human-readable workspace name
        sessions: List of chat sessions in this workspace
        session_count: Number of sessions in this workspace
        last_modified: Last modification timestamp as string
    """
    workspace_path: str
    workspace_name: str
    sessions: List[KiroSession]
    session_count: int
    last_modified: str


def decode_workspace_path(encoded_path: str) -> str:
    """Decode base64-encoded workspace path to human-readable name.
    
    Kiro encodes workspace paths using URL-safe base64 encoding.
    This function decodes them back to the original path string.
    
    Args:
        encoded_path: Base64-encoded workspace path
        
    Returns:
        Decoded workspace path string
        
    Raises:
        ValueError: If the encoded path cannot be decoded
    """
    try:
        # Calculate correct padding based on string length
        # Base64 strings must be a multiple of 4 characters
        padding_needed = (4 - len(encoded_path) % 4) % 4
        padded_encoded = encoded_path + ('=' * padding_needed)
        
        # URL-safe base64 decoding
        decoded_bytes = base64.urlsafe_b64decode(padded_encoded)
        return decoded_bytes.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to decode workspace path '{encoded_path}': {e}")


def list_kiro_sessions(workspace_dir: Path) -> List[KiroSession]:
    """List all chat sessions in a Kiro workspace.
    
    Reads the sessions.json file to get session metadata and maps
    each session to its corresponding .chat file.
    
    Args:
        workspace_dir: Path to workspace-sessions subdirectory
        
    Returns:
        List of KiroSession objects
        
    Raises:
        ChatFileNotFoundError: If sessions.json doesn't exist
        InvalidChatFileError: If sessions.json is malformed
    """
    sessions_file = workspace_dir / 'sessions.json'
    
    if not sessions_file.exists():
        raise ChatFileNotFoundError(f"sessions.json not found in {workspace_dir}")
    
    try:
        with open(sessions_file, 'r', encoding='utf-8') as f:
            sessions_data = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidChatFileError(f"Invalid JSON in sessions.json: {e}")
    
    if not isinstance(sessions_data, list):
        raise InvalidChatFileError("sessions.json must contain a JSON array")
    
    kiro_sessions = []
    for session in sessions_data:
        session_id = session.get('sessionId', '')
        title = session.get('title', 'Untitled')
        date_created = session.get('dateCreated', '')
        workspace_directory = session.get('workspaceDirectory', '')
        
        # Construct path to the .chat file
        chat_file_path = workspace_dir / f"{session_id}.json"
        
        kiro_sessions.append(KiroSession(
            session_id=session_id,
            title=title,
            date_created=str(date_created),
            workspace_directory=workspace_directory,
            chat_file_path=chat_file_path
        ))
    
    return kiro_sessions


def discover_kiro_workspaces(kiro_data_dir: Path) -> List[KiroWorkspace]:
    """Discover all Kiro workspaces and their sessions.
    
    Scans the Kiro data directory for workspace-sessions folders,
    decodes workspace paths, and lists all sessions in each workspace.
    
    Args:
        kiro_data_dir: Path to Kiro data directory
        
    Returns:
        List of KiroWorkspace objects
    """
    workspaces = []
    
    # Look for workspace-sessions directory
    workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
    
    if not workspace_sessions_dir.exists():
        return workspaces
    
    # Iterate through each workspace directory
    for workspace_dir in workspace_sessions_dir.iterdir():
        if not workspace_dir.is_dir():
            continue
        
        # The directory name is the base64-encoded workspace path
        encoded_path = workspace_dir.name
        
        try:
            # Decode the workspace path
            decoded_path = decode_workspace_path(encoded_path)
            workspace_name = Path(decoded_path).name or decoded_path
        except ValueError:
            # If decoding fails, use the encoded path as fallback
            workspace_name = encoded_path
            decoded_path = encoded_path
        
        try:
            # List all sessions in this workspace
            sessions = list_kiro_sessions(workspace_dir)
            
            if not sessions:
                continue
            
            # Calculate last modified time from sessions
            last_modified_timestamp = 0
            for session in sessions:
                try:
                    timestamp = int(session.date_created)
                    if timestamp > last_modified_timestamp:
                        last_modified_timestamp = timestamp
                except (ValueError, TypeError):
                    pass
            
            # Convert timestamp to readable format
            if last_modified_timestamp > 0:
                from datetime import datetime
                last_modified = datetime.fromtimestamp(
                    last_modified_timestamp / 1000  # Convert ms to seconds
                ).strftime('%Y-%m-%d %H:%M:%S')
            else:
                last_modified = 'Unknown'
            
            workspaces.append(KiroWorkspace(
                workspace_path=decoded_path,
                workspace_name=workspace_name,
                sessions=sessions,
                session_count=len(sessions),
                last_modified=last_modified
            ))
        except (ChatFileNotFoundError, InvalidChatFileError):
            # Skip workspaces with missing or invalid sessions.json
            continue
    
    return workspaces
