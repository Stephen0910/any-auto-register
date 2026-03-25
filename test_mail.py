import json, re
with open('/tmp/mail_test.json') as f:
    data = json.load(f)
mail = data['results'][0]
raw = mail.get('raw', '')
print('raw len:', len(raw))
body_start = raw.find('\r\n\r\n')
print('body_start:', body_start)
search_text = raw[body_start:] if body_start != -1 else raw
search_text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', search_text)
search_text = re.sub(r'm=\+\d+\.\d+', '', search_text)
search_text = re.sub(r'\bt=\d+\b', '', search_text)
m = re.search(r'[A-Z0-9]{3}-[A-Z0-9]{3}', search_text)
print('pattern match:', m.group(0) if m else None)
# 也打印 before body
m2 = re.search(r'[A-Z0-9]{3}-[A-Z0-9]{3}', raw)
print('full raw match:', m2.group(0) if m2 else None)
