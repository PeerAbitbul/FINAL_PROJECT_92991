import gzip
import json
import zlib

#def parse_file(response):
#    decompressed = gzip.decompress(response.content)
#    text = decompressed.decode('utf-8')
#    lines = text.splitlines()
#    return lines


def parse_file(response):
    # gzip.decompress קורס על stream חתוך (truncated chaos). במקום זה משתמשים
    # ב-decompressobj שמחזיר את כל מה שהספיק להתפענח ולא זורק על סוף מוקדם.
    decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
    try:
        decompressed = decompressor.decompress(response.content)
        decompressed += decompressor.flush()
    except (zlib.error, OSError, EOFError) as e:
        # truncated gzip — שומרים את מה שכבר פוענח עד לנקודת החיתוך
        print(f"Truncated/corrupt gzip, keeping partial data: {e}", flush=True)
        decompressed = decompressor.flush()

    text = decompressed.decode('utf-8', errors='ignore')
    lines = text.splitlines()
    # השורה האחרונה עלולה להיות חצי-שורה בגלל החיתוך — נזרקת ב-parse_event
    return lines

def parse_event(line):
    try:
        event = json.loads(line)
        return event
    except json.JSONDecodeError as e:
        print(f"Error parsing line: {e}")
        return None
    
def normalize(event):
    event_type = event['type']

    if event_type == 'PushEvent':
        return {
            'type': 'push',
            'actor': event['actor']['login'],
            'repo': event['repo']['name'],
            'created_at': event['created_at'],
            'forced': event['payload'].get('forced', False),
            'commits': [
                {
                    'author_name': c['author']['name'],
                    'author_email': c['author']['email']
                }
                for c in event['payload'].get('commits', [])
            ]
        }

    elif event_type == 'PullRequestEvent':
        pr = event['payload']['pull_request']
        return {
            'type': 'pull_request',
            'actor': event['actor']['login'],
            'pr_author': pr['user']['login'],
            'repo': event['repo']['name'],
            'language': pr['base']['repo'].get('language'),
            'action': event['payload']['action'],
            'merged': pr.get('merged', False),
            'created_at': event['created_at']
        }

    elif event_type == 'WatchEvent':
        return {
            'type': 'watch',
            'actor': event['actor']['login'],
            'repo': event['repo']['name'],
            'created_at': event['created_at']
        }

    elif event_type == 'ForkEvent':
        return {
            'type': 'fork',
            'actor': event['actor']['login'],
            'repo': event['repo']['name'],
            'created_at': event['created_at']
        }

    else:
        return {
            'type': 'raw',
            'event_type': event['type'],
            'actor': event['actor']['login'],
            'repo': event['repo']['name'],
            'created_at': event['created_at'],
            'payload': event['payload']
        }
