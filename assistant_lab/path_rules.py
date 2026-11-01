"""Canonical local paths and grounding against paths actually supplied by the user."""
from __future__ import annotations
import ntpath,posixpath,re
from urllib.parse import urlsplit,unquote


def normalize_path(value):
    value=str(value).strip().strip('"\'“”')
    if value.casefold().startswith('file:'):
        url=urlsplit(value);path=unquote(url.path)
        if url.netloc and url.netloc.casefold()!='localhost':path='//'+url.netloc+path
        value=path
        if re.match(r'^/[A-Za-z]:[\\/]',value):value=value[1:]
    if re.match(r'^/mnt/[a-zA-Z]/',value):value=value[5].upper()+':/'+value[7:]
    if re.match(r'^[A-Za-z]:[\\/]',value) or value.startswith(('\\\\','//')):
        return ntpath.normpath(value.replace('/','\\')).replace('\\','/')
    return posixpath.normpath(value) if value else ''


def path_key(value):
    normalized=normalize_path(value)
    return normalized.casefold() if re.match(r'^[A-Za-z]:/',normalized) or normalized.startswith('//') else normalized

def text_without_paths(text):
    prefix=r'(?:file://|[A-Za-z]:[\\/]|\\\\|/mnt/[a-zA-Z]/)'
    text=re.sub(r'["“\']'+prefix+r'[^"”\'\r\n]+["”\']',' ',text,flags=re.I)
    return re.sub(prefix+r'[^\s"“”\'<>|]+',' ',text,flags=re.I)


def extract_paths(text):
    prefix=r'(?:file://|[A-Za-z]:[\\/]|\\\\|/mnt/[a-zA-Z]/)'
    quoted=list(re.finditer(r'["“\']('+prefix+r'[^"”\'\r\n]+)["”\']',text,re.I))
    found=[(m.start(),m[1]) for m in quoted]
    for match in re.finditer(prefix+r'[^\s"“”\'<>|]+',text,re.I):
        if any(q.start()<=match.start()<q.end() for q in quoted):continue
        value=match[0].rstrip('.,;!?，。；！？')
        while value.endswith(')') and value.count(')')>value.count('('):value=value[:-1]
        while value.endswith(']') and value.count(']')>value.count('['):value=value[:-1]
        found.append((match.start(),value))
    paths=[];seen=set()
    for _,raw in sorted(found):
        value=normalize_path(raw);key=path_key(value)
        if key not in seen:paths.append(value);seen.add(key)
    return paths


def ground_path_updates(pairs,text,settings,path_fields):
    supplied={path_key(p):p for p in extract_paths(text)};verified=[];notes=[]
    for pair in pairs:
        field=pair.get('field');value=pair.get('value')
        if field not in path_fields:verified.append(pair);continue
        if not isinstance(value,str):raise ValueError('Invalid path value')
        key=path_key(value)
        if key in supplied:
            verified.append({'field':field,'value':supplied[key]})
            if value!=supplied[key]:notes.append('Normalized explicit '+field)
        elif key and key==path_key(settings.get(field,'')):
            notes.append('Ignored repeated current '+field)
        elif field in ('output_root','checkpoint','resume_checkpoint'):
            notes.append('Ignored unrequested '+field)
        else:
            raise ValueError('Please paste the exact input file or folder path. The proposed '+str(field)+' was not in your message.')
    return verified,notes
