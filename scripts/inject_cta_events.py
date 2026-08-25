#!/usr/bin/env python3
"""Inject Plausible custom event attributes into CTA links in Ghost posts.

For each published post with links to sistemabritto.com.br, add:
  - class="plausible-event--cta-<funnel>" (Plausible custom event via CSS class)
  - data-funnel="whatsapp"|"sistema"|"socialjobs" (semantic attr)

The Plausible snippet tracks custom events when elements have class
"plausible-event--<event-name>". We use the funnel name as event name
so the dashboard shows: cta-whatsapp, cta-sistema, cta-socialjobs.
"""
import os, re, subprocess, sys

DB_CONTAINER_CMD = "docker ps -q -f name=ghost_ghost_db | head -1"

# Alias do ~/.ssh/config, não IP/usuário hardcoded — mesma convenção do resto
# do workspace (ver .claude/rules/integrations.md). A senha do MySQL vem de
# env, nunca de literal no script: GHOST_DB_MYSQL_PWD, a mesma que o
# container do Ghost já usa (checar em config/.env na VPS).
SSH_HOST = os.environ.get("EVO_NEXUS_SSH_HOST", "evo-nexus-vps")
MYSQL_PWD = os.environ.get("GHOST_DB_MYSQL_PWD")

def run_ssh(cmd, timeout=60):
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", SSH_HOST, cmd],
        capture_output=True, text=True, timeout=timeout
    )
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def get_posts():
    """Get all published posts with sistemabritto.com.br links."""
    cmd = (
        "CONTAINER=$(docker ps -q -f name=ghost_ghost_db | head -1) && "
        f"docker exec -e MYSQL_PWD='{MYSQL_PWD}' $CONTAINER mysql -uroot ghost_db -N -e "
        "\"SELECT id, slug, html FROM posts WHERE status='published' AND html LIKE '%sistemabritto.com.br/%'\""
    )
    out, err, rc = run_ssh(cmd, timeout=60)
    if rc != 0:
        print(f"Error getting posts: {err}")
        return []

    posts = []
    # Parse tab-separated: id \t slug \t html (html is multi-line, so we need to handle this)
    # MySQL -N gives raw output, tab-separated columns, but html can contain newlines and tabs
    # Better approach: get ids and slugs first, then process each post individually
    return out

def detect_funnel(url):
    """Detect which funnel a URL points to."""
    url_lower = url.lower()
    if '/whatsapp' in url_lower or 'wa.me' in url_lower:
        return 'whatsapp'
    if '/socialjobs' in url_lower:
        return 'socialjobs'
    if '/sistema' in url_lower or '/socialjobs' in url_lower:
        return 'sistema'
    if 'sistemabritto.com.br' in url_lower:
        return 'site'
    return None

# Strategy: process each post individually to avoid multi-line HTML issues
# 1. Get list of post IDs
# 2. For each post, extract html, modify, update back

def main():
    if not MYSQL_PWD:
        print("GHOST_DB_MYSQL_PWD não está definida — sem ela a chamada roda "
              "com senha vazia e falha silenciosamente lá no MySQL.", file=sys.stderr)
        sys.exit(1)

    # Step 1: Get all post IDs that have CTA links
    cmd = (
        "CONTAINER=$(docker ps -q -f name=ghost_ghost_db | head -1) && "
        f"docker exec -e MYSQL_PWD='{MYSQL_PWD}' $CONTAINER mysql -uroot ghost_db -N -e "
        "\"SELECT id, slug FROM posts WHERE status='published' AND html LIKE '%sistemabritto.com.br/%'\""
    )
    out, err, rc = run_ssh(cmd, timeout=60)
    if rc != 0:
        print(f"Error: {err}")
        sys.exit(1)

    posts = []
    for line in out.strip().split('\n'):
        if '\t' in line:
            parts = line.split('\t', 1)
            if len(parts) == 2:
                posts.append((parts[0], parts[1]))

    print(f"Found {len(posts)} posts with CTA links")

    updated = 0
    skipped = 0

    for post_id, slug in posts:
        # Get HTML for this post
        cmd = (
            f"CONTAINER=$(docker ps -q -f name=ghost_ghost_db | head -1) && "
            f"docker exec -e MYSQL_PWD='{MYSQL_PWD}' $CONTAINER mysql -uroot ghost_db -N -e "
            f"\"SELECT html FROM posts WHERE id='{post_id}'\""
        )
        html, err, rc = run_ssh(cmd, timeout=60)
        if rc != 0 or not html:
            print(f"  SKIP {slug}: could not fetch HTML")
            skipped += 1
            continue

        # Process: find all <a> tags with href containing sistemabritto.com.br
        # and add plausible-event class if not already present
        original_html = html
        modifications = 0

        # Pattern: <a href="...sistemabritto.com.br/...">
        # We need to add class="plausible-event--cta-<funnel>" to the <a> tag
        # Handle both: <a href="..." class="..."> and <a href="...">

        def replace_link(match):
            nonlocal modifications
            full_tag = match.group(0)
            href_match = re.search(r'href="([^"]+)"', full_tag)
            if not href_match:
                return full_tag
            href = href_match.group(1)
            # Only process sistemabritto links (not blog links)
            if 'sistemabritto.com.br/' not in href and 'wa.me' not in href:
                return full_tag
            # Skip blog.sistemabritto links (internal)
            if 'blog.sistemabritto' in href:
                return full_tag

            funnel = detect_funnel(href)
            if not funnel:
                return full_tag

            event_class = f'plausible-event--cta-{funnel}'

            # Check if already has plausible-event class
            if 'plausible-event--' in full_tag:
                return full_tag

            # Add class attribute
            if 'class="' in full_tag:
                # Append to existing class
                new_tag = re.sub(
                    r'class="([^"]*)"',
                    lambda m: f'class="{m.group(1)} {event_class}"',
                    full_tag
                )
            else:
                # Add class attribute after the href
                new_tag = re.sub(
                    r'(href="[^"]*")',
                    f'\\1 class="{event_class}"',
                    full_tag,
                    count=1
                )

            modifications += 1
            return new_tag

        # Match <a ...> tags (opening tag only)
        new_html = re.sub(r'<a\s[^>]*href="[^"]*"[^>]*>', replace_link, html)

        if new_html == original_html:
            print(f"  SKIP {slug}: no modifications needed")
            skipped += 1
            continue

        print(f"  UPDATE {slug}: {modifications} links modified")

        # Write new HTML back to DB
        # Escape single quotes for SQL
        escaped_html = new_html.replace("\\", "\\\\").replace("'", "\\'")

        cmd = (
            f"CONTAINER=$(docker ps -q -f name=ghost_ghost_db | head -1) && "
            f"docker exec -e MYSQL_PWD='{MYSQL_PWD}' $CONTAINER mysql -uroot ghost_db -e "
            f"\"UPDATE posts SET html='{escaped_html}' WHERE id='{post_id}'\""
        )
        out, err, rc = run_ssh(cmd, timeout=120)
        if rc != 0:
            print(f"  ERROR writing {slug}: {err[:200]}")
            skipped += 1
        else:
            updated += 1

    print(f"\nDone: {updated} posts updated, {skipped} skipped")

if __name__ == '__main__':
    main()