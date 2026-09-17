"""Send one generated session prompt to the local Ollama server."""
import argparse
import json
from pathlib import Path
import requests
from story_memory import MEMORY_PATH, parse_story, save_story


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt', type=Path, default=Path(__file__).with_name('day1_prompt.json'))
    parser.add_argument('--session', type=int, default=0, help='Zero-based session index; never combine reload histories')
    parser.add_argument('--model', default='qwen3')
    parser.add_argument('--memory', type=Path, default=MEMORY_PATH)
    args = parser.parse_args()
    data = json.loads(args.prompt.read_text(encoding='utf-8'))
    if not 0 <= args.session < len(data['sessions']):
        parser.error('Session index is out of range')
    args.session = 1
    session = data['sessions'][args.session]
    prompt = session['prompt']
    #print(prompt)
    
    print(f"Using session {session['session_id']} ({session['event_count']} events)")
    response = requests.post(
        'http://localhost:11434/api/chat',
        json={
            'model': args.model,
            'messages': [
                {'role': 'system', 'content': prompt['system']},
                {'role': 'user', 'content': prompt['user'] if isinstance(prompt['user'], str) else json.dumps(prompt['user'], ensure_ascii=False, indent=2)},
            ],
            'stream': False,
            'format': 'json',
        },
        timeout=600,
    )
    response.raise_for_status()
    content = response.json()['message']['content']
    print(content)
    try:
        story = parse_story(content)
    except (ValueError, TypeError) as error:
        print(f"Story memory was not changed: {error}")
        return
    save_story(story, session, data['day'], args.memory)
    print(f"Saved chronicle and story_bits to {args.memory}")


if __name__ == '__main__':
    main()
