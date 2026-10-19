"""Metadata-only Live tool trace in the existing context SQLite database."""
import re

TOOLS = frozenset({'administer_omni_area','read_omni_document','write_omni_document','inspect_omni_area','update_omni_area','handoff_to_agent','list_omni_capabilities','read_omni_skill','list_omni_assets','read_omni_artifact','create_omni_artifact','create_omni_image','create_omni_media','read_current_omni_session', 'search_omni_context', 'request_internal_task',
                   'read_internal_task_status', 'cancel_internal_task', 'unsupported', 'session'})
STAGES = frozenset({'received', 'dispatch', 'response', 'error', 'send_attempt',
                    'sent_to_sdk', 'send_error', 'cancelled', 'duplicate', 'instrumented'})
ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_tool_audit (
        context_id INTEGER NOT NULL, user_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
        runtime_session_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL, stage TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        PRIMARY KEY(context_id,conversation_id,tool_call_id,stage))''')


def append(conn, row, data):
    if (set(data) != {'conversationId', 'toolCallId', 'toolName', 'stage'}
            or not isinstance(data['toolCallId'], str) or not ID.fullmatch(data['toolCallId'])
            or not isinstance(data['toolName'], str) or data['toolName'] not in TOOLS
            or not isinstance(data['stage'], str) or data['stage'] not in STAGES):
        raise ValueError('invalid_audit_metadata')
    if (data['toolName'] == 'session') != (data['stage'] == 'instrumented'):
        raise ValueError('invalid_audit_metadata')
    ensure(conn)
    previous = conn.execute('SELECT tool_name FROM live_tool_audit WHERE context_id=? AND conversation_id=? AND tool_call_id=? LIMIT 1',
                            (row['id'], row['conversation_id'], data['toolCallId'])).fetchone()
    if previous and previous['tool_name'] != data['toolName']:
        raise ValueError('tool_call_conflict')
    # Duplicate stage delivery is idempotent. Arguments/results never enter SQL.
    conn.execute('INSERT OR IGNORE INTO live_tool_audit(context_id,user_id,company_id,runtime_session_id,conversation_id,tool_call_id,tool_name,stage) VALUES(?,?,?,?,?,?,?,?)',
                 (row['id'], row['user_id'], row['company_id'], row['runtime_session_id'],
                  row['conversation_id'], data['toolCallId'], data['toolName'], data['stage']))


def read(conn, row, tool_call_id=None):
    ensure(conn)
    sql = 'SELECT tool_call_id,tool_name,stage,created_at FROM live_tool_audit WHERE context_id=? AND user_id=? AND company_id=? AND conversation_id=?'
    values = [row['id'], row['user_id'], row['company_id'], row['conversation_id']]
    if tool_call_id is not None:
        if not isinstance(tool_call_id, str) or not ID.fullmatch(tool_call_id):
            raise ValueError('invalid_tool_call_id')
        sql += ' AND tool_call_id=?'
        values.append(tool_call_id)
    rows = conn.execute(sql + ' ORDER BY rowid DESC LIMIT 200', values).fetchall()
    return [dict(r) for r in reversed(rows)]
