import string

from bs4 import BeautifulSoup
import re
import urllib.error
import urllib.request
import random
import time

def get_lyrics_doc(lyric_id:int) -> BeautifulSoup:
    try:
        html_url = urllib.request.urlopen("https://songmeanings.com/songs/view/%d/" % lyric_id)
    except urllib.error.HTTPError:
        return None
    doc = html_url.read()
    if b'Error - Does Not Exist' in doc:
        return None
    return BeautifulSoup(doc, 'html.parser')

def get_comments_count(soup:BeautifulSoup) -> str:
    return soup.find('a', id='header-comments-counter').text.split()[0]

def get_lyrics(soup:BeautifulSoup) -> str:
    return soup.find('div', 'lyric-box').text.replace("'", '').replace('"', '').replace('/', '').strip()

def get_title(soup:BeautifulSoup) -> str:
    return soup.title.text[:-1 * len(' Lyrics | SongMeanings')].strip()

def get_lyrics_match(lyrics:str, regex:re.Pattern) -> str:
    matches = regex.findall(lyrics)
    if matches:
        return random.choice(matches)
    return ''

def make_regex(word_lengths:list) -> re.Pattern:
    regex_str = r'\W+'
    for word_len in word_lengths:
        regex_str += '\w{%d}' % word_len
        regex_str += '\W+'
    return re.compile(regex_str, re.M)

# words by length
# NEVER GONNA GIVE YOU UP = [5,5,4,3,2]
WHEEL_PATTERN = [5,5,4,3,2,5,5,3,3,4]
WHEEL_RE = make_regex(WHEEL_PATTERN)

g_counter = 0

def main(lyric_id:int):
    global g_counter
    doc = get_lyrics_doc(lyric_id)
    if not doc:
        return
    g_counter += 1
    print("{:5}. {:6} - {} ({} comments)...".format(g_counter, lyric_id, get_title(doc), get_comments_count(doc)))
    lm = get_lyrics_match( get_lyrics(doc), WHEEL_RE )
    if lm:
        s = "{}: {}({}): {}".format(time.asctime(), get_title(doc), lyric_id, lm)
        print('*' * len(s))
        print(s)
        print('*' * len(s))
        with open(r"C:\tmp\wheel.txt", 'a') as f:
            f.write(s + '\n')

if __name__ == "__main__":
    visited = []
    lid = random.randint(1000,160000)
    while len(visited) < 95000:
        while lid in visited:
            lid = random.randint(1000,150000)
        main(lid)
        visited.append(lid)
        time.sleep(0.25)