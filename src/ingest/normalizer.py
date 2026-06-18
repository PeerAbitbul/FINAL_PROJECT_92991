import gzip
import json

def parse_file(response):
    decompressed = gzip.decompress(response.content)
    text = decompressed.decode('utf-8')
    lines = text.splitlines()
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
